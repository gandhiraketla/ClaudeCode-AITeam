import aiosqlite
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from .models import ProjectState

DB_PATH = Path(__file__).parent.parent / "db" / "claudeforge.db"
SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        schema = SCHEMA_PATH.read_text()
        await db.executescript(schema)
        await db.commit()


async def create_project(slack_channel: str, slack_thread_ts: str) -> str:
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO projects (id, slack_channel, slack_thread_ts, state) VALUES (?, ?, ?, ?)",
            (project_id, slack_channel, slack_thread_ts, ProjectState.DISCOVERY_ACTIVE)
        )
        await db.commit()
    return project_id


async def get_project_by_thread(thread_ts: str) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM projects WHERE slack_thread_ts = ?", (thread_ts,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_project(project_id: str) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_state(project_id: str, state: ProjectState):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET state = ? WHERE id = ?", (state, project_id)
        )
        await db.commit()


async def update_project_name(project_id: str, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET name = ? WHERE id = ?", (name, project_id)
        )
        await db.commit()


async def add_message(project_id: str, role: str, content: str,
                      persona: Optional[str] = None, slack_ts: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (project_id, role, persona, content, slack_ts) VALUES (?, ?, ?, ?, ?)",
            (project_id, role, persona, content, slack_ts)
        )
        await db.commit()


async def get_messages(project_id: str) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def save_artifact(project_id: str, stage: str, content: str,
                        file_path: Optional[str] = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO artifacts (project_id, stage, content, file_path) VALUES (?, ?, ?, ?)",
            (project_id, stage, content, file_path)
        )
        await db.commit()
        return cursor.lastrowid


async def approve_artifact(project_id: str, stage: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE artifacts SET approved = 1, approved_at = ? WHERE project_id = ? AND stage = ?",
            (datetime.utcnow().isoformat(), project_id, stage)
        )
        await db.commit()


async def get_artifact(project_id: str, stage: str) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM artifacts WHERE project_id = ? AND stage = ? ORDER BY created_at DESC LIMIT 1",
            (project_id, stage)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_artifacts(project_id: str) -> Dict[str, str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT stage, content FROM artifacts WHERE project_id = ? AND approved = 1 ORDER BY created_at ASC",
            (project_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {row["stage"]: row["content"] for row in rows}


# State machine transition map
VALID_TRANSITIONS = {
    ProjectState.DISCOVERY_ACTIVE:          [ProjectState.DISCOVERY_WAITING, ProjectState.DISCOVERY_APPROVAL_PENDING, ProjectState.BLOCKED],
    ProjectState.DISCOVERY_WAITING:         [ProjectState.DISCOVERY_ACTIVE],
    ProjectState.DISCOVERY_APPROVAL_PENDING:[ProjectState.ARCH_DISCOVERY_ACTIVE, ProjectState.DISCOVERY_ACTIVE],
    ProjectState.ARCH_DISCOVERY_ACTIVE:     [ProjectState.ARCH_DISCOVERY_WAITING, ProjectState.ARCH_WAITING_FOR_KEYS, ProjectState.ARCHITECTURE_ACTIVE, ProjectState.BLOCKED],
    ProjectState.ARCH_DISCOVERY_WAITING:    [ProjectState.ARCH_DISCOVERY_ACTIVE],
    ProjectState.ARCH_WAITING_FOR_KEYS:     [ProjectState.ARCHITECTURE_ACTIVE, ProjectState.ARCH_DISCOVERY_ACTIVE],
    ProjectState.ARCHITECTURE_ACTIVE:       [ProjectState.ARCHITECTURE_APPROVAL_PENDING, ProjectState.BLOCKED],
    ProjectState.ARCHITECTURE_APPROVAL_PENDING: [ProjectState.AGENT_DESIGN_ACTIVE, ProjectState.ARCHITECTURE_ACTIVE],
    ProjectState.AGENT_DESIGN_ACTIVE:       [ProjectState.AGENT_DESIGN_APPROVAL_PENDING, ProjectState.BLOCKED],
    ProjectState.AGENT_DESIGN_APPROVAL_PENDING: [ProjectState.IMPLEMENTATION_ACTIVE, ProjectState.AGENT_DESIGN_ACTIVE],
    ProjectState.IMPLEMENTATION_ACTIVE:     [ProjectState.REVIEW_ACTIVE, ProjectState.BLOCKED],
    ProjectState.REVIEW_ACTIVE:             [ProjectState.SECURITY_ACTIVE, ProjectState.IMPLEMENTATION_ACTIVE, ProjectState.BLOCKED],
    ProjectState.SECURITY_ACTIVE:           [ProjectState.TESTING_ACTIVE, ProjectState.BLOCKED],
    ProjectState.TESTING_ACTIVE:            [ProjectState.DEVOPS_ACTIVE, ProjectState.IMPLEMENTATION_ACTIVE, ProjectState.BLOCKED],
    ProjectState.DEVOPS_ACTIVE:             [ProjectState.COMPLETE, ProjectState.BLOCKED],
    ProjectState.COMPLETE:                  [],
    ProjectState.BLOCKED: [
        ProjectState.DISCOVERY_ACTIVE, ProjectState.ARCH_DISCOVERY_ACTIVE,
        ProjectState.ARCHITECTURE_ACTIVE, ProjectState.AGENT_DESIGN_ACTIVE,
        ProjectState.IMPLEMENTATION_ACTIVE, ProjectState.REVIEW_ACTIVE,
        ProjectState.SECURITY_ACTIVE, ProjectState.TESTING_ACTIVE,
        ProjectState.DEVOPS_ACTIVE,
    ],
}

# What stage each state resumes from (for the resume command)
RESUME_MAP = {
    ProjectState.BLOCKED:                   None,
    ProjectState.DISCOVERY_ACTIVE:          "ba",
    ProjectState.ARCH_DISCOVERY_ACTIVE:     "architect",
    ProjectState.ARCHITECTURE_ACTIVE:       "architect",
    ProjectState.AGENT_DESIGN_ACTIVE:       "agent-implementer",
    ProjectState.IMPLEMENTATION_ACTIVE:     "implementer",
    ProjectState.REVIEW_ACTIVE:             "reviewer",
    ProjectState.SECURITY_ACTIVE:           "security",
    ProjectState.TESTING_ACTIVE:            "tester",
    ProjectState.DEVOPS_ACTIVE:             "devops",
}

# Last approved stage -> next active state for resume from BLOCKED
RESUME_STATE_FROM_ARTIFACT = {
    None:               ProjectState.DISCOVERY_ACTIVE,
    "ba":               ProjectState.ARCH_DISCOVERY_ACTIVE,
    "architect":        ProjectState.AGENT_DESIGN_ACTIVE,
    "agent-implementer":ProjectState.IMPLEMENTATION_ACTIVE,
    "implementer":      ProjectState.REVIEW_ACTIVE,
    "reviewer":         ProjectState.SECURITY_ACTIVE,
    "security":         ProjectState.TESTING_ACTIVE,
    "tester":           ProjectState.DEVOPS_ACTIVE,
}

RESUME_PERSONA_FROM_ARTIFACT = {
    None:               "ba",
    "ba":               "architect",
    "architect":        "agent-implementer",
    "agent-implementer":"implementer",
    "implementer":      "reviewer",
    "reviewer":         "security",
    "security":         "tester",
    "tester":           "devops",
}


async def transition(project_id: str, new_state: ProjectState):
    project = await get_project(project_id)
    current = ProjectState(project["state"])
    allowed = VALID_TRANSITIONS.get(current, [])
    if new_state not in allowed:
        raise ValueError(f"Invalid transition: {current} -> {new_state}")
    await update_state(project_id, new_state)


async def block_project(project_id: str, error_msg: str):
    """Move project to BLOCKED and store the error for display."""
    await update_state(project_id, ProjectState.BLOCKED)
    # Store error as a message so it's visible in history
    await add_message(project_id, "agent", f"[BLOCKED]: {error_msg}", persona="orchestrator")


async def get_resume_info(project_id: str) -> dict:
    """Return what state and persona to resume from for a blocked/stuck project."""
    project = await get_project(project_id)
    state = ProjectState(project["state"])
    persona = RESUME_MAP.get(state)
    return {"state": state, "persona": persona, "project": project}
