from .router import is_approval_message
from .models import ProjectState
from . import state as db

# Maps approval-pending state -> (next_active_state, next_persona)
STATE_TO_NEXT_STAGE = {
    "DISCOVERY_APPROVAL_PENDING":      ("ARCH_DISCOVERY_ACTIVE", "architect"),
    "ARCHITECTURE_APPROVAL_PENDING":   ("AGENT_DESIGN_ACTIVE",   "agent-implementer"),
    "AGENT_DESIGN_APPROVAL_PENDING":   ("IMPLEMENTATION_ACTIVE", "implementer"),
}

# Maps approval-pending state -> loop-back state on changes
LOOP_BACK_MAP = {
    "DISCOVERY_APPROVAL_PENDING":      (ProjectState.DISCOVERY_ACTIVE,    "ba"),
    "ARCHITECTURE_APPROVAL_PENDING":   (ProjectState.ARCHITECTURE_ACTIVE, "architect"),
    "AGENT_DESIGN_APPROVAL_PENDING":   (ProjectState.AGENT_DESIGN_ACTIVE, "agent-implementer"),
}

# Stage that was just approved (for approve_artifact call)
PENDING_TO_STAGE = {
    "DISCOVERY_APPROVAL_PENDING":    "ba",
    "ARCHITECTURE_APPROVAL_PENDING": "architect",
    "AGENT_DESIGN_APPROVAL_PENDING": "agent-implementer",
}


async def handle_approval(project_id: str, text: str, channel: str,
                           thread_ts: str) -> dict:
    project = await db.get_project(project_id)
    current_state = project["state"]

    is_approval, approved, feedback = is_approval_message(text)
    if not is_approval:
        return {"handled": False}

    if current_state not in STATE_TO_NEXT_STAGE:
        return {"handled": False}

    if approved:
        completed_stage = PENDING_TO_STAGE.get(current_state)
        if completed_stage:
            await db.approve_artifact(project_id, completed_stage)

        next_state_str, next_persona = STATE_TO_NEXT_STAGE[current_state]
        await db.update_state(project_id, ProjectState(next_state_str))

        return {
            "handled": True,
            "approved": True,
            "feedback": "",
            "next_stage": next_state_str,
            "next_persona": next_persona,
        }
    else:
        loop_state, loop_persona = LOOP_BACK_MAP[current_state]
        await db.update_state(project_id, loop_state)

        return {
            "handled": True,
            "approved": False,
            "feedback": feedback,
            "next_stage": loop_state.value,
            "next_persona": loop_persona,
        }
