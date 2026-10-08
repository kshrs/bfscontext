"""
Git utilities to interact with repository state and commit SHAs.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_git_head_sha(repo_path: str = ".") -> str:
    """
    Get the current Git HEAD SHA of the given repository.
    Falls back to a deterministic string if not a git repository.
    """
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = res.stdout.strip()
        if sha:
            return sha
    except Exception as e:
        logger.debug("Failed to get git HEAD via subprocess in %s: %s", repo_path, e)

    # Check .git manually as secondary fallback
    git_dir = Path(repo_path) / ".git"
    if git_dir.exists():
        head_file = git_dir / "HEAD"
        if head_file.is_file():
            try:
                content = head_file.read_text().strip()
                if content.startswith("ref: "):
                    ref_path = git_dir / content[5:].strip()
                    if ref_path.is_file():
                        return ref_path.read_text().strip()
                elif len(content) == 40:
                    return content
            except Exception:
                pass

    return "0000000000000000000000000000000000000000"


def is_sha_stale(current_sha: str, target_sha: Optional[str]) -> bool:
    """Check if the provided target_sha matches current_sha."""
    if not target_sha:
        return False
    return current_sha.lower() != target_sha.lower()


def is_file_modified_in_git(file_path: str | Path, repo_path: str | Path = ".") -> bool:
    """
    Checks if a specific file has uncommitted modifications in git.
    Returns True if the file has untracked or unstaged changes.
    """
    try:
        path = Path(file_path)
        repo = Path(repo_path).resolve()
        rel_path = path.relative_to(repo) if path.is_absolute() else path
        res = subprocess.run(
            ["git", "status", "--porcelain", str(rel_path)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(res.stdout.strip())
    except Exception as e:
        logger.debug("Failed checking git status for %s: %s", file_path, e)
        return False


def restore_file_to_commit(file_path: str | Path, commit_sha: str, repo_path: str | Path = ".") -> bool:
    """
    Safely restores a specific target file to its state at commit_sha.
    Does NOT execute a broad git reset --hard, protecting unrelated changes.
    """
    try:
        path = Path(file_path)
        repo = Path(repo_path).resolve()
        rel_path = path.relative_to(repo) if path.is_absolute() else path
        subprocess.run(
            ["git", "checkout", commit_sha, "--", str(rel_path)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except Exception as e:
        logger.warning("Failed restoring file %s to commit %s: %s", file_path, commit_sha, e)
        return False

