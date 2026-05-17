from typing import Dict, List
from . import state as db
from .workspace_manager import get_project_paths
from .models import SkillContext


async def build_context(project_id: str, stage: str, persona: str,
                        user_message: str = None, turn: int = 1,
                        known: dict = None, missing: list = None) -> SkillContext:
    paths = get_project_paths(project_id)
    conversation_history = await db.get_messages(project_id)
    prior_artifacts = await db.get_all_artifacts(project_id)

    history = [
        {"role": msg["role"], "content": msg["content"], "persona": msg.get("persona") or ""}
        for msg in conversation_history
    ]

    return SkillContext(
        project_id=project_id,
        stage=stage,
        persona=persona,
        workspace_path=paths["workspace_path"],
        artifacts_path=paths["artifacts_path"],
        conversation_history=history,
        prior_artifacts=prior_artifacts,
        user_message=user_message,
        turn=turn,
        known=known or {},
        missing=missing or [],
    )
