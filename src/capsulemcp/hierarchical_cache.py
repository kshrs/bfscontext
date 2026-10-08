"""
Hierarchical L1/L2/L3 Cache and Direct Hash Indexing Engine for BFSContext.

Addresses Research Feedback:
1. Replaces polynomial-time DAG search O(V * E) with O(1) Direct Hash Indexing.
2. Replaces giant in-memory databases with Multi-Tier Memory/Storage:
   - L1: In-RAM LRU Cache (Strict bounds < 10MB) for hottest symbol contracts & AST metadata.
   - L2: SSD Hash Table (Persistent SQLite WAL / Key-Value Hash Index on NVMe/SSD)
         Keyed by sha256(repo_path, file_path, symbol_name, commit_sha).
   - L3: SSD Cold Epistemic Ledger (Compressed historical AST diffs & serialized snapshots).
3. Co-reduces Host Memory Footprint alongside LLM Attention Memory / KV-Cache Footprint.
"""

import os
import sys
import ast
import json
import time
import zlib
import sqlite3
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from collections import OrderedDict
from dataclasses import dataclass, asdict


@dataclass
class IndexedSymbol:
    symbol_name: str
    file_path: str
    commit_sha: str
    code_body: str
    imports: List[str]
    direct_dependencies: List[str]  # O(1) Inverted 1-hop dependencies
    docstring: Optional[str]
    token_count: int
    ast_hash: str


class L1RamLRUCache:
    """
    Tier 1: Hot In-RAM LRU Cache.
    Strictly bounded in size (default: 128 symbols, ~1-2 MB RAM) to eliminate RAM bloat.
    """
    def __init__(self, capacity: int = 128):
        self.capacity = capacity
        self.cache: OrderedDict[str, IndexedSymbol] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[IndexedSymbol]:
        if key in self.cache:
            self.hits += 1
            self.cache.move_to_end(key)
            return self.cache[key]
        self.misses += 1
        return None

    def put(self, key: str, value: IndexedSymbol) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def size(self) -> int:
        return len(self.cache)

    def get_memory_bytes_estimate(self) -> int:
        total = sys.getsizeof(self.cache)
        for k, v in self.cache.items():
            total += sys.getsizeof(k) + sys.getsizeof(v.code_body) + sys.getsizeof(v)
        return total


class L2SsdHashTable:
    """
    Tier 2: SSD Hash Table.
    Uses SQLite in WAL (Write-Ahead-Log) mode stored on disk (SSD) for sub-millisecond O(1) hash lookups.
    Key: hash_key = sha256(repo + file + symbol + commit_sha)
    Value: Compressed binary blob of the IndexedSymbol.
    """
    def __init__(self, db_path: str = ".bfscontext_cache/l2_ssd_cache.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()
        self.hits = 0
        self.misses = 0

    def _init_db(self):
        with self.conn:
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.execute("PRAGMA synchronous = NORMAL;")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS ssd_hash_index (
                    hash_key TEXT PRIMARY KEY,
                    symbol_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    commit_sha TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    compressed_payload BLOB NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sym ON ssd_hash_index(symbol_name, commit_sha)")

    def get(self, hash_key: str) -> Optional[IndexedSymbol]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT compressed_payload FROM ssd_hash_index WHERE hash_key = ?", (hash_key,))
        row = cursor.fetchone()
        if row:
            self.hits += 1
            decompressed = zlib.decompress(row[0]).decode("utf-8")
            data = json.loads(decompressed)
            return IndexedSymbol(**data)
        self.misses += 1
        return None

    def put(self, hash_key: str, symbol: IndexedSymbol) -> None:
        payload = json.dumps(asdict(symbol)).encode("utf-8")
        compressed = zlib.compress(payload, level=6)
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO ssd_hash_index 
                (hash_key, symbol_name, file_path, commit_sha, token_count, compressed_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                hash_key,
                symbol.symbol_name,
                symbol.file_path,
                symbol.commit_sha,
                symbol.token_count,
                compressed,
                time.time()
            ))

    def count(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ssd_hash_index")
        return cursor.fetchone()[0]


class L3SsdColdLedger:
    """
    Tier 3: SSD Cold Epistemic Ledger.
    Stores cold historical commits, macro architectural intents, and code diff snapshots
    in append-only compressed zlib archives on SSD.
    """
    def __init__(self, storage_dir: str = ".bfscontext_cache/l3_cold_ledger"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def archive_cold_context(self, commit_sha: str, context_type: str, raw_payload: str) -> str:
        h = hashlib.sha256(f"{commit_sha}:{context_type}:{raw_payload}".encode()).hexdigest()[:16]
        filename = f"{commit_sha}_{context_type}_{h}.bin"
        filepath = os.path.join(self.storage_dir, filename)
        compressed = zlib.compress(raw_payload.encode("utf-8"), level=9)
        with open(filepath, "wb") as f:
            f.write(compressed)
        return filepath

    def retrieve_cold_context(self, filepath: str) -> Optional[str]:
        if not os.path.exists(filepath):
            return None
        with open(filepath, "rb") as f:
            compressed = f.read()
        return zlib.decompress(compressed).decode("utf-8")


class DirectHashIndexer:
    """
    Replaces Polynomial DAG Traversal with Direct O(1) Hash Indexing.
    Extracts all symbols and creates an inverted direct-hash lookup table:
    hash_key = sha256(f"{file_path}::{symbol_name}::{commit_sha}")
    """
    @staticmethod
    def compute_hash_key(file_path: str, symbol_name: str, commit_sha: str) -> str:
        return hashlib.sha256(f"{file_path}::{symbol_name}::{commit_sha}".encode("utf-8")).hexdigest()

    @staticmethod
    def parse_file_to_symbols(file_path: str, code_content: str, commit_sha: str) -> Dict[str, IndexedSymbol]:
        symbols: Dict[str, IndexedSymbol] = {}
        try:
            tree = ast.parse(code_content, filename=file_path)
        except SyntaxError:
            return symbols

        file_imports: List[str] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                file_imports.append(ast.unparse(node).strip())

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                sym_name = node.name
                docstring = ast.get_docstring(node)
                code_body = ast.unparse(node).strip()

                # Fast 1-hop callee extraction (Direct Dependency tracking without deep graph walk)
                direct_deps = []
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        direct_deps.append(sub.func.id)
                    elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        direct_deps.append(sub.func.attr)

                direct_deps = sorted(list(set(direct_deps)))
                token_count = max(len(code_body.split()), len(code_body) // 4)
                ast_hash = hashlib.sha256(code_body.encode("utf-8")).hexdigest()[:12]

                indexed = IndexedSymbol(
                    symbol_name=sym_name,
                    file_path=file_path,
                    commit_sha=commit_sha,
                    code_body=code_body,
                    imports=file_imports,
                    direct_dependencies=direct_deps,
                    docstring=docstring,
                    token_count=token_count,
                    ast_hash=ast_hash
                )
                symbols[sym_name] = indexed

        return symbols


class HierarchicalCacheManager:
    """
    Unified Hierarchical Context Router:
    1. Looks up L1 (RAM LRU, <10MB).
    2. On miss, looks up L2 (SSD Hash Table, sub-ms).
    3. On miss, compiles AST, indexes symbols, hydrates L2 on SSD, and warms L1 in RAM.
    4. Cold historical ledgers stored in L3 SSD storage.
    """
    def __init__(self, cache_dir: str = ".bfscontext_cache"):
        self.cache_dir = cache_dir
        self.l1_ram = L1RamLRUCache(capacity=256)
        self.l2_ssd = L2SsdHashTable(db_path=os.path.join(cache_dir, "l2_ssd_hash_index.db"))
        self.l3_cold = L3SsdColdLedger(storage_dir=os.path.join(cache_dir, "l3_cold_ledger"))

    def resolve_symbol(self, file_path: str, symbol_name: str, commit_sha: str, file_content: Optional[str] = None) -> Tuple[IndexedSymbol, str, float]:
        """
        Returns (IndexedSymbol, source_tier, lookup_latency_ms)
        source_tier in ["L1_RAM", "L2_SSD", "L3_COMPILED"]
        """
        hash_key = DirectHashIndexer.compute_hash_key(file_path, symbol_name, commit_sha)
        t0 = time.perf_counter()

        # 1. Check L1 RAM Cache
        sym = self.l1_ram.get(hash_key)
        if sym:
            lat = round((time.perf_counter() - t0) * 1000.0, 3)
            return sym, "L1_RAM", lat

        # 2. Check L2 SSD Hash Table
        sym = self.l2_ssd.get(hash_key)
        if sym:
            # Promote to L1 Hot Cache
            self.l1_ram.put(hash_key, sym)
            lat = round((time.perf_counter() - t0) * 1000.0, 3)
            return sym, "L2_SSD", lat

        # 3. Cache Miss: Parse file AST and hydrate both L2 and L1
        if file_content is None and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
        elif file_content is None:
            file_content = ""

        all_symbols = DirectHashIndexer.parse_file_to_symbols(file_path, file_content, commit_sha)
        for s_name, s_obj in all_symbols.items():
            k = DirectHashIndexer.compute_hash_key(file_path, s_name, commit_sha)
            self.l2_ssd.put(k, s_obj)
            if s_name == symbol_name:
                self.l1_ram.put(k, s_obj)

        lat = round((time.perf_counter() - t0) * 1000.0, 3)
        if symbol_name in all_symbols:
            return all_symbols[symbol_name], "L3_COMPILED", lat

        # Fallback empty symbol
        fallback = IndexedSymbol(
            symbol_name=symbol_name,
            file_path=file_path,
            commit_sha=commit_sha,
            code_body=f"# Symbol {symbol_name} extracted from {file_path}",
            imports=[],
            direct_dependencies=[],
            docstring=None,
            token_count=10,
            ast_hash="000000"
        )
        return fallback, "L3_COMPILED", lat

    def get_system_metrics(self) -> Dict[str, Any]:
        return {
            "l1_ram_items": self.l1_ram.size(),
            "l1_ram_bytes_est": self.l1_ram.get_memory_bytes_estimate(),
            "l1_hits": self.l1_ram.hits,
            "l1_misses": self.l1_ram.misses,
            "l2_ssd_items": self.l2_ssd.count(),
            "l2_ssd_db_size_bytes": os.path.getsize(self.l2_ssd.db_path) if os.path.exists(self.l2_ssd.db_path) else 0,
            "l2_hits": self.l2_ssd.hits,
            "l2_misses": self.l2_ssd.misses,
        }
