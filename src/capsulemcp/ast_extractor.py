"""
Track A: Deterministic AST-based code analysis and syntactic unit extraction.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from capsulemcp.adapters.interfaces import CodeAnalyzer
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


class ASTExtractor(CodeAnalyzer):
    """Extracts syntactic units, imports, and 1-hop dependencies deterministically using Python AST."""

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

        # Collect candidate units (top-level and class methods)
        candidates: List[Tuple[str, str, ast.AST, int, int]] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                candidates.append((node.name, "function", node, node.lineno, getattr(node, "end_lineno", node.lineno)))
            elif isinstance(node, ast.ClassDef):
                candidates.append((node.name, "class", node, node.lineno, getattr(node, "end_lineno", node.lineno)))
                # Also collect methods within the class
                for subnode in ast.iter_child_nodes(node):
                    if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        candidates.append((subnode.name, "method", subnode, subnode.lineno, getattr(subnode, "end_lineno", subnode.lineno)))
                        # Also register qualified name e.g. AuthService.authenticate_user
                        candidates.append((f"{node.name}.{subnode.name}", "method", subnode, subnode.lineno, getattr(subnode, "end_lineno", subnode.lineno)))

        if not candidates:
            raise UnitNotFoundError("No top-level or class function/class definitions found in source file.")

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

    def _resolve_module_path(self, from_file_path: Path, module_name: str) -> Optional[Path]:
        """Resolves local imported module path relative to source directory or repo root."""
        target_dir = from_file_path.parent
        candidate_paths = [
            target_dir / f"{module_name.replace('.', '/')}.py",
            self.repo_path / f"{module_name.replace('.', '/')}.py",
            self.repo_path / "src" / f"{module_name.replace('.', '/')}.py",
        ]
        for cp in candidate_paths:
            if cp.is_file():
                return cp.resolve()
        return None

    def extract_local_dependencies(
        self,
        target_file_path: str | Path,
        target_unit_node: ast.AST,
        tree: ast.AST,
        max_depth: int = 1,
    ) -> List[DependencyUnit]:
        """
        Controlled bounded dependency expansion up to max_depth (e.g. 0, 1, 2).
        Guarantees termination, cyclic dependency protection, and deduplication.
        """
        if max_depth <= 0:
            return []

        target_path = Path(target_file_path)
        if not target_path.is_absolute():
            target_path = (self.repo_path / target_path).resolve()

        # Track visited symbols: (resolved_file_path_str, symbol_name)
        visited_symbols: Set[Tuple[str, str]] = set()
        target_name = getattr(target_unit_node, "name", "")
        visited_symbols.add((str(target_path), target_name))

        dependencies: List[DependencyUnit] = []

        # Queue items: (current_node, current_file_path, current_tree, current_depth)
        queue = [(target_unit_node, target_path, tree, 1)]

        # Cache parsed files: path -> (tree, source)
        file_cache: Dict[str, Tuple[ast.AST, str]] = {
            str(target_path): (tree, target_path.read_text(encoding="utf-8"))
        }

        while queue:
            curr_node, curr_path, curr_tree, curr_depth = queue.pop(0)
            if curr_depth > max_depth:
                continue

            ref_names = self.extract_referenced_names(curr_node)
            curr_source = file_cache[str(curr_path)][1]
            curr_lines = curr_source.splitlines()

            # 1. Local definitions in the SAME file
            for node in ast.iter_child_nodes(curr_tree):
                if node is curr_node:
                    continue
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    sym_key = (str(curr_path), node.name)
                    if node.name in ref_names and sym_key not in visited_symbols:
                        visited_symbols.add(sym_key)
                        start = node.lineno - 1
                        end = getattr(node, "end_lineno", node.lineno)
                        dep_code = "\n".join(curr_lines[start:end])
                        dep_unit = DependencyUnit(
                            name=node.name,
                            file_path=str(curr_path.relative_to(self.repo_path)),
                            unit_type="class" if isinstance(node, ast.ClassDef) else "function",
                            source_code=dep_code,
                            is_direct=(curr_depth == 1),
                        )
                        dependencies.append(dep_unit)
                        if curr_depth + 1 <= max_depth:
                            queue.append((node, curr_path, curr_tree, curr_depth + 1))

            # 2. Local module imports in curr_tree
            for node in ast.iter_child_nodes(curr_tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    resolved_mod_path = self._resolve_module_path(curr_path, node.module)
                    if not resolved_mod_path:
                        continue

                    mod_str = str(resolved_mod_path)
                    if mod_str not in file_cache:
                        try:
                            d_tree, d_source = self.parse_file(resolved_mod_path)
                            file_cache[mod_str] = (d_tree, d_source)
                        except Exception as e:
                            logger.debug("Failed parsing dependency file %s: %s", resolved_mod_path, e)
                            continue

                    dep_tree, dep_source = file_cache[mod_str]
                    dep_lines = dep_source.splitlines()
                    imported_names = {alias.name for alias in node.names if alias.name in ref_names}

                    for d_node in ast.iter_child_nodes(dep_tree):
                        if isinstance(d_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            sym_key = (mod_str, d_node.name)
                            if d_node.name in imported_names and sym_key not in visited_symbols:
                                visited_symbols.add(sym_key)
                                d_start = d_node.lineno - 1
                                d_end = getattr(d_node, "end_lineno", d_node.lineno)
                                code = "\n".join(dep_lines[d_start:d_end])
                                dep_unit = DependencyUnit(
                                    name=d_node.name,
                                    file_path=str(resolved_mod_path.relative_to(self.repo_path)),
                                    unit_type="class" if isinstance(d_node, ast.ClassDef) else "function",
                                    source_code=code,
                                    is_direct=(curr_depth == 1),
                                )
                                dependencies.append(dep_unit)
                                if curr_depth + 1 <= max_depth:
                                    queue.append((d_node, resolved_mod_path, dep_tree, curr_depth + 1))

        return dependencies


# Alias for explicit clarity
PythonASTAnalyzer = ASTExtractor
