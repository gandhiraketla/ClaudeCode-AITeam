import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

WORKSPACE_BASE = Path(os.getenv("WORKSPACE_BASE_PATH", "C:/ClaudeCode-AITeam/workspace"))


def create_project_workspace(project_id: str) -> dict:
    base = WORKSPACE_BASE / project_id
    artifacts = base / "artifacts"
    src = base / "src"
    tests = base / "tests"

    for directory in [artifacts, src, tests]:
        directory.mkdir(parents=True, exist_ok=True)

    return {
        "workspace_path": str(base),
        "artifacts_path": str(artifacts),
        "src_path": str(src),
        "tests_path": str(tests),
    }


def get_project_paths(project_id: str) -> dict:
    base = WORKSPACE_BASE / project_id
    return {
        "workspace_path": str(base),
        "artifacts_path": str(base / "artifacts"),
        "src_path": str(base / "src"),
        "tests_path": str(base / "tests"),
    }


def write_artifact(project_id: str, filename: str, content: str) -> str:
    paths = get_project_paths(project_id)
    file_path = Path(paths["artifacts_path"]) / filename
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def get_file_tree(project_id: str) -> str:
    base = WORKSPACE_BASE / project_id
    lines = []
    for path in sorted(base.rglob("*")):
        if path.is_file():
            relative = path.relative_to(base)
            depth = len(relative.parts) - 1
            indent = "  " * depth
            lines.append(f"{indent}{'└── ' if depth > 0 else ''}{path.name}")
    return "\n".join(lines) if lines else "(empty)"
