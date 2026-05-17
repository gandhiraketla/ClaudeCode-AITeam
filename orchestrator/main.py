import os
import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv, dotenv_values

from . import state as db
from .models import ProjectState
from .router import parse_mention
from .approval_handler import handle_approval
from .context_builder import build_context
from .skill_runner import run_skill
from .workspace_manager import create_project_workspace, write_artifact, get_file_tree, get_project_paths
from . import git_helper as git
from . import slack_client as slack
from . import console

load_dotenv()
logging.basicConfig(level=logging.WARNING)

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
ENV_PATH = Path(__file__).parent.parent / ".env"


# --- Slack signature verification ---

def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    base = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# --- FastAPI app ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    console.banner()
    yield

app = FastAPI(lifespan=lifespan)


@app.post("/slack/events")
async def slack_events(request: Request):
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body, timestamp, signature):
        return Response(content="Unauthorized", status_code=401)

    payload = json.loads(body)

    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    event_data = payload.get("event", {})
    asyncio.create_task(handle_event(event_data))
    return Response(content="OK", status_code=200)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ClaudeForge"}


# --- Event handler ---

async def handle_event(event: dict):
    if event.get("bot_id") or event.get("subtype"):
        return

    text = event.get("text", "").strip()
    user = event.get("user")
    channel = event.get("channel")
    ts = event.get("ts")
    thread_ts = event.get("thread_ts")

    if not text or not user or not channel:
        return

    is_thread = bool(thread_ts and thread_ts != ts)
    console.event_received(user, text, is_thread)

    if is_thread:
        project = await db.get_project_by_thread(thread_ts)
        if not project:
            return
        await handle_thread_reply(project, text, channel, thread_ts, ts)
        return

    persona, user_request = parse_mention(text)
    if not persona:
        return

    if persona != "ba":
        console.routing("ba", "Non-BA mention — redirecting")
        await slack.post_message(channel,
            "Start with `@Business-Analyst` to begin a new project.", ts, "ba")
        return

    console.routing("ba", "New project request detected")
    await handle_new_project(user_request, channel, ts)


async def handle_new_project(user_request: str, channel: str, thread_ts: str):
    project_id = await db.create_project(channel, thread_ts)
    paths = create_project_workspace(project_id)
    await db.add_message(project_id, "user", user_request, slack_ts=thread_ts)

    console.project_created(project_id, paths["workspace_path"])
    console.state_transition("IDLE", "DISCOVERY_ACTIVE")

    thinking_ts = await slack.post_thinking(channel, thread_ts, "ba")
    try:
        context = await build_context(project_id, "DISCOVERY_ACTIVE", "ba",
                                      user_message=user_request, turn=1)
        console.skill_invoked("ba", turn=1)
        console.context_summary(context)
        result = await run_skill("ba", context)
        console.skill_result("ba", result)
        await process_ba_result(project_id, result, channel, thread_ts, thinking_ts, turn=1)
    except Exception as e:
        await handle_stage_error(project_id, "ba", ProjectState.DISCOVERY_ACTIVE,
                                  str(e), channel, thread_ts, thinking_ts)


async def handle_thread_reply(project: dict, text: str, channel: str,
                               thread_ts: str, ts: str):
    project_id = project["id"]
    current_state = project["state"]

    await db.add_message(project_id, "user", text, slack_ts=ts)
    clean_text = text.strip().lower().strip("*_~` ")

    # Resume command
    if clean_text.startswith("resume"):
        await handle_resume(project_id, current_state, channel, thread_ts)
        return

    # Approval states
    if current_state.endswith("_APPROVAL_PENDING"):
        result = await handle_approval(project_id, text, channel, thread_ts)
        if result["handled"]:
            console.approval_received(result["approved"], result.get("feedback", ""))
            if result["approved"]:
                console.state_transition(current_state, result["next_stage"])
                await route_to_next_stage(project_id, result["next_stage"],
                                          result["next_persona"], channel, thread_ts)
            else:
                console.routing(result["next_persona"], "Changes requested -- re-running")
                await rerun_with_feedback(project_id, result["next_stage"],
                                          result["next_persona"], result["feedback"],
                                          channel, thread_ts)
        else:
            await slack.post_message(channel,
                "_Waiting for approval. Reply *approved* or *changes* + feedback._",
                thread_ts, "ba")
        return

    # BLOCKED state
    if current_state == ProjectState.BLOCKED:
        await slack.post_message(channel,
            "Project is blocked. Reply *resume* to retry the failed stage.",
            thread_ts, "ba")
        return

    # Architect waiting for keys
    if current_state == ProjectState.ARCH_WAITING_FOR_KEYS:
        if clean_text in ("ready", "done", "updated", "skip", "proceed", "continue"):
            await handle_keys_confirmed(project_id, channel, thread_ts)
        else:
            # User asked a question or wants to change APIs — route back into Arch discovery
            await db.update_state(project_id, ProjectState.ARCH_DISCOVERY_ACTIVE)
            thinking_ts = await slack.post_thinking(channel, thread_ts, "architect")
            try:
                messages = await db.get_messages(project_id)
                turn = len([m for m in messages if m.get("persona") == "architect"]) + 1
                context = await build_context(project_id, "ARCH_DISCOVERY_ACTIVE", "architect",
                                              user_message=text, turn=turn)
                console.skill_invoked("architect", turn=turn)
                result = await run_skill("architect", context)
                console.skill_result("architect", result)
                await process_arch_discovery_result(project_id, result, channel, thread_ts, thinking_ts, turn)
            except Exception as e:
                await handle_stage_error(project_id, "architect", ProjectState.ARCH_DISCOVERY_ACTIVE,
                                          str(e), channel, thread_ts, thinking_ts)
        return

    # BA discovery waiting
    if current_state == ProjectState.DISCOVERY_WAITING:
        await db.update_state(project_id, ProjectState.DISCOVERY_ACTIVE)
        console.state_transition("DISCOVERY_WAITING", "DISCOVERY_ACTIVE")
        messages = await db.get_messages(project_id)
        turn = len([m for m in messages if m["role"] == "agent"]) + 1
        thinking_ts = await slack.post_thinking(channel, thread_ts, "ba")
        try:
            context = await build_context(project_id, "DISCOVERY_ACTIVE", "ba",
                                          user_message=text, turn=turn)
            console.skill_invoked("ba", turn=turn)
            console.context_summary(context)
            result = await run_skill("ba", context)
            console.skill_result("ba", result)
            await process_ba_result(project_id, result, channel, thread_ts, thinking_ts, turn)
        except Exception as e:
            await handle_stage_error(project_id, "ba", ProjectState.DISCOVERY_ACTIVE,
                                      str(e), channel, thread_ts, thinking_ts)
        return

    # Architect discovery waiting
    if current_state == ProjectState.ARCH_DISCOVERY_WAITING:
        await db.update_state(project_id, ProjectState.ARCH_DISCOVERY_ACTIVE)
        console.state_transition("ARCH_DISCOVERY_WAITING", "ARCH_DISCOVERY_ACTIVE")
        messages = await db.get_messages(project_id)
        turn = len([m for m in messages if m["role"] == "agent" and m.get("persona") == "architect"]) + 1
        thinking_ts = await slack.post_thinking(channel, thread_ts, "architect")
        try:
            context = await build_context(project_id, "ARCH_DISCOVERY_ACTIVE", "architect",
                                          user_message=text, turn=turn)
            console.skill_invoked("architect", turn=turn)
            console.context_summary(context)
            result = await run_skill("architect", context)
            console.skill_result("architect", result)
            await process_arch_discovery_result(project_id, result, channel, thread_ts, thinking_ts, turn)
        except Exception as e:
            await handle_stage_error(project_id, "architect", ProjectState.ARCH_DISCOVERY_ACTIVE,
                                      str(e), channel, thread_ts, thinking_ts)
        return

    # Auto-processing states
    auto_states = [
        ProjectState.SECURITY_ACTIVE, ProjectState.IMPLEMENTATION_ACTIVE,
        ProjectState.REVIEW_ACTIVE, ProjectState.TESTING_ACTIVE,
        ProjectState.ARCHITECTURE_ACTIVE, ProjectState.AGENT_DESIGN_ACTIVE,
        ProjectState.DISCOVERY_ACTIVE, ProjectState.ARCH_DISCOVERY_ACTIVE,
        ProjectState.DEVOPS_ACTIVE,
    ]
    if ProjectState(current_state) in auto_states:
        await slack.post_message(channel,
            f"_Pipeline is running ({current_state}). Please wait..._",
            thread_ts, "ba")
        return

    console.error("orchestrator", f"Unhandled reply in state {current_state}")


# --- BA Discovery ---

async def process_ba_result(project_id: str, result: dict, channel: str,
                             thread_ts: str, thinking_ts: str, turn: int):
    status = result.get("status")

    if status == "asking":
        question = result.get("question", "")
        console.posting_to_slack("ba", question)
        await slack.update_message(channel, thinking_ts, question, "ba")
        await db.add_message(project_id, "agent", question, persona="ba")
        console.state_transition("DISCOVERY_ACTIVE", "DISCOVERY_WAITING")
        await db.update_state(project_id, ProjectState.DISCOVERY_WAITING)
        if turn >= 6:
            await force_ba_summary(project_id, channel, thread_ts)

    elif status == "ready":
        req_doc = result.get("requirements_doc", {})
        formatted = format_requirements(req_doc)
        file_path = write_artifact(project_id, "requirements.md", formatted)
        console.artifact_written("ba", file_path)
        await db.save_artifact(project_id, "ba", formatted, file_path)
        git.commit_artifact(project_id, "ba", "requirements document")
        git.push()

        # Derive project name from problem statement
        problem = req_doc.get("problem_statement", "")
        if problem:
            name = derive_project_name(problem)
            await db.update_project_name(project_id, name)
            print(f"  Project name: {name}", flush=True)

        summary = build_requirements_summary(req_doc)
        console.posting_to_slack("ba", summary)
        await slack.update_message(channel, thinking_ts, summary, "ba")
        await db.add_message(project_id, "agent", summary, persona="ba")
        await slack.upload_file(channel, thread_ts, file_path, "Requirements Document")
        console.state_transition("DISCOVERY_ACTIVE", "DISCOVERY_APPROVAL_PENDING")
        await db.update_state(project_id, ProjectState.DISCOVERY_APPROVAL_PENDING)


async def force_ba_summary(project_id: str, channel: str, thread_ts: str):
    thinking_ts = await slack.post_thinking(channel, thread_ts, "ba")
    context = await build_context(project_id, "DISCOVERY_ACTIVE", "ba",
                                  user_message="Summarize requirements now.", turn=99)
    result = await run_skill("ba", context)
    await process_ba_result(project_id, result, channel, thread_ts, thinking_ts, turn=99)


def derive_project_name(problem_statement: str) -> str:
    """Extract a short meaningful project name from the problem statement."""
    words = re.sub(r"[^a-zA-Z0-9\s]", "", problem_statement).split()
    stop = {"a", "an", "the", "and", "or", "for", "to", "of", "in", "is", "are",
            "this", "that", "with", "by", "on", "at", "from", "as", "it", "be"}
    key_words = [w.lower() for w in words if w.lower() not in stop][:4]
    return "-".join(key_words) if key_words else "claudeforge-project"


# --- Architect Discovery ---

async def run_arch_discovery(project_id: str, channel: str, thread_ts: str):
    await db.update_state(project_id, ProjectState.ARCH_DISCOVERY_ACTIVE)
    console.state_transition("DISCOVERY_APPROVAL_PENDING", "ARCH_DISCOVERY_ACTIVE")
    thinking_ts = await slack.post_thinking(channel, thread_ts, "architect")
    try:
        context = await build_context(project_id, "ARCH_DISCOVERY_ACTIVE", "architect",
                                      user_message="", turn=1)
        console.skill_invoked("architect", turn=1)
        console.context_summary(context)
        result = await run_skill("architect", context)
        console.skill_result("architect", result)
        await process_arch_discovery_result(project_id, result, channel, thread_ts, thinking_ts, turn=1)
    except Exception as e:
        await handle_stage_error(project_id, "architect", ProjectState.ARCH_DISCOVERY_ACTIVE,
                                  str(e), channel, thread_ts, thinking_ts)


async def process_arch_discovery_result(project_id: str, result: dict, channel: str,
                                         thread_ts: str, thinking_ts: str, turn: int):
    status = result.get("status")

    if status == "asking":
        question = result.get("question", "")
        console.posting_to_slack("architect", question)
        await slack.update_message(channel, thinking_ts, question, "architect")
        await db.add_message(project_id, "agent", question, persona="architect")
        console.state_transition("ARCH_DISCOVERY_ACTIVE", "ARCH_DISCOVERY_WAITING")
        await db.update_state(project_id, ProjectState.ARCH_DISCOVERY_WAITING)
        if turn >= 5:
            await force_arch_design(project_id, channel, thread_ts)

    elif status == "needs_keys":
        required_keys = result.get("required_api_keys", [])
        await db.update_state(project_id, ProjectState.ARCH_WAITING_FOR_KEYS)
        console.state_transition("ARCH_DISCOVERY_ACTIVE", "ARCH_WAITING_FOR_KEYS")

        key_lines = "\n".join(
            f"• `{k['key']}` — {k['purpose']}\n  Get it: {k.get('where_to_get', 'see docs')}"
            for k in required_keys
        )
        msg = (
            f"*Before I design the architecture, I need these API keys.*\n\n"
            f"{key_lines}\n\n"
            f"Add them to your `.env` file, then reply *ready* to continue."
        )
        await slack.update_message(channel, thinking_ts, msg, "architect")
        await db.add_message(project_id, "agent", msg, persona="architect")

    elif status == "ready":
        await force_arch_design(project_id, channel, thread_ts, thinking_ts)


async def force_arch_design(project_id: str, channel: str, thread_ts: str,
                             thinking_ts: str = None):
    if not thinking_ts:
        thinking_ts = await slack.post_thinking(channel, thread_ts, "architect")
    else:
        await slack.update_message(channel, thinking_ts, "_Designing architecture..._", "architect")

    context = await build_context(project_id, "ARCHITECTURE_ACTIVE", "architect",
                                  user_message="DESIGN_NOW")
    console.skill_invoked("architect")
    result = await run_skill("architect", context)
    console.skill_result("architect", result)
    await process_architect_result(project_id, result, channel, thread_ts, thinking_ts)


async def handle_keys_confirmed(project_id: str, channel: str, thread_ts: str):
    """User confirmed API keys are in .env — verify and proceed to architecture."""
    required_keys = await get_required_keys_from_messages(project_id)
    # Reload .env fresh — user may have just updated it
    load_dotenv(ENV_PATH, override=True)
    env_values = dotenv_values(ENV_PATH)

    # Check which keys are missing or still placeholder
    missing = [
        k for k in required_keys
        if not env_values.get(k) or env_values.get(k, "").startswith("your-")
    ]

    if missing:
        missing_str = ", ".join(f"`{k}`" for k in missing)
        await slack.post_message(channel,
            f":warning: *Heads up:* These keys are not set in `.env`: {missing_str}\n"
            f"The agent will be built but *will not work as expected* without them.\n"
            f"You can add them later and restart the agent.\n\n"
            f"_Proceeding with architecture design..._",
            thread_ts, "architect")
    else:
        await slack.post_message(channel,
            ":white_check_mark: All API keys verified. Designing architecture...",
            thread_ts, "architect")

    await force_arch_design(project_id, channel, thread_ts)


async def get_required_keys_from_messages(project_id: str) -> list:
    """Extract required API key names from the MOST RECENT architect needs_keys message."""
    messages = await db.get_messages(project_id)
    # Walk backwards — first architect message with backtick keys is the latest needs_keys post
    for msg in reversed(messages):
        if msg.get("persona") != "architect":
            continue
        content = msg.get("content", "")
        # Only look at messages that contain the "Add them to your .env" instruction
        if "Add them to your" not in content:
            continue
        keys = re.findall(r"`([A-Z][A-Z0-9_]+_[A-Z0-9_]+|ANTHROPIC_API_KEY|LANGSMITH_API_KEY)`", content)
        # Deduplicate while preserving order
        seen = set()
        unique_keys = [k for k in keys if not (k in seen or seen.add(k))]
        if unique_keys:
            return unique_keys
    return []


# --- Architecture ---

async def process_architect_result(project_id: str, result: dict,
                                    channel: str, thread_ts: str, thinking_ts: str):
    await db.update_state(project_id, ProjectState.ARCHITECTURE_ACTIVE)
    arch_doc = result.get("architecture_doc", {})
    formatted = format_architecture(arch_doc)
    file_path = write_artifact(project_id, "architecture.md", formatted)
    console.artifact_written("architect", file_path)
    await db.save_artifact(project_id, "architect", formatted, file_path)
    git.commit_artifact(project_id, "architect", "architecture design")
    git.push()

    mermaid = arch_doc.get("diagram_mermaid", "")
    if mermaid:
        mp = write_artifact(project_id, "architecture.mermaid", mermaid)
        console.artifact_written("architect", mp)

    summary = build_architecture_summary(arch_doc)
    console.posting_to_slack("architect", summary)
    await slack.update_message(channel, thinking_ts, summary, "architect")
    await db.add_message(project_id, "agent", summary, persona="architect")
    await slack.upload_file(channel, thread_ts, file_path, "Architecture Document")
    console.state_transition("ARCHITECTURE_ACTIVE", "ARCHITECTURE_APPROVAL_PENDING")
    await db.update_state(project_id, ProjectState.ARCHITECTURE_APPROVAL_PENDING)


# --- Agent Implementer ---

async def run_agent_implementer(project_id: str, channel: str,
                                 thread_ts: str, thinking_ts: str):
    console.state_transition("ARCHITECTURE_APPROVAL_PENDING", "AGENT_DESIGN_ACTIVE")
    await db.update_state(project_id, ProjectState.AGENT_DESIGN_ACTIVE)
    try:
        context = await build_context(project_id, "AGENT_DESIGN_ACTIVE", "agent-implementer")
        console.skill_invoked("agent-implementer", prior_artifacts=list(context.prior_artifacts.keys()))
        console.context_summary(context)
        result = await run_skill("agent-implementer", context)
        console.skill_result("agent-implementer", result)

        design = result.get("agent_design", {})
        formatted = format_agent_design(design)
        file_path = write_artifact(project_id, "agent-design.md", formatted)
        console.artifact_written("agent-implementer", file_path)
        await db.save_artifact(project_id, "agent-implementer", formatted, file_path)
        git.commit_artifact(project_id, "agent-implementer", "agent reasoning design")
        git.push()

        summary = build_agent_design_summary(design)
        console.posting_to_slack("agent-implementer", summary)
        await slack.update_message(channel, thinking_ts, summary, "agent-implementer")
        await db.add_message(project_id, "agent", summary, persona="agent-implementer")
        await slack.upload_file(channel, thread_ts, file_path, "Agent Design Document")
        console.state_transition("AGENT_DESIGN_ACTIVE", "AGENT_DESIGN_APPROVAL_PENDING")
        await db.update_state(project_id, ProjectState.AGENT_DESIGN_APPROVAL_PENDING)
    except Exception as e:
        await handle_stage_error(project_id, "agent-implementer", ProjectState.AGENT_DESIGN_ACTIVE,
                                  str(e), channel, thread_ts, thinking_ts)


# --- Implementer ---

async def run_implementer(project_id: str, channel: str, thread_ts: str, thinking_ts: str):
    console.state_transition("AGENT_DESIGN_APPROVAL_PENDING", "IMPLEMENTATION_ACTIVE")
    await db.update_state(project_id, ProjectState.IMPLEMENTATION_ACTIVE)
    from pathlib import Path
    files_created = []
    paths = get_project_paths(project_id)

    try:
        await slack.update_message(channel, thinking_ts,
            "_Reading architecture and planning file structure..._", "implementer")

        plan_context = await build_context(project_id, "IMPLEMENTATION_ACTIVE", "implementer",
                                           user_message="LIST_FILES_ONLY")
        plan_result = await run_skill("implementer", plan_context)
        files_to_generate = plan_result.get("files_to_generate",
            plan_result.get("files_created", [
                "requirements.txt", ".env.example",
                "src/main.py", "src/agent.py", "src/tools.py",
                "demo.py", "tests/test_agent.py"
            ]))

        console.skill_result("implementer", {"status": "planned", "files": files_to_generate})
        await slack.update_message(channel, thinking_ts,
            f"_Implementing {len(files_to_generate)} files..._", "implementer")

        # Track already-written file contents so each subsequent file
        # can read actual exports/classes from previously written files
        written_files: dict = {}

        for file_name in files_to_generate:
            print(f"  Generating: {file_name}", flush=True)
            context = await build_context(
                project_id, "IMPLEMENTATION_ACTIVE", "implementer",
                user_message=file_name,
                known=written_files   # pass all files written so far
            )
            try:
                result = await run_skill("implementer", context)
                content = result.get("content", "")
                rel_path = result.get("file_path", file_name)
                abs_path = Path(paths["workspace_path"]) / rel_path
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content, encoding="utf-8")
                files_created.append(rel_path)
                written_files[rel_path] = content   # add to context for next file
                console.artifact_written("implementer", str(abs_path))
            except Exception as e:
                console.error("implementer", f"Failed to generate {file_name}: {e}")

        report = "# Implementation Report\n\n## Files Created\n" + \
                 "\n".join(f"- {f}" for f in files_created)
        report_path = write_artifact(project_id, "implementation-report.md", report)
        await db.save_artifact(project_id, "implementer", report, report_path)
        git.commit_artifact(project_id, "implementer", f"initial implementation - {len(files_created)} files")
        git.push()

        file_tree = get_file_tree(project_id)
        summary = (f"*Implementation complete.* {len(files_created)} files written.\n\n"
                   f"```\n{file_tree}\n```\n\nRouting to Code Reviewer...")
        console.posting_to_slack("implementer", summary)
        await slack.update_message(channel, thinking_ts, summary, "implementer")
        await db.add_message(project_id, "agent", summary, persona="implementer")
        await route_to_next_stage(project_id, "REVIEW_ACTIVE", "reviewer", channel, thread_ts)
    except Exception as e:
        await handle_stage_error(project_id, "implementer", ProjectState.IMPLEMENTATION_ACTIVE,
                                  str(e), channel, thread_ts, thinking_ts)


# --- Code Reviewer ---

async def run_reviewer(project_id: str, channel: str, thread_ts: str, thinking_ts: str):
    console.state_transition("IMPLEMENTATION_ACTIVE", "REVIEW_ACTIVE")
    await db.update_state(project_id, ProjectState.REVIEW_ACTIVE)
    try:
        context = await build_context(project_id, "REVIEW_ACTIVE", "reviewer")
        console.skill_invoked("reviewer", prior_artifacts=list(context.prior_artifacts.keys()))
        console.context_summary(context)
        result = await run_skill("reviewer", context)
        console.skill_result("reviewer", result)

        formatted = format_review_report(result)
        file_path = write_artifact(project_id, "code-review.md", formatted)
        console.artifact_written("reviewer", file_path)
        await db.save_artifact(project_id, "reviewer", formatted, file_path)
        git.commit_artifact(project_id, "reviewer", f"code review - {result.get('verdict','')}")
        git.push()

        verdict = result.get("verdict", "APPROVED")
        summary = build_review_summary(result)
        console.posting_to_slack("reviewer", summary)
        await slack.update_message(channel, thinking_ts, summary, "reviewer")
        await db.add_message(project_id, "agent", summary, persona="reviewer")
        await slack.upload_file(channel, thread_ts, file_path, "Code Review")

        if verdict == "REJECTED":
            console.routing("implementer", "Review REJECTED -- looping back")
            thinking_ts2 = await slack.post_thinking(channel, thread_ts, "implementer")
            await run_implementer(project_id, channel, thread_ts, thinking_ts2)
        else:
            await route_to_next_stage(project_id, "SECURITY_ACTIVE", "security", channel, thread_ts)
    except Exception as e:
        await handle_stage_error(project_id, "reviewer", ProjectState.REVIEW_ACTIVE,
                                  str(e), channel, thread_ts, thinking_ts)


# --- Security Audit (post-implementation) ---

async def run_security(project_id: str, channel: str, thread_ts: str, thinking_ts: str):
    console.state_transition("REVIEW_ACTIVE", "SECURITY_ACTIVE")
    await db.update_state(project_id, ProjectState.SECURITY_ACTIVE)
    try:
        context = await build_context(project_id, "SECURITY_ACTIVE", "security")
        console.skill_invoked("security", prior_artifacts=list(context.prior_artifacts.keys()))
        console.context_summary(context)
        result = await run_skill("security", context)
        console.skill_result("security", result)

        formatted = format_security_report(result)
        file_path = write_artifact(project_id, "security-audit.md", formatted)
        console.artifact_written("security", file_path)
        await db.save_artifact(project_id, "security", formatted, file_path)
        await db.approve_artifact(project_id, "security")
        git.commit_artifact(project_id, "security",
                            f"security audit - {len(result.get('findings',[]))} findings")
        git.push()

        summary = build_security_summary(result)
        console.posting_to_slack("security", summary)
        await slack.update_message(channel, thinking_ts, summary, "security")
        await db.add_message(project_id, "agent", summary, persona="security")
        await slack.upload_file(channel, thread_ts, file_path, "Security Audit")

        # Security is advisory after implementation — always proceed to testing
        await route_to_next_stage(project_id, "TESTING_ACTIVE", "tester", channel, thread_ts)
    except Exception as e:
        await handle_stage_error(project_id, "security", ProjectState.SECURITY_ACTIVE,
                                  str(e), channel, thread_ts, thinking_ts)


# --- Tester with LangSmith evals ---

async def run_tester(project_id: str, channel: str, thread_ts: str, thinking_ts: str):
    console.state_transition("SECURITY_ACTIVE", "TESTING_ACTIVE")
    await db.update_state(project_id, ProjectState.TESTING_ACTIVE)
    try:
        context = await build_context(project_id, "TESTING_ACTIVE", "tester")
        console.skill_invoked("tester", prior_artifacts=list(context.prior_artifacts.keys()))
        console.context_summary(context)
        result = await run_skill("tester", context)
        console.skill_result("tester", result)

        # Write eval file to workspace
        eval_content = result.get("eval_content", "")
        paths = get_project_paths(project_id)
        if eval_content:
            eval_path = Path(paths["workspace_path"]) / "evals" / "run_evals.py"
            eval_path.parent.mkdir(parents=True, exist_ok=True)
            eval_path.write_text(eval_content, encoding="utf-8")
            console.artifact_written("tester", str(eval_path))

        formatted = format_test_report(result)
        file_path = write_artifact(project_id, "test-plan.md", formatted)
        console.artifact_written("tester", file_path)
        await db.save_artifact(project_id, "tester", formatted, file_path)
        git.commit_artifact(project_id, "tester", f"evals and test plan - {result.get('verdict','')}")
        git.push()

        verdict = result.get("verdict", "PASS")
        summary = build_test_summary(result)
        console.posting_to_slack("tester", summary)
        await slack.update_message(channel, thinking_ts, summary, "tester")
        await db.add_message(project_id, "agent", summary, persona="tester")
        await slack.upload_file(channel, thread_ts, file_path, "Test Plan & Evals")

        # Run evals if file was created
        if eval_content:
            await run_evals(project_id, channel, thread_ts, paths["workspace_path"])

        if verdict == "FAIL":
            blocking_gaps = result.get("blocking_gaps", [])
            gap_text = "\n".join(f"- {g}" for g in blocking_gaps)
            console.routing("implementer", f"Tests FAILED -- {len(blocking_gaps)} blocking gaps")
            await slack.post_message(channel,
                f"Failing gaps found. Routing back to Implementer.\n{gap_text}",
                thread_ts, "tester")
            thinking_ts2 = await slack.post_thinking(channel, thread_ts, "implementer")
            await run_implementer(project_id, channel, thread_ts, thinking_ts2)
        else:
            await route_to_next_stage(project_id, "DEVOPS_ACTIVE", "devops", channel, thread_ts)
    except Exception as e:
        await handle_stage_error(project_id, "tester", ProjectState.TESTING_ACTIVE,
                                  str(e), channel, thread_ts, thinking_ts)


async def run_evals(project_id: str, channel: str, thread_ts: str, workspace_path: str):
    eval_file = Path(workspace_path) / "evals" / "run_evals.py"
    if not eval_file.exists():
        return

    await slack.post_message(channel, "_Running LangSmith evals..._", thread_ts, "tester")
    print(f"  Running evals: {eval_file}", flush=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", str(eval_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_path,
            env={**os.environ},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        output = stdout.decode("utf-8", errors="replace").strip()
        errors = stderr.decode("utf-8", errors="replace").strip()

        if output:
            if len(output) > 2500:
                output = output[:2500] + "\n... (truncated)"
            await slack.post_message(channel,
                f":test_tube: *Eval Results:*\n```\n{output}\n```",
                thread_ts, "tester")
        if errors and proc.returncode != 0:
            await slack.post_message(channel,
                f":warning: Eval errors:\n```\n{errors[:600]}\n```",
                thread_ts, "tester")
    except asyncio.TimeoutError:
        await slack.post_message(channel, "_Evals timed out._", thread_ts, "tester")
    except Exception as e:
        await slack.post_message(channel, f"_Evals failed: {e}_", thread_ts, "tester")


# --- DevOps ---

async def run_devops(project_id: str, channel: str, thread_ts: str, thinking_ts: str):
    console.state_transition("TESTING_ACTIVE", "DEVOPS_ACTIVE")
    await db.update_state(project_id, ProjectState.DEVOPS_ACTIVE)
    try:
        context = await build_context(project_id, "DEVOPS_ACTIVE", "devops")
        console.skill_invoked("devops", prior_artifacts=list(context.prior_artifacts.keys()))
        console.context_summary(context)
        result = await run_skill("devops", context)
        console.skill_result("devops", result)

        start_command = result.get("start_command", "")
        url = result.get("url", "")
        port = result.get("port", 8000)
        env_vars = result.get("env_vars_required", [])
        setup_steps = result.get("setup_steps", [])
        health_path = result.get("health_check_path", "/health")

        paths = get_project_paths(project_id)
        workspace = paths["workspace_path"]

        # Post setup instructions first
        env_check = "\n".join(f"• `{k}`" for k in env_vars[:8])
        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(setup_steps))
        await slack.update_message(channel, thinking_ts,
            f"*DevOps preparing deployment...*\n\n"
            f"Required env vars:\n{env_check}\n\n"
            f"Setup:\n{steps_text}\n\n"
            f"_Installing dependencies and starting agent..._",
            "devops")

        # Execute start command
        if start_command:
            await execute_start_command(project_id, start_command, workspace,
                                         url, port, health_path, channel, thread_ts)
        else:
            await slack.post_message(channel,
                ":warning: No start command determined. Check architecture docs.",
                thread_ts, "devops")

        # Show git log
        log = git.get_log(8)
        await slack.post_message(channel,
            f"*Git history for this project:*\n```\n{log}\n```",
            thread_ts, "ba")

        console.state_transition("DEVOPS_ACTIVE", "COMPLETE")
        await db.update_state(project_id, ProjectState.COMPLETE)
        project = await db.get_project(project_id)
        project_name = project.get("name", project_id)
        console.pipeline_complete(project_id, workspace)

        await slack.post_message(channel,
            f":checkered_flag: *{project_name} — Pipeline Complete*\n\n"
            f"All 8 stages complete. Agent is live at: *{url}*\n"
            f"Workspace: `{workspace}`",
            thread_ts, "ba")
    except Exception as e:
        await handle_stage_error(project_id, "devops", ProjectState.DEVOPS_ACTIVE,
                                  str(e), channel, thread_ts, thinking_ts)


async def execute_start_command(project_id: str, command: str, workspace: str,
                                  url: str, port: int, health_path: str,
                                  channel: str, thread_ts: str):
    """Run the start command in the workspace, wait for health check, post URL."""
    import subprocess
    print(f"  Starting agent: {command}", flush=True)

    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait up to 30 seconds for health check
        import aiohttp
        health_url = f"http://localhost:{port}{health_path}"
        started = False
        for _ in range(15):
            await asyncio.sleep(2)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        if resp.status == 200:
                            started = True
                            break
            except Exception:
                continue

        if started:
            await slack.post_message(channel,
                f":rocket: *Agent is live!*\n\n"
                f"Open in your browser: *{url}*\n"
                f"Health check: `{health_url}` - OK",
                thread_ts, "devops")
        else:
            await slack.post_message(channel,
                f":warning: Agent started but health check did not respond at `{health_url}`.\n"
                f"Check the terminal for errors. The process is running with PID {proc.pid}.",
                thread_ts, "devops")

    except Exception as e:
        await slack.post_message(channel,
            f":warning: Could not start agent: `{e}`\n"
            f"Run manually: `cd {workspace} && {command}`",
            thread_ts, "devops")


# --- Routing and error handling ---

async def route_to_next_stage(project_id: str, next_stage: str,
                               persona: str, channel: str, thread_ts: str):
    console.routing(persona, f"Auto-routing to {next_stage}")
    thinking_ts = await slack.post_thinking(channel, thread_ts, persona)

    try:
        if next_stage == "ARCH_DISCOVERY_ACTIVE":
            await run_arch_discovery(project_id, channel, thread_ts)
        elif next_stage == "AGENT_DESIGN_ACTIVE":
            await run_agent_implementer(project_id, channel, thread_ts, thinking_ts)
        elif next_stage == "IMPLEMENTATION_ACTIVE":
            await run_implementer(project_id, channel, thread_ts, thinking_ts)
        elif next_stage == "REVIEW_ACTIVE":
            await run_reviewer(project_id, channel, thread_ts, thinking_ts)
        elif next_stage == "SECURITY_ACTIVE":
            await run_security(project_id, channel, thread_ts, thinking_ts)
        elif next_stage == "TESTING_ACTIVE":
            await run_tester(project_id, channel, thread_ts, thinking_ts)
        elif next_stage == "DEVOPS_ACTIVE":
            await run_devops(project_id, channel, thread_ts, thinking_ts)
    except Exception as e:
        console.error(next_stage, str(e))
        await slack.update_message(channel, thinking_ts,
                                    f"Error in {next_stage}: {e}", persona)


async def rerun_with_feedback(project_id: str, stage: str, persona: str,
                               feedback: str, channel: str, thread_ts: str):
    await db.add_message(project_id, "user", f"[Changes requested]: {feedback}")
    thinking_ts = await slack.post_thinking(channel, thread_ts, persona)
    context = await build_context(project_id, stage, persona, user_message=feedback)
    console.skill_invoked(persona)
    console.context_summary(context)
    result = await run_skill(persona, context)
    console.skill_result(persona, result)

    if persona == "ba":
        await process_ba_result(project_id, result, channel, thread_ts, thinking_ts, turn=0)
    elif persona == "architect":
        await process_architect_result(project_id, result, channel, thread_ts, thinking_ts)
    elif persona == "agent-implementer":
        design = result.get("agent_design", {})
        formatted = format_agent_design(design)
        file_path = write_artifact(project_id, "agent-design.md", formatted)
        await db.save_artifact(project_id, "agent-implementer", formatted, file_path)
        summary = build_agent_design_summary(design)
        await slack.update_message(channel, thinking_ts, summary, "agent-implementer")
        await db.update_state(project_id, ProjectState.AGENT_DESIGN_APPROVAL_PENDING)


async def handle_stage_error(project_id: str, stage: str, current_state: ProjectState,
                              error: str, channel: str, thread_ts: str,
                              thinking_ts: str = None):
    console.error(stage, error)
    await db.block_project(project_id, f"{stage}: {error}")
    msg = (
        f":warning: *{stage.upper()} failed* — pipeline paused.\n\n"
        f"Error: `{error[:200]}`\n\n"
        f"Reply *resume* to retry, or *changes* + feedback to adjust."
    )
    if thinking_ts:
        await slack.update_message(channel, thinking_ts, msg, stage)
    else:
        await slack.post_message(channel, msg, thread_ts, stage)


async def handle_resume(project_id: str, current_state: str, channel: str, thread_ts: str):
    from .state import RESUME_MAP, RESUME_STATE_FROM_ARTIFACT, RESUME_PERSONA_FROM_ARTIFACT

    state = ProjectState(current_state)

    if state == ProjectState.BLOCKED:
        artifacts = await db.get_all_artifacts(project_id)
        approved = list(artifacts.keys())
        stage_order = ["ba", "architect", "agent-implementer", "implementer",
                       "reviewer", "security", "tester"]
        last_approved = None
        for s in stage_order:
            if s in approved:
                last_approved = s

        resume_state = RESUME_STATE_FROM_ARTIFACT.get(last_approved, ProjectState.DISCOVERY_ACTIVE)
        resume_persona = RESUME_PERSONA_FROM_ARTIFACT.get(last_approved, "ba")
        await db.update_state(project_id, resume_state)
        state = resume_state
    else:
        resume_persona = RESUME_MAP.get(state, "ba")

    console.routing(resume_persona, f"Resume from {state}")
    thinking_ts = await slack.post_thinking(channel, thread_ts, resume_persona)
    await slack.update_message(channel, thinking_ts,
        f"_Resuming from {state.value}..._", resume_persona)

    try:
        await route_to_next_stage(project_id, state.value, resume_persona, channel, thread_ts)
    except Exception as e:
        await handle_stage_error(project_id, resume_persona, state,
                                  str(e), channel, thread_ts, thinking_ts)


# --- Formatters ---

def format_requirements(doc: dict) -> str:
    lines = ["# Requirements Document\n"]
    lines.append(f"## Problem Statement\n{doc.get('problem_statement', '')}\n")
    lines.append("## Users\n" + "\n".join(f"- {u}" for u in doc.get("users", [])) + "\n")
    lines.append("## Functional Requirements\n" + "\n".join(f"- {r}" for r in doc.get("functional_requirements", [])) + "\n")
    lines.append("## Non-Functional Requirements\n" + "\n".join(f"- {r}" for r in doc.get("non_functional_requirements", [])) + "\n")
    lines.append("## Acceptance Criteria\n" + "\n".join(f"- {c}" for c in doc.get("acceptance_criteria", [])) + "\n")
    lines.append("## Out of Scope\n" + "\n".join(f"- {o}" for o in doc.get("out_of_scope", [])) + "\n")
    return "\n".join(lines)


def build_requirements_summary(doc: dict) -> str:
    reqs = "\n".join(f"- {r}" for r in doc.get("functional_requirements", []))
    oos = "\n".join(f"- {o}" for o in doc.get("out_of_scope", []))
    return (
        f"*Requirements captured.*\n\n"
        f"*Problem:* {doc.get('problem_statement', '')}\n\n"
        f"*What it does:*\n{reqs}\n\n"
        f"*Out of scope:*\n{oos}\n\n"
        f"Full document attached.\n"
        f"Reply *approved* to proceed to architecture  |  *changes* + feedback to revise"
    )


def format_architecture(doc: dict) -> str:
    lines = ["# Architecture Document\n"]
    lines.append("## Components\n" + "\n".join(f"- {c}" for c in doc.get("components", [])) + "\n")
    stack = doc.get("tech_stack", {})
    lines.append("## Tech Stack\n" + "\n".join(f"- **{k}**: {v}" for k, v in stack.items()) + "\n")
    lines.append(f"## Data Flow\n{doc.get('data_flow', '')}\n")
    lines.append(f"## Deployment\n{doc.get('deployment', '')}\n")
    mermaid = doc.get("diagram_mermaid", "")
    if mermaid:
        lines.append(f"## Diagram\n```mermaid\n{mermaid}\n```\n")
    return "\n".join(lines)


def build_architecture_summary(doc: dict) -> str:
    stack = doc.get("tech_stack", {})
    stack_text = ", ".join(f"{k}: {v}" for k, v in list(stack.items())[:4])
    risks = "\n".join(f"- {r}" for r in doc.get("open_risks", [])[:3])
    return (
        f"*Architecture designed.*\n\n"
        f"*Stack:* {stack_text}\n\n"
        f"*Open risks:*\n{risks}\n\n"
        f"Full document + Mermaid diagram attached.\n"
        f"Reply *approved* to proceed to agent design  |  *changes* + feedback to revise"
    )


def format_agent_design(design: dict) -> str:
    lines = ["# Agent Design Document\n"]
    lines.append(f"## Reasoning Strategy\n{design.get('reasoning_strategy', '')}\n")
    tools = design.get("tools", [])
    if tools:
        lines.append("## Tools\n")
        for t in tools:
            lines.append(f"### {t.get('name', '')}\n- Purpose: {t.get('purpose', '')}\n- Input: {t.get('input', '')}\n- Output: {t.get('output', '')}\n")
    lines.append(f"## Memory Strategy\n{design.get('memory_strategy', '')}\n")
    lines.append(f"## Prompt Architecture\n{design.get('prompt_architecture', '')}\n")
    lines.append("## Failure Modes\n" + "\n".join(f"- {f}" for f in design.get("failure_modes", [])) + "\n")
    lines.append("## Guardrails\n" + "\n".join(f"- {g}" for g in design.get("guardrails", [])) + "\n")
    return "\n".join(lines)


def build_agent_design_summary(design: dict) -> str:
    tools = design.get("tools", [])
    tool_names = ", ".join(t.get("name", "") for t in tools[:4])
    return (
        f"*Agent design complete.*\n\n"
        f"*Reasoning:* {design.get('reasoning_strategy', '')[:100]}\n"
        f"*Tools:* {tool_names}\n"
        f"*Memory:* {design.get('memory_strategy', '')}\n\n"
        f"Full design document attached.\n"
        f"Reply *approved* to proceed to implementation  |  *changes* + feedback to revise"
    )


def format_security_report(result: dict) -> str:
    lines = ["# Security Audit\n"]
    audited = result.get("files_audited", [])
    if audited:
        lines.append("## Files Audited\n" + "\n".join(f"- {f}" for f in audited) + "\n")
    for f in result.get("findings", []):
        lines.append(f"## [{f.get('severity')}] {f.get('file','')}: {f.get('category','')}\n"
                     f"{f.get('description','')}\n**Fix:** {f.get('recommendation','')}\n")
    warnings = result.get("deployment_warnings", [])
    if warnings:
        lines.append("## Deployment Warnings\n" + "\n".join(f"- {w}" for w in warnings) + "\n")
    return "\n".join(lines)


def build_security_summary(result: dict) -> str:
    findings = result.get("findings", [])
    high = [f for f in findings if f.get("severity") == "HIGH"]
    advisory = result.get("advisory_issues", [])
    finding_lines = "\n".join(
        f"- *[{f.get('severity')}]* `{f.get('file','')}`: {f.get('description','')[:80]}"
        for f in findings[:5]
    )
    return (
        f"*Security audit complete.*\n\n"
        f"Total: {len(findings)}  |  HIGH: {len(high)}  |  Advisory: {len(advisory)}\n\n"
        f"{finding_lines}"
    )


def format_review_report(result: dict) -> str:
    lines = [f"# Code Review - {result.get('verdict', '')}\n"]
    lines.append(f"## Summary\n{result.get('summary', '')}\n")
    for f in result.get("findings", []):
        lines.append(f"## [{f.get('severity')}] {f.get('file')} {f.get('line', '')}\n"
                     f"{f.get('issue')}\n**Fix:** {f.get('recommendation')}\n")
    return "\n".join(lines)


def build_review_summary(result: dict) -> str:
    verdict = result.get("verdict", "")
    findings = result.get("findings", [])
    blocking = [f for f in findings if f.get("severity") == "BLOCKING"]
    emoji = ":white_check_mark:" if verdict == "APPROVED" else ":x:" if verdict == "REJECTED" else ":warning:"
    return (
        f"{emoji} *Code Review: {verdict}*\n\n"
        f"{result.get('summary', '')}\n\n"
        f"Findings: {len(findings)}  |  Blocking: {len(blocking)}"
    )


def format_test_report(result: dict) -> str:
    lines = [f"# Test Plan & Evals - {result.get('verdict', '')}\n"]
    cases = result.get("eval_cases", [])
    if cases:
        lines.append("## Eval Cases\n")
        for c in cases:
            lines.append(f"- **{c.get('name')}**: {c.get('input','')[:60]} -> {c.get('expected_behavior','')[:60]}\n")
    gaps = result.get("gap_analysis", [])
    if gaps:
        lines.append("## Gap Analysis\n" + "\n".join(f"- {g}" for g in gaps) + "\n")
    return "\n".join(lines)


def build_test_summary(result: dict) -> str:
    verdict = result.get("verdict", "")
    cases = result.get("eval_cases", [])
    blocking = result.get("blocking_gaps", [])
    emoji = ":white_check_mark:" if verdict == "PASS" else ":warning:" if verdict == "PASS_WITH_WARNINGS" else ":x:"
    return (
        f"{emoji} *Testing: {verdict}*\n\n"
        f"Eval cases: {len(cases)}  |  Blocking gaps: {len(blocking)}\n"
        f"Eval file: `evals/run_evals.py`"
    )
