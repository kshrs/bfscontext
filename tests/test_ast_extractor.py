"""
Tests for ASTExtractor (Track A State extraction).
"""

import pytest
from pathlib import Path
from capsulemcp.ast_extractor import (
    ASTExtractor,
    SourceParseError,
    UnitNotFoundError,
    UnsupportedLanguageError,
)


@pytest.fixture
def sample_code_file(tmp_path):
    code = '''import os
from math import sqrt
from helpers import helper_fn

GLOBAL_VAR = 42

def helper_internal(x: int) -> int:
    """Internal helper."""
    return x * 2

@decorator_a
@decorator_b(param=1)
def target_function(val: int) -> int:
    """Computes target value."""
    temp = helper_internal(val)
    return temp + helper_fn(val)

class TargetClass:
    """Target class representation."""
    def run(self):
        return True
'''
    helper_code = '''def helper_fn(y: int) -> int:
    return y + 10
'''
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()
    (repo_dir / "helpers.py").write_text(helper_code, encoding="utf-8")
    target_file = repo_dir / "target.py"
    target_file.write_text(code, encoding="utf-8")
    return repo_dir, target_file


def test_target_function_extraction(sample_code_file):
    repo_dir, target_file = sample_code_file
    extractor = ASTExtractor(repo_path=str(repo_dir))
    tree, source = extractor.parse_file(target_file)

    unit = extractor.find_target_unit(tree, source, target_name="target_function")
    assert unit.name == "target_function"
    assert unit.unit_type == "function"
    assert unit.returns == "int"
    assert "val: int" in unit.parameters
    assert unit.docstring == "Computes target value."
    assert len(unit.decorators) == 2
    assert "@decorator_a" in unit.decorators[0]
    assert "def target_function" in unit.source_code


def test_import_preservation(sample_code_file):
    repo_dir, target_file = sample_code_file
    extractor = ASTExtractor(repo_path=str(repo_dir))
    tree, source = extractor.parse_file(target_file)
    imports = extractor.extract_imports(tree, source)

    assert any("import os" in imp for imp in imports)
    assert any("from math import sqrt" in imp for imp in imports)
    assert any("from helpers import helper_fn" in imp for imp in imports)


def test_local_dependency_extraction(sample_code_file):
    repo_dir, target_file = sample_code_file
    extractor = ASTExtractor(repo_path=str(repo_dir))
    tree, source = extractor.parse_file(target_file)

    unit = extractor.find_target_unit(tree, source, target_name="target_function")
    # target node
    target_node = next(n for n in tree.body if getattr(n, "name", None) == "target_function")
    deps = extractor.extract_local_dependencies(target_file, target_node, tree)

    dep_names = {d.name for d in deps}
    # helper_internal is in the same file; helper_fn is in 1-hop helpers.py
    assert "helper_internal" in dep_names
    assert "helper_fn" in dep_names


def test_irrelevant_code_exclusion(sample_code_file):
    repo_dir, target_file = sample_code_file
    extractor = ASTExtractor(repo_path=str(repo_dir))
    tree, source = extractor.parse_file(target_file)

    unit = extractor.find_target_unit(tree, source, target_name="target_function")
    assert "TargetClass" not in unit.source_code


def test_missing_file_handling():
    extractor = ASTExtractor()
    with pytest.raises(FileNotFoundError):
        extractor.parse_file("non_existent_file.py")


def test_invalid_source_syntax(tmp_path):
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("def unclosed_function(:", encoding="utf-8")
    extractor = ASTExtractor()
    with pytest.raises(SourceParseError):
        extractor.parse_file(bad_file)


def test_unsupported_language_handling(tmp_path):
    js_file = tmp_path / "script.js"
    js_file.write_text("function test() {}", encoding="utf-8")
    extractor = ASTExtractor()
    with pytest.raises(UnsupportedLanguageError):
        extractor.parse_file(js_file)


def test_unit_not_found_handling(sample_code_file):
    repo_dir, target_file = sample_code_file
    extractor = ASTExtractor(repo_path=str(repo_dir))
    tree, source = extractor.parse_file(target_file)
    with pytest.raises(UnitNotFoundError):
        extractor.find_target_unit(tree, source, target_name="non_existent_fn")
