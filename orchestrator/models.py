from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from enum import Enum


class ProjectState(str, Enum):
    IDLE = "IDLE"
    # BA discovery
    DISCOVERY_ACTIVE = "DISCOVERY_ACTIVE"
    DISCOVERY_WAITING = "DISCOVERY_WAITING"
    DISCOVERY_APPROVAL_PENDING = "DISCOVERY_APPROVAL_PENDING"
    # Architect discovery
    ARCH_DISCOVERY_ACTIVE = "ARCH_DISCOVERY_ACTIVE"
    ARCH_DISCOVERY_WAITING = "ARCH_DISCOVERY_WAITING"
    ARCH_WAITING_FOR_KEYS = "ARCH_WAITING_FOR_KEYS"
    ARCHITECTURE_ACTIVE = "ARCHITECTURE_ACTIVE"
    ARCHITECTURE_APPROVAL_PENDING = "ARCHITECTURE_APPROVAL_PENDING"
    # Agent design
    AGENT_DESIGN_ACTIVE = "AGENT_DESIGN_ACTIVE"
    AGENT_DESIGN_APPROVAL_PENDING = "AGENT_DESIGN_APPROVAL_PENDING"
    # Implementation
    IMPLEMENTATION_ACTIVE = "IMPLEMENTATION_ACTIVE"
    # Review
    REVIEW_ACTIVE = "REVIEW_ACTIVE"
    # Security audit (post-implementation)
    SECURITY_ACTIVE = "SECURITY_ACTIVE"
    # Testing with evals
    TESTING_ACTIVE = "TESTING_ACTIVE"
    # DevOps
    DEVOPS_ACTIVE = "DEVOPS_ACTIVE"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"


class ApprovalStatus(str, Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes"
    PENDING = "pending"


class SkillStatus(str, Enum):
    ASKING = "asking"
    READY = "ready"


class FindingSeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    BLOCKING = "BLOCKING"
    SUGGESTION = "SUGGESTION"


class ReviewVerdict(str, Enum):
    APPROVED = "APPROVED"
    APPROVED_WITH_CHANGES = "APPROVED_WITH_CHANGES"
    REJECTED = "REJECTED"


class TestVerdict(str, Enum):
    PASS_ = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"


# --- Skill Input Contract ---

class SkillContext(BaseModel):
    project_id: str
    stage: str
    persona: str
    workspace_path: str
    artifacts_path: str
    conversation_history: List[Dict[str, Any]] = []
    prior_artifacts: Dict[str, str] = {}
    user_message: Optional[str] = None
    turn: int = 1
    known: Dict[str, Any] = {}
    missing: List[str] = []


# --- Skill Output Contracts ---

class BAOutput(BaseModel):
    status: SkillStatus
    question: Optional[str] = None
    known: Dict[str, Any] = {}
    missing: List[str] = []
    requirements_doc: Optional[Dict[str, Any]] = None


class ArchitectOutput(BaseModel):
    architecture_doc: Dict[str, Any]
    open_risks: List[str] = []


class AgentDesignOutput(BaseModel):
    agent_design: Dict[str, Any]


class SecurityFinding(BaseModel):
    severity: FindingSeverity
    category: str
    description: str
    recommendation: str


class SecurityOutput(BaseModel):
    threat_model: List[str] = []
    findings: List[SecurityFinding] = []
    blocking_issues: List[SecurityFinding] = []
    advisory_issues: List[SecurityFinding] = []


class ImplementerOutput(BaseModel):
    files_created: List[str] = []
    file_tree: str
    key_snippets: Dict[str, str] = {}
    setup_instructions: str
    known_gaps: List[str] = []


class ReviewFinding(BaseModel):
    severity: FindingSeverity
    file: str
    line: Optional[str] = None
    issue: str
    recommendation: str


class ReviewerOutput(BaseModel):
    verdict: ReviewVerdict
    findings: List[ReviewFinding] = []
    summary: str


class TestCase(BaseModel):
    name: str
    description: str
    expected: str


class TesterOutput(BaseModel):
    eval_file: str = "evals/run_evals.py"
    eval_cases: List[Dict[str, Any]] = []
    gap_analysis: List[str] = []
    verdict: TestVerdict
    blocking_gaps: List[str] = []


class DevOpsOutput(BaseModel):
    start_command: str
    url: str
    port: int = 8000
    env_vars_required: List[str] = []
    health_check_path: str = "/health"
    setup_steps: List[str] = []
    known_issues: List[str] = []


class ArchDiscoveryOutput(BaseModel):
    status: str  # "asking" | "ready" | "needs_keys"
    question: Optional[str] = None
    known: Dict[str, Any] = {}
    missing: List[str] = []
    required_api_keys: List[Dict[str, str]] = []  # [{"key": "AMADEUS_CLIENT_ID", "purpose": "..."}]


# --- Orchestrator Internal Models ---

class Project(BaseModel):
    id: str
    name: Optional[str]
    slack_channel: str
    slack_thread_ts: str
    state: ProjectState
    created_at: str


class Message(BaseModel):
    project_id: str
    role: str
    persona: Optional[str]
    content: str
    slack_ts: Optional[str]


class Artifact(BaseModel):
    project_id: str
    stage: str
    file_path: str
    content: str
    approved: bool = False


class SlackEvent(BaseModel):
    type: str
    text: Optional[str] = None
    user: Optional[str] = None
    channel: Optional[str] = None
    ts: Optional[str] = None
    thread_ts: Optional[str] = None
    bot_id: Optional[str] = None


class ParsedMessage(BaseModel):
    persona: Optional[str]
    user_request: str
    is_thread_reply: bool
    thread_ts: Optional[str]
    channel: str
    user: str
    ts: str
