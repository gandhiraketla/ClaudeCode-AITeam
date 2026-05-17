# ClaudeForge

> **An AI Engineering Team built with Claude.**
> Turn a single Slack message into a fully built, tested, and deployed application.

---

## Overview

ClaudeForge is a local-first AI engineering organization powered by Claude. You describe what you want to build in Slack. Eight specialized AI personas collaborate — asking questions, designing systems, writing code, reviewing it, auditing security, running evaluations, and deploying the result.

Every decision is committed to Git. Every stage is visible in your terminal. The final app is live on localhost.

---

## System Architecture

```
 ╔══════════════════════════════════════════════════════════════════════╗
 ║                          CLAUDEFORGE                                 ║
 ╚══════════════════════════════════════════════════════════════════════╝

  ┌─────────────────┐        HTTP POST         ┌──────────────────────┐
  │                 │  ─────────────────────>  │                      │
  │   Slack         │    /slack/events          │   FastAPI            │
  │   #channel      │  <─────────────────────  │   Orchestrator       │
  │                 │    persona messages       │   localhost:8000     │
  └─────────────────┘                          └──────────┬───────────┘
           ^                                              │
           │                                             │
    ngrok tunnel                                         │
    (public HTTPS)                              ┌────────▼────────────┐
                                                │   State Machine     │
                                                │   SQLite            │
                                                │                     │
                                                │  DISCOVERY          │
                                                │    -> ARCH          │
                                                │    -> AGENT_DESIGN  │
                                                │    -> IMPLEMENT     │
                                                │    -> REVIEW        │
                                                │    -> SECURITY      │
                                                │    -> TESTING       │
                                                │    -> DEVOPS        │
                                                │    -> COMPLETE      │
                                                └────────┬────────────┘
                                                         │
                                            ┌────────────▼─────────────┐
                                            │      Skill Runner        │
                                            │      Anthropic SDK       │
                                            │                          │
                                            │  system: <persona>.md    │
                                            │  user:   context JSON    │
                                            │  output: structured JSON │
                                            └────────────┬─────────────┘
                                                         │
                              ┌──────────────────────────▼──────────────────────────┐
                              │                  8 AI Personas                       │
                              │                                                       │
                              │  [BA] -> [Architect] -> [Agent Impl] -> [Implementer]│
                              │       -> [Reviewer]  -> [Security]  -> [Tester]      │
                              │       -> [DevOps]                                     │
                              └──────────────────────────┬──────────────────────────┘
                                                         │
                              ┌──────────────────────────▼──────────────────────────┐
                              │                Workspace / Git                        │
                              │                                                       │
                              │  workspace/{project}/                                 │
                              │    artifacts/   <- design docs (.md)                 │
                              │    src/         <- generated application code        │
                              │    evals/       <- LangSmith eval scripts            │
                              │                                                       │
                              │  git commit + push after every stage                 │
                              └─────────────────────────────────────────────────────┘
```

---

## The 8 AI Personas

Each persona is a markdown skill file in `.claude/skills/`. It defines the cognitive mode, input/output contract, and engineering rules for that role.

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                        PIPELINE FLOW                                      │
 │                                                                            │
 │   User types @Business-Analyst <request> in Slack                         │
 │                                                                            │
 │   ┌─────────────────┐                                                      │
 │   │  Business        │  Discovery loop — asks focused questions            │
 │   │  Analyst         │  until requirements are complete                    │
 │   │  [USER APPROVAL] │  Outputs: requirements.md                           │
 │   └────────┬─────────┘                                                     │
 │            │                                                               │
 │   ┌────────▼─────────┐                                                     │
 │   │  Solution         │  Technical discovery — asks about stack,           │
 │   │  Architect        │  UI preference, API keys needed                    │
 │   │  [USER APPROVAL] │  Outputs: architecture.md + Mermaid diagram        │
 │   └────────┬─────────┘                                                     │
 │            │                                                               │
 │   ┌────────▼─────────┐                                                     │
 │   │  Agent            │  Designs reasoning strategy, tools,                │
 │   │  Implementer      │  memory, guardrails                                │
 │   │  [USER APPROVAL] │  Outputs: agent-design.md                          │
 │   └────────┬─────────┘                                                     │
 │            │                                                               │
 │   ┌────────▼─────────┐                                                     │
 │   │  Implementer      │  Generates code file by file in dependency        │
 │   │  [AUTO]          │  order using prior artifacts as context             │
 │   └────────┬─────────┘  Outputs: src/, requirements.txt, demo.py          │
 │            │                                                               │
 │   ┌────────▼─────────┐                                                     │
 │   │  Code Reviewer    │  Audits quality, architecture alignment,           │
 │   │  [AUTO]          │  error handling, completeness                       │
 │   └────────┬─────────┘  Outputs: code-review.md                           │
 │            │                                                               │
 │   ┌────────▼─────────┐                                                     │
 │   │  Security         │  Audits actual generated code — OWASP Top 10,     │
 │   │  Reviewer [AUTO] │  prompt injection, hardcoded secrets                │
 │   └────────┬─────────┘  Outputs: security-audit.md                        │
 │            │                                                               │
 │   ┌────────▼─────────┐                                                     │
 │   │  Tester           │  Writes + executes LangSmith evaluations           │
 │   │  [AUTO]          │  against acceptance criteria                        │
 │   └────────┬─────────┘  Outputs: evals/run_evals.py, test-plan.md         │
 │            │                                                               │
 │   ┌────────▼─────────┐                                                     │
 │   │  DevOps           │  Installs deps, starts the app,                    │
 │   │  [AUTO]          │  health-checks, posts live URL to Slack             │
 │   └────────┬─────────┘                                                     │
 │            │                                                               │
 │   ┌────────▼─────────┐                                                     │
 │   │  COMPLETE         │  Git log posted to Slack. App is live.             │
 │   └──────────────────┘                                                     │
 └──────────────────────────────────────────────────────────────────────────┘
```

---

## Project Workspace

Every project gets an isolated workspace:

```
 workspace/
 └── {project-name}/
     ├── artifacts/
     │   ├── requirements.md          (Business Analyst)
     │   ├── architecture.md          (Solution Architect)
     │   ├── architecture.mermaid     (Solution Architect)
     │   ├── agent-design.md          (Agent Implementer)
     │   ├── implementation-report.md (Implementer)
     │   ├── code-review.md           (Code Reviewer)
     │   ├── security-audit.md        (Security Reviewer)
     │   └── test-plan.md             (Tester)
     ├── src/                         (generated application code)
     ├── evals/
     │   └── run_evals.py             (LangSmith evaluations)
     ├── tests/
     ├── requirements.txt
     ├── .env.example
     └── demo.py
```

---

## Git History Per Project

Every stage commits and pushes. Your repo tells the full engineering story:

```
feat(ba):                requirements document
feat(architect):         architecture design
feat(agent-implementer): agent reasoning design
feat(implementer):       initial implementation - N files
feat(reviewer):          code review - APPROVED
feat(security):          security audit - N findings
feat(tester):            evals and test plan - PASS
```

---

## Orchestrator Components

```
 orchestrator/
 ├── main.py              FastAPI app + Slack event handler + full pipeline
 ├── state.py             SQLite state machine — project lifecycle + artifacts
 ├── skill_runner.py      Invokes Claude with skill prompt + context JSON
 ├── context_builder.py   Assembles context passed to each skill invocation
 ├── router.py            Parses @mentions, detects approvals
 ├── approval_handler.py  Routes approved / changes responses
 ├── slack_client.py      Persona-aware Slack posting (username + emoji per role)
 ├── workspace_manager.py Creates and manages project workspace on disk
 ├── git_helper.py        Commits and pushes after each stage
 └── console.py           Color-coded terminal output
```

---

## Local Setup

### Prerequisites

- Python 3.12+
- [ngrok](https://ngrok.com) account and CLI
- Slack workspace with admin access
- Anthropic API key

### 1. Install

```powershell
git clone https://github.com/gandhiraketla/ClaudeCode-AITeam.git
cd ClaudeCode-AITeam
pip install -r requirements.txt
```

### 2. Configure `.env`

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_CHANNEL_ID=C...
ANTHROPIC_API_KEY=sk-ant-...
WORKSPACE_BASE_PATH=C:/ClaudeCode-AITeam/workspace
LANGSMITH_API_KEY=...        # optional — for eval tracing
```

### 3. Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App
2. **OAuth & Permissions** → Bot Token Scopes:
   `chat:write` `chat:write.customize` `files:write` `reactions:write` `channels:history` `channels:read`
3. **Event Subscriptions** → Subscribe to bot events:
   `message.channels` `app_mention`
4. Install app to workspace → copy Bot Token

### 4. Start

**Terminal 1:**
```powershell
python .\run.py
```

**Terminal 2:**
```powershell
ngrok http 8000
```

Paste the ngrok URL into **Slack App → Event Subscriptions → Request URL**:
```
https://xxx.ngrok-free.app/slack/events
```

**Invite bot to channel:**
```
/invite @claudeforge
```

---

## Usage

Post in Slack:

```
@Business-Analyst I want to build a CSV Insights Generator web app
```

At approval gates reply `approved` to proceed or `changes` + feedback to revise.
If a stage fails, reply `resume` to retry it.

---

## Key Design Decisions

**HTTP mode over Socket Mode**
Socket Mode load-balances events across all open connections. Ghost connections from restarts cause events to be lost. HTTP mode via ngrok is deterministic — every event hits one endpoint.

**One file per Implementer invocation**
A single call for all files overflows the context window and truncates JSON. One file per call keeps responses small, passes already-written files as context so imports stay consistent, and makes individual failures recoverable.

**SQLite over a heavier database**
Local-first demo system. SQLite with WAL mode handles the sequential workload with zero external dependencies.

**Commit after every stage**
The git history becomes a complete audit trail. You can show `git log` and walk through every decision the AI team made — from requirements to deployment.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Pipeline stuck | Reply `resume` in the Slack thread |
| ngrok URL changed | Update Request URL in Slack Event Subscriptions |
| Missing API keys | Add to `.env`, reply `ready` in thread |
| Port already in use | `Get-Process python \| Stop-Process -Force` |
| No events from Slack | Run `/invite @claudeforge`, verify ngrok forwards to port 8000 |
