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
