import re
from typing import Optional, Tuple

ALIAS_MAP = {
    "business-analyst": "ba",
    "businessanalyst": "ba",
    "ba": "ba",
    "analyst": "ba",
    "architect": "architect",
    "solution-architect": "architect",
    "solutionarchitect": "architect",
    "agent-implementer": "agent-implementer",
    "agentimplementer": "agent-implementer",
    "agent": "agent-implementer",
    "security": "security",
    "security-reviewer": "security",
    "securityreviewer": "security",
    "implementer": "implementer",
    "implement": "implementer",
    "developer": "implementer",
    "reviewer": "reviewer",
    "code-reviewer": "reviewer",
    "codereviewer": "reviewer",
    "review": "reviewer",
    "tester": "tester",
    "test": "tester",
    "qa": "tester",
}

MENTION_PATTERN = re.compile(r"^@([\w\-]+)\s*(.*)", re.IGNORECASE | re.DOTALL)


def parse_mention(text: str) -> Tuple[Optional[str], str]:
    """
    Returns (persona_key, user_request).
    persona_key is None if no valid @mention found.
    """
    text = text.strip()
    match = MENTION_PATTERN.match(text)
    if not match:
        return None, text

    alias = match.group(1).lower()
    user_request = match.group(2).strip()
    persona = ALIAS_MAP.get(alias)
    return persona, user_request


def is_approval_message(text: str) -> Tuple[bool, bool, str]:
    """
    Returns (is_approval_response, is_approved, feedback_text).
    Strips Slack formatting characters (* _ ~ `) before matching.
    """
    # Strip Slack markdown formatting and whitespace
    clean = re.sub(r"[*_~`]", "", text).strip().lower()

    if clean.startswith("approved"):
        return True, True, ""

    if clean.startswith("changes") or clean.startswith("change") or clean.startswith("revise"):
        feedback = re.sub(r"^(changes?|revise)\s*[:\-]?\s*", "", clean, flags=re.IGNORECASE).strip()
        return True, False, feedback

    return False, False, ""


# Maps project state to which persona should act next after approval
STATE_TO_NEXT_STAGE = {
    "DISCOVERY_APPROVAL_PENDING": ("ARCHITECTURE_ACTIVE", "architect"),
    "ARCHITECTURE_APPROVAL_PENDING": ("AGENT_DESIGN_ACTIVE", "agent-implementer"),
    "AGENT_DESIGN_APPROVAL_PENDING": ("SECURITY_ACTIVE", "security"),
}
