"""
Tests for git utilities.
"""

from capsulemcp.git_utils import get_git_head_sha, is_sha_stale


def test_get_git_head_sha():
    sha = get_git_head_sha(".")
    assert isinstance(sha, str)
    assert len(sha) == 40


def test_is_sha_stale():
    sha1 = "a" * 40
    sha2 = "b" * 40
    assert is_sha_stale(sha1, sha2) is True
    assert is_sha_stale(sha1, sha1) is False
    assert is_sha_stale(sha1, None) is False
