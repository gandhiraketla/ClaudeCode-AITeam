import subprocess
import os
from pathlib import Path
from . import console

REPO_ROOT = Path(__file__).parent.parent


def _run(cmd: list, cwd: str = None) -> tuple[int, str]:
    result = subprocess.run(
        cmd,
        cwd=cwd or str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def git_available() -> bool:
    code, _ = _run(["git", "rev-parse", "--is-inside-work-tree"])
    return code == 0


def commit_artifact(project_id: str, stage: str, message: str, files: list[str] = None):
    """
    Stage and commit artifact files for a given project stage.
    files: list of absolute or relative-to-repo paths to stage.
           If None, stages the entire workspace/{project_id}/ directory.
    """
    if not git_available():
        console.error("git", "Not inside a git repo — skipping commit")
        return

    # Stage files
    if files:
        for f in files:
            code, out = _run(["git", "add", f])
            if code != 0:
                console.error("git", f"git add failed for {f}: {out}")
    else:
        workspace_rel = f"workspace/{project_id}"
        code, out = _run(["git", "add", workspace_rel])
        if code != 0:
            console.error("git", f"git add failed: {out}")
            return

    # Check if there's anything to commit
    code, status = _run(["git", "status", "--porcelain"])
    if not status.strip():
        console.error("git", f"Nothing to commit for stage {stage}")
        return

    # Commit
    commit_msg = f"feat({stage}): {message} [{project_id}]"
    code, out = _run(["git", "commit", "-m", commit_msg])
    if code == 0:
        print(f"  [git] Committed: {commit_msg}", flush=True)
    else:
        console.error("git", f"git commit failed: {out}")


def push():
    """Push to remote origin current branch."""
    code, out = _run(["git", "push"])
    if code == 0:
        print("  [git] Pushed to remote", flush=True)
    else:
        console.error("git", f"git push failed: {out}")


def get_log(n: int = 7) -> str:
    """Return last n commit messages."""
    code, out = _run(["git", "log", f"-{n}", "--oneline"])
    return out if code == 0 else ""
