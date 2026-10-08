"""
Context generation baselines for comparison against CapsuleMCP:
1. Full Context (uncompiled raw repository context)
2. Vector-style Retrieval Simulation (configurable top-k semantic chunking)
3. Capsule Compiler (deterministic AST-compiled minimal sufficient context)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
from capsulemcp.context_compiler import ContextCompiler
from capsulemcp.models import ContextCapsule


def generate_full_context(repo_path: str | Path) -> str:
    """
    Concatenates all source files in repository with file header separators.
    Represents the naive baseline where an agent receives the entire codebase.
    """
    repo = Path(repo_path).resolve()
    chunks = []
    for f in sorted(repo.rglob("*.py")):
        if f.is_file():
            rel = f.relative_to(repo)
            code = f.read_text(encoding="utf-8")
            chunks.append(f"### File: {rel}\n{code}\n")
    return "\n".join(chunks)


def generate_vector_retrieval_simulation(
    repo_path: str | Path,
    query: str,
    top_k: int = 3,
    chunk_size_lines: int = 25,
) -> str:
    """
    Simulates standard RAG vector retrieval:
    NOTE: VECTOR-STYLE RETRIEVAL SIMULATION ONLY - NOT A REAL EMBEDDING MODEL OR VECTOR DB.
    Chunks files into fixed-size line windows, scores chunks via lexical token overlap with the query,
    and returns top-k chunks.
    """
    repo = Path(repo_path).resolve()
    query_tokens = set(query.lower().replace("(", " ").replace(")", " ").replace(".", " ").split())

    scored_chunks: List[Tuple[int, str]] = []

    for f in sorted(repo.rglob("*.py")):
        if not f.is_file():
            continue
        rel = f.relative_to(repo)
        lines = f.read_text(encoding="utf-8").splitlines()
        for i in range(0, len(lines), chunk_size_lines):
            chunk_slice = lines[i : i + chunk_size_lines]
            chunk_text = "\n".join(chunk_slice)
            chunk_tokens = set(chunk_text.lower().replace("(", " ").replace(")", " ").replace(".", " ").split())
            overlap = len(query_tokens.intersection(chunk_tokens))
            header = f"### [Chunk from {rel}:{i+1}-{i+len(chunk_slice)} (score={overlap})]\n"
            scored_chunks.append((overlap, header + chunk_text))

    # Sort descending by score; break ties deterministically by text content
    scored_chunks.sort(key=lambda x: (x[0], x[1]), reverse=True)
    selected = [c[1] for c in scored_chunks[:top_k]]
    return "\n\n".join(selected)


def generate_capsule_context(
    repo_path: str | Path,
    file_path: str,
    subtask_description: str,
    target_unit_name: str,
    dependency_depth: int = 1,
) -> Tuple[ContextCapsule, str]:
    """Compiles algorithmic Context Capsule."""
    compiler = ContextCompiler(repo_path=str(repo_path))
    capsule = compiler.generate_context_capsule(
        file_path=file_path,
        subtask_description=subtask_description,
        target_unit_name=target_unit_name,
        dependency_depth=dependency_depth,
    )
    return capsule, capsule.render()
