"""
Tests for bounded dependency traversal:
- depth=0
- depth=1
- depth=2
- cyclic dependency handling
- duplicate dependency handling
- missing local dependency handling
- cross-module local dependency resolution
- unrelated module exclusion
"""

from pathlib import Path
import pytest
from capsulemcp.ast_extractor import ASTExtractor
from capsulemcp.context_compiler import ContextCompiler


@pytest.fixture
def complex_repo(tmp_path):
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # mod_a.py has root_fn -> calls mod_b.b_fn (1-hop)
    (repo / "mod_a.py").write_text('''from mod_b import b_fn

def root_fn(x: int) -> int:
    return b_fn(x) + 1
''', encoding="utf-8")

    # mod_b.py has b_fn -> calls mod_c.c_fn (2-hop) and local helper_b
    (repo / "mod_b.py").write_text('''from mod_c import c_fn

def helper_b(y: int) -> int:
    return y * 2

def b_fn(y: int) -> int:
    return c_fn(y) + helper_b(y)
''', encoding="utf-8")

    # mod_c.py has c_fn (leaf)
    (repo / "mod_c.py").write_text('''def c_fn(z: int) -> int:
    return z * 10
''', encoding="utf-8")

    # cyclic_1.py and cyclic_2.py
    (repo / "cyclic_1.py").write_text('''from cyclic_2 import cyc_two

def cyc_one():
    return cyc_two()
''', encoding="utf-8")

    (repo / "cyclic_2.py").write_text('''from cyclic_1 import cyc_one

def cyc_two():
    return cyc_one()
''', encoding="utf-8")

    # unrelated.py
    (repo / "unrelated.py").write_text('''def unrelated_secret():
    return "secret"
''', encoding="utf-8")

    return repo


def test_depth_zero(complex_repo):
    """Depth=0 should return no dependencies."""
    extractor = ASTExtractor(repo_path=str(complex_repo))
    tree, src = extractor.parse_file(complex_repo / "mod_a.py")
    target_node = tree.body[1]  # root_fn

    deps = extractor.extract_local_dependencies(complex_repo / "mod_a.py", target_node, tree, max_depth=0)
    assert len(deps) == 0


def test_depth_one(complex_repo):
    """Depth=1 should extract direct 1-hop dependencies only (b_fn, but NOT c_fn or helper_b)."""
    extractor = ASTExtractor(repo_path=str(complex_repo))
    tree, src = extractor.parse_file(complex_repo / "mod_a.py")
    target_node = tree.body[1]

    deps = extractor.extract_local_dependencies(complex_repo / "mod_a.py", target_node, tree, max_depth=1)
    dep_names = {d.name for d in deps}
    assert "b_fn" in dep_names
    assert "c_fn" not in dep_names
    assert "helper_b" not in dep_names


def test_depth_two(complex_repo):
    """Depth=2 should extract 1-hop and 2-hop dependencies (b_fn, c_fn, helper_b)."""
    extractor = ASTExtractor(repo_path=str(complex_repo))
    tree, src = extractor.parse_file(complex_repo / "mod_a.py")
    target_node = tree.body[1]

    deps = extractor.extract_local_dependencies(complex_repo / "mod_a.py", target_node, tree, max_depth=2)
    dep_names = {d.name for d in deps}
    assert "b_fn" in dep_names
    assert "c_fn" in dep_names
    assert "helper_b" in dep_names
    assert "unrelated_secret" not in dep_names


def test_cyclic_dependency_protection(complex_repo):
    """Cyclic references between modules must terminate without recursion/infinite loop."""
    extractor = ASTExtractor(repo_path=str(complex_repo))
    tree, src = extractor.parse_file(complex_repo / "cyclic_1.py")
    target_node = tree.body[1]  # cyc_one

    # Even with depth=5, cyclic dependencies must terminate cleanly
    deps = extractor.extract_local_dependencies(complex_repo / "cyclic_1.py", target_node, tree, max_depth=5)
    dep_names = [d.name for d in deps]
    # Should only contain cyc_two, not infinite copies of cyc_one and cyc_two
    assert dep_names.count("cyc_two") == 1
    assert dep_names.count("cyc_one") == 0


def test_no_duplicate_dependencies(complex_repo):
    """Duplicate references across nodes should result in unique dependency entries."""
    extractor = ASTExtractor(repo_path=str(complex_repo))
    tree, src = extractor.parse_file(complex_repo / "mod_a.py")
    target_node = tree.body[1]

    deps = extractor.extract_local_dependencies(complex_repo / "mod_a.py", target_node, tree, max_depth=2)
    names = [d.name for d in deps]
    assert len(names) == len(set(names))


def test_missing_dependency_graceful_handling(tmp_path):
    """Importing from a non-existent local file should not crash the extractor."""
    repo = tmp_path / "broken_repo"
    repo.mkdir()
    (repo / "broken.py").write_text('''from nonexistent_module import ghost_fn

def caller():
    return ghost_fn()
''', encoding="utf-8")

    extractor = ASTExtractor(repo_path=str(repo))
    tree, src = extractor.parse_file(repo / "broken.py")
    target_node = tree.body[1]

    deps = extractor.extract_local_dependencies(repo / "broken.py", target_node, tree, max_depth=2)
    assert len(deps) == 0
