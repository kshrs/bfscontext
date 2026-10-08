"""
Track A: Deterministic AST-based code analysis and syntactic unit extraction.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from capsulemcp.models import CodeUnit, DependencyUnit

logger = logging.getLogger(__name__)


class UnsupportedLanguageError(Exception):
    """Raised when the target file language is not supported for AST parsing."""
    pass


class SourceParseError(Exception):
    """Raised when source file cannot be parsed or contains syntax errors."""
    pass


class UnitNotFoundError(Exception):
    """Raised when the target function or class cannot be located in the file."""
    pass


class ASTExtractor:
    """Extracts syntactic units, imports, and 1-hop dependencies deterministically."""

    SUPPORTED_EXTENSIONS = {".py"}

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()

    def parse_file(self, file_path: str | Path) -> Tuple[ast.AST, str]:
        """Read and parse a Python file into an AST tree and its raw code."""
        path = Path(file_path)
        if not path.is_absolute():
            path = (self.repo_path / path).resolve()

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Source file not found: {path}")

        if path.suffix not in self.SUPPORTED_EXTENSIONS:
            raise UnsupportedLanguageError(
                f"File extension '{path.suffix}' is unsupported. Supported: {self.SUPPORTED_EXTENSIONS}"
            )

        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source = path.read_text(encoding="latin-1")

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            raise SourceParseError(f"Syntax error parsing {path}: {e}") from e

        return tree, source

    def extract_imports(self, tree: ast.AST, source: str) -> List[str]:
        """Extract all import statements preserving verbatim text from source."""
        lines = source.splitlines()
        import_statements: List[str] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # ast lines are 1-indexed
                start = node.lineno - 1
                end = getattr(node, "end_lineno", node.lineno)
                stmt = "\n".join(lines[start:end])
                import_statements.append(stmt)

        return import_statements

    def find_target_unit(
        self,
        tree: ast.AST,
        source: str,
        target_name: Optional[str] = None,
        subtask_description: str = "",
    ) -> CodeUnit:
        """
        Locate the complete syntactic unit (function or class).
        If target_name is not provided, infers it from subtask_description or selects the first primary unit.
        """
        lines = source.splitlines()

        # Collect candidate units
        candidates: List[Tuple[str, str, ast.AST, int, int]] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                candidates.append((node.name, "function", node, node.lineno, getattr(node, "end_lineno", node.lineno)))
            elif isinstance(node, ast.ClassDef):
                candidates.append((node.name, "class", node, node.lineno, getattr(node, "end_lineno", node.lineno)))

        if not candidates:
            raise UnitNotFoundError("No top-level function or class definitions found in source file.")

        selected = None
        if target_name:
            for c in candidates:
                if c[0] == target_name:
                    selected = c
                    break
        else:
            # Heuristic match against subtask description
            desc_lower = subtask_description.lower()
            for c in candidates:
                if c[0].lower() in desc_lower:
                    selected = c
                    break
            if not selected:
                # Default to the first candidate
                selected = candidates[0]

        if not selected:
            raise UnitNotFoundError(f"Target unit '{target_name}' not found in source.")

        name, unit_type, node, start_line, end_line = selected

        # Complete unit source preservation
        unit_source = "\n".join(lines[start_line - 1 : end_line])

        # Extract decorators
        decorators: List[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                dec_start = dec.lineno - 1
                dec_end = getattr(dec, "end_lineno", dec.lineno)
                decorators.append("\n".join(lines[dec_start:dec_end]))

        # Docstring
        docstring = ast.get_docstring(node)

        # Parameters
        params: List[str] = []
        returns: Optional[str] = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                params.append(arg_str)
            if node.returns:
                returns = ast.unparse(node.returns)

        return CodeUnit(
            name=name,
            unit_type=unit_type,
            source_code=unit_source,
            start_line=start_line,
            end_line=end_line,
            decorators=decorators,
            docstring=docstring,
            parameters=params,
            returns=returns,
        )

    def extract_referenced_names(self, node: ast.AST) -> Set[str]:
        """Extract all name identifiers referenced within a code node."""
        names: Set[str] = set()
        for subnode in ast.walk(node):
            if isinstance(subnode, ast.Name):
                names.add(subnode.id)
            elif isinstance(subnode, ast.Attribute) and isinstance(subnode.value, ast.Name):
                names.add(subnode.value.id)
        return names

    def extract_local_dependencies(
        self,
        target_file_path: str | Path,
        target_unit_node: ast.AST,
        tree: ast.AST,
    ) -> List[DependencyUnit]:
        """
        Controlled 1-hop dependency expansion:
        Finds definitions referenced by the target unit within the same file or directly imported local modules.
        """
        target_path = Path(target_file_path)
        if not target_path.is_absolute():
            target_path = (self.repo_path / target_path).resolve()

        referenced_names = self.extract_referenced_names(target_unit_node)
        dependencies: List[DependencyUnit] = []

        # 1. Check local top-level definitions within the same file (excluding target itself)
        source = target_path.read_text(encoding="utf-8")
        lines = source.splitlines()

        for node in ast.iter_child_nodes(tree):
            if node is target_unit_node:
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in referenced_names:
                    start = node.lineno - 1
                    end = getattr(node, "end_lineno", node.lineno)
                    dep_code = "\n".join(lines[start:end])
                    dependencies.append(
                        DependencyUnit(
                            name=node.name,
                            file_path=str(target_path.relative_to(self.repo_path)),
                            unit_type="class" if isinstance(node, ast.ClassDef) else "function",
                            source_code=dep_code,
                            is_direct=True,
                        )
                    )

        # 2. Check 1-hop local module imports
        # For each from X import Y, check if X is a local file in repo_path
        target_dir = target_path.parent
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                module_parts = node.module.split(".")
                # Candidates: relative to target_dir or relative to repo_path
                candidate_paths = [
                    target_dir / f"{node.module.replace('.', '/')}.py",
                    self.repo_path / f"{node.module.replace('.', '/')}.py",
                    self.repo_path / "src" / f"{node.module.replace('.', '/')}.py",
                ]
                found_path = None
                for cp in candidate_paths:
                    if cp.is_file():
                        found_path = cp
                        break

                if found_path:
                    # Parse target dependency file and extract imported symbols
                    try:
                        dep_tree, dep_source = self.parse_file(found_path)
                        dep_lines = dep_source.splitlines()
                        imported_names = {alias.name for alias in node.names if alias.name in referenced_names}

                        for dep_node in ast.iter_child_nodes(dep_tree):
                            if isinstance(dep_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                                if dep_node.name in imported_names:
                                    dep_start = dep_node.lineno - 1
                                    dep_end = getattr(dep_node, "end_lineno", dep_node.lineno)
                                    code = "\n".join(dep_lines[dep_start:dep_end])
                                    dependencies.append(
                                        DependencyUnit(
                                            name=dep_node.name,
                                            file_path=str(found_path.relative_to(self.repo_path)),
                                            unit_type="class" if isinstance(dep_node, ast.ClassDef) else "function",
                                            source_code=code,
                                            is_direct=True,
                                        )
                                    )
                    except Exception as e:
                        logger.debug("Could not resolve local dependency %s: %s", found_path, e)

        return dependencies
