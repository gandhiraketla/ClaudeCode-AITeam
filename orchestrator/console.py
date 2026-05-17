"""
Clean console output for ClaudeForge demo.
Every print goes through here so the terminal tells a readable story.
ASCII-only to avoid Windows cp1252 encoding errors.
"""
import json
import sys
from datetime import datetime

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ANSI colors
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
MAGENTA = "\033[35m"
BLUE    = "\033[34m"
WHITE   = "\033[97m"

PERSONA_COLORS = {
    "ba":                CYAN,
    "architect":         BLUE,
    "agent-implementer": MAGENTA,
    "security":          RED,
    "implementer":       GREEN,
    "reviewer":          YELLOW,
    "tester":            MAGENTA,
}

PERSONA_LABELS = {
    "ba":                "Business Analyst",
    "architect":         "Solution Architect",
    "agent-implementer": "Agent Implementer",
    "security":          "Security Reviewer",
    "implementer":       "Implementer",
    "reviewer":          "Code Reviewer",
    "tester":            "Tester",
}


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _line(char="-", width=60) -> str:
    return char * width


def banner():
    print(f"\n{BOLD}{CYAN}{_line('=')}{RESET}")
    print(f"{BOLD}{CYAN}  ClaudeForge - AI Engineering Team{RESET}")
    print(f"{BOLD}{CYAN}  HTTP Mode | Ready for messages{RESET}")
    print(f"{BOLD}{CYAN}{_line('=')}{RESET}\n", flush=True)


def section(title: str):
    print(f"\n{BOLD}{WHITE}{_line()}{RESET}")
    print(f"{BOLD}{WHITE}  {title}{RESET}")
    print(f"{BOLD}{WHITE}{_line()}{RESET}")


def event_received(user: str, text: str, is_thread: bool):
    kind = "THREAD REPLY" if is_thread else "NEW MESSAGE"
    print(f"\n{BOLD}[{_ts()}] SLACK EVENT - {kind}{RESET}")
    print(f"  {DIM}User   :{RESET} {user}")
    print(f"  {DIM}Text   :{RESET} {text[:120]}", flush=True)


def routing(persona: str, reason: str):
    color = PERSONA_COLORS.get(persona, WHITE)
    label = PERSONA_LABELS.get(persona, persona)
    print(f"\n{BOLD}[{_ts()}] ROUTING -> {color}{label.upper()}{RESET}")
    print(f"  {DIM}Reason :{RESET} {reason}", flush=True)


def project_created(project_id: str, workspace_path: str):
    print(f"\n{BOLD}[{_ts()}] PROJECT CREATED{RESET}")
    print(f"  {DIM}ID        :{RESET} {project_id}")
    print(f"  {DIM}Workspace :{RESET} {workspace_path}", flush=True)


def state_transition(from_state: str, to_state: str):
    print(f"\n{BOLD}[{_ts()}] STATE{RESET}  {DIM}{from_state}{RESET}  ->  {BOLD}{to_state}{RESET}", flush=True)


def skill_invoked(skill: str, turn: int = None, prior_artifacts: list = None):
    color = PERSONA_COLORS.get(skill, WHITE)
    label = PERSONA_LABELS.get(skill, skill)
    turn_str = f"  turn {turn}" if turn else ""
    print(f"\n{BOLD}[{_ts()}] SKILL INVOKED - {color}{label.upper()}{RESET}{DIM}{turn_str}{RESET}")
    if prior_artifacts:
        print(f"  {DIM}Context includes:{RESET} {', '.join(prior_artifacts)}", flush=True)


def context_summary(context):
    print(f"  {DIM}{_line('-', 50)}{RESET}")
    print(f"  {BOLD}Context passed to skill:{RESET}")
    print(f"    {DIM}project_id     :{RESET} {context.project_id}")
    print(f"    {DIM}stage          :{RESET} {context.stage}")
    print(f"    {DIM}turn           :{RESET} {context.turn}")
    print(f"    {DIM}history msgs   :{RESET} {len(context.conversation_history)}")
    if context.prior_artifacts:
        print(f"    {DIM}prior artifacts:{RESET} {', '.join(context.prior_artifacts.keys())}")
    if context.known:
        known_preview = json.dumps(context.known, indent=None)[:120]
        print(f"    {DIM}known so far   :{RESET} {known_preview}")
    if context.missing:
        print(f"    {DIM}still missing  :{RESET} {', '.join(context.missing[:6])}")
    print(f"    {DIM}artifacts_path :{RESET} {context.artifacts_path}")
    print(f"  {DIM}{_line('-', 50)}{RESET}", flush=True)


def skill_result(skill: str, result: dict):
    color = PERSONA_COLORS.get(skill, WHITE)
    label = PERSONA_LABELS.get(skill, skill)
    status = result.get("status", result.get("verdict", "complete"))
    print(f"\n{BOLD}[{_ts()}] SKILL RESULT - {color}{label.upper()}{RESET}")
    print(f"  {DIM}Status  :{RESET} {BOLD}{status}{RESET}")

    if skill == "ba":
        if status == "asking":
            q = result.get("question", "")
            print(f"  {DIM}Question:{RESET} {q[:120]}")
            missing = result.get("missing", [])
            if missing:
                print(f"  {DIM}Missing :{RESET} {', '.join(missing[:6])}")
        elif status == "ready":
            doc = result.get("requirements_doc", {})
            reqs = doc.get("functional_requirements", [])
            print(f"  {DIM}Requirements captured:{RESET} {len(reqs)} functional")
            print(f"  {DIM}Out of scope         :{RESET} {len(doc.get('out_of_scope', []))}")

    elif skill == "architect":
        doc = result.get("architecture_doc", {})
        stack = doc.get("tech_stack", {})
        print(f"  {DIM}Components:{RESET} {len(doc.get('components', []))}")
        print(f"  {DIM}Tech stack:{RESET} {', '.join(list(stack.keys())[:4])}")
        print(f"  {DIM}Risks     :{RESET} {len(result.get('open_risks', []))}")

    elif skill == "agent-implementer":
        design = result.get("agent_design", {})
        tools = design.get("tools", [])
        print(f"  {DIM}Strategy:{RESET} {design.get('reasoning_strategy', '')[:80]}")
        print(f"  {DIM}Tools   :{RESET} {', '.join(t.get('name','') for t in tools[:5])}")

    elif skill == "security":
        findings = result.get("findings", [])
        blocking = result.get("blocking_issues", [])
        advisory = result.get("advisory_issues", [])
        print(f"  {DIM}Total findings:{RESET} {len(findings)}  Blocking: {len(blocking)}  Advisory: {len(advisory)}")
        for f in findings[:3]:
            sev_color = RED if f.get("severity") == "HIGH" else YELLOW
            print(f"    {sev_color}[{f.get('severity')}]{RESET} {f.get('category')}: {f.get('description','')[:80]}")

    elif skill == "implementer":
        files = result.get("files_created", [])
        gaps = result.get("known_gaps", [])
        print(f"  {DIM}Files created:{RESET} {len(files)}")
        for f in files[:8]:
            print(f"    + {f}")
        if gaps:
            print(f"  {DIM}Known gaps   :{RESET} {len(gaps)}")

    elif skill == "reviewer":
        findings = result.get("findings", [])
        blocking = [f for f in findings if f.get("severity") == "BLOCKING"]
        print(f"  {DIM}Verdict  :{RESET} {BOLD}{result.get('verdict','')}{RESET}")
        print(f"  {DIM}Findings :{RESET} {len(findings)}  Blocking: {len(blocking)}")
        print(f"  {DIM}Summary  :{RESET} {result.get('summary','')[:120]}")

    elif skill == "tester":
        plan = result.get("test_plan", {})
        total = sum(len(v) for v in plan.values())
        gaps = result.get("blocking_gaps", [])
        print(f"  {DIM}Verdict    :{RESET} {BOLD}{result.get('verdict','')}{RESET}")
        print(f"  {DIM}Test cases :{RESET} {total}")
        print(f"  {DIM}Blocking   :{RESET} {len(gaps)}")

    print("", flush=True)


def approval_received(approved: bool, feedback: str = ""):
    if approved:
        print(f"\n{BOLD}[{_ts()}] {GREEN}APPROVED{RESET} - proceeding to next stage", flush=True)
    else:
        print(f"\n{BOLD}[{_ts()}] {YELLOW}CHANGES REQUESTED{RESET}")
        if feedback:
            print(f"  {DIM}Feedback:{RESET} {feedback[:120]}", flush=True)


def artifact_written(stage: str, file_path: str):
    print(f"  Artifact written: {file_path}", flush=True)


def posting_to_slack(persona: str, preview: str):
    color = PERSONA_COLORS.get(persona, WHITE)
    label = PERSONA_LABELS.get(persona, persona)
    print(f"\n{BOLD}[{_ts()}] POSTING TO SLACK - {color}{label}{RESET}")
    print(f"  {DIM}Preview:{RESET} {preview[:120].strip()}...", flush=True)


def pipeline_complete(project_id: str, workspace_path: str):
    print(f"\n{BOLD}{GREEN}{_line('=')}{RESET}")
    print(f"{BOLD}{GREEN}  PIPELINE COMPLETE{RESET}")
    print(f"{BOLD}{GREEN}  Project  : {project_id}{RESET}")
    print(f"{BOLD}{GREEN}  Workspace: {workspace_path}{RESET}")
    print(f"{BOLD}{GREEN}{_line('=')}{RESET}\n", flush=True)


def error(stage: str, message: str):
    print(f"\n{BOLD}[{_ts()}] {RED}ERROR in {stage.upper()}{RESET}")
    print(f"  {message}", flush=True)
