# ClaudeForge

**An AI Engineering Team built with Claude.**

ClaudeForge turns a single Slack message into a fully built, tested, and deployed web application — by running a team of specialized AI agents that collaborate, review each other's work, and commit every artifact to Git.

---

## What It Does

You type one message in Slack. ClaudeForge assembles an AI engineering team that:

1. Asks clarifying questions to understand what you want to build
2. Designs the system architecture
3. Plans how the AI agent inside the app should reason
4. Builds the code file by file
5. Reviews the code for quality
6. Audits it for security vulnerabilities
7. Writes and runs evaluations using LangSmith
8. Deploys it locally and posts the live URL back to Slack

Every stage commits its artifacts to Git. By the end, your repo has a complete audit trail of every decision made.

---

## Demo

**Start a project by posting in Slack:**

```
@Business-Analyst I want to build a CSV Insights Generator web app
```

**What you see in Slack:**

```
Business Analyst:   "What types of insights matter most to your users?"
You:                "Trends, anomalies, and a plain-English summary"
Business Analyst:   "Got it. Requirements captured. Reply approved to proceed."
You:                approved

Solution Architect: "Do you have a UI preference? Streamlit, React, or HTML?"
You:                "Streamlit"
Solution Architect: "Architecture designed. Mermaid diagram attached."
You:                approved

Agent Implementer:  "Agent reasoning design complete. ReAct strategy with 3 tools."
You:                approved

Implementer:        "7 files written. Routing to Code Reviewer..."
Code Reviewer:      "APPROVED WITH CHANGES. 2 suggestions noted."
Security Reviewer:  "4 findings. 0 blocking. 4 advisory."
Tester:             "Evals written and executed. PASS."
DevOps:             "Agent is live at http://localhost:8501"
```

**What you see in Git:**

```
feat(ba):               requirements document
feat(architect):        architecture design
feat(agent-implementer):agent reasoning design
feat(implementer):      initial implementation - 7 files
feat(reviewer):         code review - APPROVED_WITH_CHANGES
feat(security):         security audit - 4 findings
feat(tester):           evals and test plan - PASS
```

---

## Architecture

```
Slack
  |
  | @mention or thread reply
  v
FastAPI Orchestrator  (localhost:8000)
  |
  | HTTP POST via ngrok tunnel
  |
  +-- State Machine (SQLite)
  |     DISCOVERY -> ARCH_DISCOVERY -> ARCHITECTURE -> AGENT_DESIGN
  |     -> IMPLEMENTATION -> REVIEW -> SECURITY -> TESTING -> DEVOPS -> COMPLETE
  |
  +-- Skill Runner (Anthropic SDK)
  |     Loads .claude/skills/<persona>.md as system prompt
  |     Passes full context JSON as user message
  |     Returns structured JSON output
  |
  +-- Workspace Manager
  |     workspace/{project_id}/
  |       artifacts/    <- requirements.md, architecture.md, ...
  |       src/          <- generated application code
  |       evals/        <- LangSmith evaluation scripts
  |       tests/        <- test stubs
  |
  +-- Git Helper
        Commits and pushes after every stage
```

### Component Breakdown

| File | Responsibility |
|------|---------------|
| `orchestrator/main.py` | FastAPI app, Slack event handler, full pipeline wiring |
| `orchestrator/state.py` | SQLite state machine — project lifecycle and artifacts |
| `orchestrator/skill_runner.py` | Invokes Claude with skill prompt + context |
| `orchestrator/context_builder.py` | Assembles context JSON passed to each skill |
| `orchestrator/router.py` | Parses `@mentions`, detects approvals |
| `orchestrator/approval_handler.py` | Routes approved/changes responses |
| `orchestrator/slack_client.py` | Persona-aware Slack posting |
| `orchestrator/workspace_manager.py` | Creates and manages project workspace on disk |
| `orchestrator/git_helper.py` | Commits and pushes artifacts after each stage |
| `orchestrator/console.py` | Clean color-coded terminal output for demo |

---

## The 8 AI Personas

Each persona is a markdown file in `.claude/skills/`. It defines the cognitive mode, output contract, and rules for that role.

| Persona | Skill File | What It Does |
|---------|-----------|-------------|
| Business Analyst | `ba.md` | Discovery loop — asks focused questions until requirements are complete |
| Solution Architect | `architect.md` | Technical discovery + system design + Mermaid diagram |
| Agent Implementer | `agent-implementer.md` | Designs agent reasoning strategy, tools, and memory |
| Implementer | `implementer.md` | Generates code file by file in dependency order |
| Code Reviewer | `reviewer.md` | Audits code quality and alignment with architecture |
| Security Reviewer | `security.md` | Audits actual generated code for OWASP vulnerabilities |
| Tester | `tester.md` | Writes and executes LangSmith evaluations |
| DevOps | `devops.md` | Installs deps, starts the app, posts the live URL |

---

## Pipeline State Machine

```
IDLE
  | @Business-Analyst <request>
  v
DISCOVERY_ACTIVE          <- BA asks questions
DISCOVERY_WAITING         <- waiting for user reply
DISCOVERY_APPROVAL_PENDING <- BA posts requirements, awaits approved
  |
  v
ARCH_DISCOVERY_ACTIVE     <- Architect asks technical questions
ARCH_WAITING_FOR_KEYS     <- Architect lists required API keys
ARCHITECTURE_ACTIVE       <- Architect designs system
ARCHITECTURE_APPROVAL_PENDING <- awaits approved
  |
  v
AGENT_DESIGN_ACTIVE       <- Agent Implementer designs reasoning
AGENT_DESIGN_APPROVAL_PENDING <- awaits approved
  |
  v
IMPLEMENTATION_ACTIVE     <- Implementer writes code
  |
  v
REVIEW_ACTIVE             <- Code Reviewer audits
  |
  v
SECURITY_ACTIVE           <- Security Reviewer audits actual code
  |
  v
TESTING_ACTIVE            <- Tester writes + runs evals
  |
  v
DEVOPS_ACTIVE             <- DevOps starts the app
  |
  v
COMPLETE
```

**Approval gates** (require user to type `approved`): Requirements, Architecture, Agent Design

**Automatic stages** (no user input): Implementation, Review, Security, Testing, DevOps

**Recovery**: Type `resume` in any thread to retry a failed stage. Type `changes` + feedback at any approval gate to loop back.

---

## Project Workspace Structure

Every project gets its own directory:

```
workspace/
  {project-name}/
    artifacts/
      requirements.md          <- BA output
      architecture.md          <- Architect output
      architecture.mermaid     <- Mermaid diagram
      agent-design.md          <- Agent Implementer output
      security-audit.md        <- Security Reviewer output
      code-review.md           <- Code Reviewer output
      test-plan.md             <- Tester output
      implementation-report.md <- Implementer output
    src/                       <- Generated application code
    evals/
      run_evals.py             <- LangSmith evaluation script
    tests/                     <- Test stubs
    requirements.txt
    .env.example
    demo.py                    <- Standalone demo runner
```

---

## Local Setup

### Prerequisites

- Python 3.12+
- [ngrok](https://ngrok.com) account and CLI installed
- Slack workspace (admin access to create apps)
- Anthropic API key

### 1. Clone and install

```powershell
git clone <repo>
cd ClaudeCode-AITeam
pip install -r requirements.txt
```

### 2. Configure environment

```powershell
cp .env.example .env
```

Edit `.env`:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...        # only needed for Socket Mode
SLACK_CHANNEL_ID=C...
ANTHROPIC_API_KEY=sk-ant-...
WORKSPACE_BASE_PATH=C:/ClaudeCode-AITeam/workspace
LANGSMITH_API_KEY=...           # optional, for eval tracing
```

### 3. Configure Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app
2. Add Bot Token Scopes: `chat:write`, `chat:write.customize`, `files:write`, `reactions:write`, `channels:history`, `channels:read`
3. Enable Event Subscriptions and add `message.channels`, `app_mention`
4. Install app to workspace

### 4. Start ngrok

```powershell
ngrok http 8000
```

Copy the `https://xxx.ngrok-free.app` URL.

### 5. Update Slack Event Subscriptions

In your Slack app settings, set Request URL to:
```
https://xxx.ngrok-free.app/slack/events
```

### 6. Start ClaudeForge

```powershell
python .\run.py
```

You should see:
```
============================================================
  ClaudeForge - AI Engineering Team
  HTTP Mode | Ready for messages
============================================================
```

### 7. Invite the bot to your channel

In Slack: `/invite @claudeforge`

---

## Running a Project

Post in your Slack channel:

```
@Business-Analyst I want to build a CSV Insights Generator web app
```

Then follow the conversation. At each approval gate, reply:
- `approved` — proceed to next stage
- `changes` + your feedback — revise and resubmit

If something fails, reply `resume` to retry.

---

## Demo Script (CSV Insights Generator)

1. Post the initial request in Slack
2. Answer BA questions about users and insight types
3. Approve requirements
4. Answer Architect question about UI preference (say **Streamlit**)
5. Approve architecture
6. Approve agent design
7. Watch implementation, review, security, testing, DevOps run automatically
8. Open `http://localhost:8501` in browser
9. Upload `sample_data/sales_data.csv`
10. Show the generated insights, charts, and AI summary

**Sample CSV:** `sample_data/sales_data.csv` — 60 rows of sales data with trends, top performers, and anomalies built in.

---

## Key Design Decisions

**Why HTTP mode over Socket Mode?**
Socket Mode load-balances events across all open connections. With multiple restarts during development, ghost connections accumulate and events get lost. HTTP mode via ngrok is deterministic — every event hits one endpoint.

**Why one file per Implementer invocation?**
Generating all files in one Claude call overflows the context window and produces truncated JSON. One file per call keeps responses small, allows each file to reference already-written files via the `known` context, and makes failures recoverable.

**Why SQLite over a heavier database?**
This is a local-first demo system. SQLite with WAL mode handles the sequential, single-process workload perfectly. No external dependencies to manage.

**Why commit after every stage?**
The git history becomes an audit trail of every decision the AI team made. During a demo you can show `git log` and walk through the entire engineering process commit by commit.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| App stuck in a state | Reply `resume` in the Slack thread |
| Ngrok URL changed | Update Request URL in Slack Event Subscriptions |
| Missing API keys warning | Add keys to `.env`, reply `ready` in thread |
| Port already in use | Kill the old process: `Get-Process python \| Stop-Process` |
| No events from Slack | Check bot is in channel (`/invite @claudeforge`), verify ngrok is forwarding to port 8000 |
