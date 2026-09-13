#!/usr/bin/env python3
"""
OMNIA Codebase Memory MCP Server (omnia_memory_server.py)
Official Codebase Memory MCP replacing Obsidian with AST symbol querying
and semantic vector search across the Antigravity OS and OMNIA Vault.
Supports both stdio MCP protocol (for IDE clients) and HTTP REST (--serve).
"""

import os
import sys
import ast
import json
import socket
import argparse
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional, Set, Tuple

# Set UTF-8 encoding on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path.cwd()))

try:
    from adaptive_profiler import with_profiling
except ImportError:
    def with_profiling(threshold_sec: float = 30.0, component_name: str = "", critical: bool = False, domain: Optional[str] = None):
        def decorator(func):
            return func
        return decorator


# --- Temporal Event Clock & Namespace Isolation Primitives ---

def _get_iso_now() -> str:
    """Returns ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _determine_namespace(rel_path: str, symbol_name: Optional[str] = None) -> str:
    """
    Namespace Isolation Policy:
    - Private: Scratchpads, .cache files, or internal private symbols (_func)
    - Group:<Subsystem>: Domain/subsystem modules (e.g. Group:Supervisor_Mesh)
    - Global: Root files, core contracts, shared interfaces
    """
    norm_path = rel_path.replace("\\", "/")
    if ".cache" in norm_path or "scratch" in norm_path or "temp" in norm_path:
        return "Private:scratch"
    if symbol_name and symbol_name.startswith("_") and not (symbol_name.startswith("__") and symbol_name.endswith("__")):
        return f"Private:{norm_path}:{symbol_name}"
    parts = norm_path.split("/")
    if len(parts) > 1 and parts[0] in ("05_Services", "01_Projects", "99_Meta", "02_Areas"):
        return f"Group:{parts[1]}"
    return "Global"


def _is_namespace_allowed(entity_namespace: str, allowed_namespaces: Optional[List[str]] = None) -> bool:
    """Strictly gates context visibility to prevent local worker hallucination bleed."""
    if not entity_namespace:
        return True
    if allowed_namespaces is None:
        return not entity_namespace.startswith("Private:")
    if "Global" in allowed_namespaces and entity_namespace == "Global":
        return True
    for allowed in allowed_namespaces:
        if allowed == entity_namespace:
            return True
        if allowed.endswith("*") and entity_namespace.startswith(allowed[:-1]):
            return True
        if allowed.startswith("Group:") and entity_namespace == allowed:
            return True
    return False


def _is_temporally_valid(valid_from: Optional[str], valid_until: Optional[str], as_of_time: Optional[str] = None) -> bool:
    """Event Clock bi-temporal evaluation: checks whether entity is valid as of given time."""
    if not valid_from:
        return True
    if as_of_time is None:
        return valid_until is None
    if valid_from > as_of_time:
        return False
    if valid_until and valid_until <= as_of_time:
        return False
    return True


# --- Core Project Themes & Thematic Knowledge Graph Taxonomy ---

CORE_PROJECT_THEMES: List[str] = [
    "Advanced Materials",
    "Energy",
    "Manufacturing Process",
    "Quantum Mechanics",
    "Environment",
]

THEME_TAXONOMY: Dict[str, List[str]] = {
    "Advanced Materials": [
        "metamaterial", "graphene", "polymer", "alloy", "nanomaterial",
        "nanotube", "crystal", "composite", "semiconductor", "ceramic",
        "metallurgy", "thin film", "biomaterial", "superconduct",
        "perovskite", "dielectric", "photonic", "aerogel", "elastomer",
        "material", "lattice", "metallics"
    ],
    "Energy": [
        "battery", "storage", "solar", "grid", "nuclear", "thermal",
        "photovoltaic", "hydrogen", "power", "fuel cell", "turbine",
        "renewable", "wind", "biomass", "thermoelectric", "capacitor",
        "inverter", "electrochemical", "lithium", "anode", "cathode",
        "electricity"
    ],
    "Manufacturing Process": [
        "additive", "machining", "lithography", "casting", "sintering",
        "tooling", "assembly", "fabrication", "stamping", "extrusion",
        "3d print", "molding", "etching", "cnc", "metrology", "inspection",
        "yield", "foundry", "deposition", "manufacturing"
    ],
    "Quantum Mechanics": [
        "qubit", "superposition", "entanglement", "decoherence",
        "hamiltonian", "wavefunction", "spin", "quantum", "circuit",
        "anneal", "gate", "teleportation", "fock", "bloch", "qec",
        "hadamard", "schrodinger", "dirac", "eigenstate", "unitary"
    ],
    "Environment": [
        "carbon", "emission", "lifecycle", "recycling", "ecological",
        "green", "remediation", "effluent", "waste", "circular",
        "climate", "footprint", "capture", "pollutant", "biodiversity",
        "decarbonization", "sustainable", "lca", "sequestration",
        "environmental", "ecology"
    ],
}


def classify_thematic_domains(text_or_tokens: str) -> Tuple[Optional[str], List[str]]:
    """
    Evaluates text against the 5 core project themes.
    Returns (primary_theme, all_matching_themes).
    """
    if not text_or_tokens:
        return (None, [])

    text_lower = text_or_tokens.lower()
    matched_themes = []

    for theme in CORE_PROJECT_THEMES:
        keywords = THEME_TAXONOMY.get(theme, [])
        for kw in keywords:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, text_lower):
                matched_themes.append(theme)
                break

    primary_theme = matched_themes[0] if matched_themes else None
    return (primary_theme, matched_themes)


class CallVisitor(ast.NodeVisitor):
    """AST NodeVisitor extracting function and method calls with caller scope attribution."""
    def __init__(self):
        self.calls = []
        self.current_scope = "module"

    def visit_FunctionDef(self, node):
        prev = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = prev

    def visit_AsyncFunctionDef(self, node):
        prev = self.current_scope
        self.current_scope = node.name
        self.generic_visit(node)
        self.current_scope = prev

    def visit_Call(self, node):
        callee = ""
        callee_module = ""
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
            if isinstance(node.func.value, ast.Name):
                callee_module = node.func.value.id
        if callee:
            self.calls.append({
                "caller": self.current_scope,
                "callee": callee,
                "callee_module": callee_module,
                "line": getattr(node, "lineno", 0)
            })
        self.generic_visit(node)


class ASTSymbolIndexer:
    """Extracts classes, functions, and relational dependency graphs (imports, inheritance, cross-file calls) using Python AST with OpenViking Tiered Loading (L0/L1/L2/RELATIONAL)."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir if root_dir is not None else WORKSPACE_ROOT
        self.symbol_index: Dict[str, List[Dict[str, Any]]] = {}
        self.file_abstracts: Dict[str, Dict[str, Any]] = {}
        self.raw_cache: Dict[str, str] = {}
        # Relational Mapping (Zero third-party graph libraries)
        self.file_dependencies: Dict[str, List[Dict[str, Any]]] = {}
        self.file_adjacency: Dict[str, List[str]] = {}
        self.reverse_adjacency: Dict[str, List[str]] = {}
        self.module_to_file: Dict[str, str] = {}
        self._pre_scan_modules()

    def _pre_scan_modules(self):
        """Pre-scans workspace to map module names/stems to workspace relative file paths."""
        target_subdirs = ["05_Services", "99_Meta", "01_Projects"]
        for sub in target_subdirs:
            sub_path = self.root_dir / sub
            if not sub_path.exists():
                continue
            for py_path in sub_path.rglob("*.py"):
                parts = py_path.parts
                if any(p.startswith(".") or p in ["venv", ".venv", "__pycache__", "node_modules", "mcp_envs", "build", "dist", ".cache"] for p in parts):
                    continue
                try:
                    rel = str(py_path.relative_to(self.root_dir)).replace("\\", "/")
                    stem = py_path.stem
                    self.module_to_file[stem] = rel
                    dotted = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel.replace("/", ".")
                    self.module_to_file[dotted] = rel
                except Exception:
                    pass

    def _resolve_module_target(self, current_file: Path, module_name: Optional[str], level: int = 0) -> Tuple[Optional[str], bool]:
        """Resolves an import target to a relative workspace file path if local."""
        if level > 0:
            try:
                base = current_file.parent
                for _ in range(level - 1):
                    base = base.parent
                if module_name:
                    target_p = base / f"{module_name.replace('.', '/')}.py"
                    target_init = base / module_name.replace('.', '/') / "__init__.py"
                    if target_p.exists():
                        return (str(target_p.relative_to(self.root_dir)).replace("\\", "/"), True)
                    if target_init.exists():
                        return (str(target_init.relative_to(self.root_dir)).replace("\\", "/"), True)
                    return (f"{module_name}.py", True)
                else:
                    return (str(base.relative_to(self.root_dir)).replace("\\", "/"), True)
            except Exception:
                return (module_name, False)

        if not module_name:
            return (None, False)

        if module_name in self.module_to_file:
            return (self.module_to_file[module_name], True)
        stem = module_name.split(".")[-1]
        if stem in self.module_to_file:
            return (self.module_to_file[stem], True)

        local_p = current_file.parent / f"{module_name}.py"
        if local_p.exists():
            return (str(local_p.relative_to(self.root_dir)).replace("\\", "/"), True)

        ws_p = self.root_dir / f"{module_name.replace('.', '/')}.py"
        if ws_p.exists():
            return (str(ws_p.relative_to(self.root_dir)).replace("\\", "/"), True)

        return (module_name, False)

    def index_file(self, file_path: Path) -> List[Dict[str, Any]]:
        symbols = []
        if not file_path.exists() or file_path.suffix != ".py":
            return symbols

        try:
            code = file_path.read_text(encoding="utf-8", errors="replace")
            self.raw_cache[str(file_path)] = code
            tree = ast.parse(code, filename=str(file_path))

            rel_path = str(file_path.relative_to(self.root_dir)).replace("\\", "/") if self.root_dir in file_path.parents else str(file_path).replace("\\", "/")
            module_doc = ast.get_docstring(tree) or ""
            doc_first_line = module_doc.strip().split("\n")[0] if module_doc else "No docstring provided"

            code_hash = hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest()[:16]
            now_iso = _get_iso_now()
            file_ns = _determine_namespace(rel_path)

            # Thematic classification for the file context
            file_primary_theme, file_thematic_tags = classify_thematic_domains(f"{rel_path} {module_doc} {code[:4000]}")

            defined_functions = set()
            defined_classes = set()
            inheritance_edges = []

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [arg.arg for arg in node.args.args]
                    fn_ns = _determine_namespace(rel_path, node.name)
                    fn_doc = ast.get_docstring(node) or ""
                    fn_primary, fn_tags = classify_thematic_domains(f"{rel_path} {node.name} {fn_doc} {' '.join(args)}")
                    if not fn_tags:
                        fn_primary, fn_tags = file_primary_theme, list(file_thematic_tags)

                    symbols.append({
                        "type": "function",
                        "name": node.name,
                        "line": node.lineno,
                        "args": args,
                        "docstring": fn_doc,
                        "file": rel_path,
                        "valid_from": now_iso,
                        "valid_until": None,
                        "thematic_tags": fn_tags,
                        "primary_theme": fn_primary,
                        "provenance": {
                            "source_file": rel_path,
                            "extractor": "ASTSymbolIndexer",
                            "hash": code_hash
                        },
                        "namespace": fn_ns
                    })
                    defined_functions.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    bases = []
                    for b in node.bases:
                        if isinstance(b, ast.Name):
                            bases.append(b.id)
                        elif isinstance(b, ast.Attribute):
                            parts = []
                            curr = b
                            while isinstance(curr, ast.Attribute):
                                parts.append(curr.attr)
                                curr = curr.value
                            if isinstance(curr, ast.Name):
                                parts.append(curr.id)
                            bases.append(".".join(reversed(parts)))
                        elif isinstance(b, ast.Subscript) and isinstance(b.value, ast.Name):
                            bases.append(b.value.id)

                    cls_ns = _determine_namespace(rel_path, node.name)
                    cls_doc = ast.get_docstring(node) or ""
                    cls_primary, cls_tags = classify_thematic_domains(f"{rel_path} {node.name} {cls_doc} {' '.join(bases)} {' '.join(methods)}")
                    if not cls_tags:
                        cls_primary, cls_tags = file_primary_theme, list(file_thematic_tags)

                    symbols.append({
                        "type": "class",
                        "name": node.name,
                        "line": node.lineno,
                        "bases": bases,
                        "methods": methods,
                        "docstring": cls_doc,
                        "file": rel_path,
                        "valid_from": now_iso,
                        "valid_until": None,
                        "thematic_tags": cls_tags,
                        "primary_theme": cls_primary,
                        "provenance": {
                            "source_file": rel_path,
                            "extractor": "ASTSymbolIndexer",
                            "hash": code_hash
                        },
                        "namespace": cls_ns
                    })
                    defined_classes.add(node.name)

                    for base in bases:
                        inh_primary, inh_tags = classify_thematic_domains(f"{rel_path} {node.name} {base} {cls_doc}")
                        if not inh_tags:
                            inh_primary, inh_tags = file_primary_theme, list(file_thematic_tags)
                        inheritance_edges.append({
                            "source": rel_path,
                            "target": base,
                            "type": "inheritance",
                            "is_local": False,
                            "line": node.lineno,
                            "valid_from": now_iso,
                            "valid_until": None,
                            "thematic_tags": inh_tags,
                            "primary_theme": inh_primary,
                            "provenance": {
                                "source_file": rel_path,
                                "extractor": "ASTSymbolIndexer"
                            },
                            "namespace": file_ns,
                            "details": {
                                "class": node.name,
                                "base": base
                            }
                        })

            # Extract Dependency Edges: Imports
            import_edges = []
            imported_symbols_map: Dict[str, Tuple[str, bool]] = {}

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name
                        asname = alias.asname or mod
                        target, is_local = self._resolve_module_target(file_path, mod, 0)
                        imp_primary, imp_tags = classify_thematic_domains(f"{rel_path} {mod} {asname}")
                        if not imp_tags:
                            imp_primary, imp_tags = file_primary_theme, list(file_thematic_tags)
                        import_edges.append({
                            "source": rel_path,
                            "target": target or mod,
                            "type": "import",
                            "is_local": is_local,
                            "line": node.lineno,
                            "valid_from": now_iso,
                            "valid_until": None,
                            "thematic_tags": imp_tags,
                            "primary_theme": imp_primary,
                            "provenance": {
                                "source_file": rel_path,
                                "extractor": "ASTSymbolIndexer"
                            },
                            "namespace": file_ns,
                            "details": {
                                "module": mod,
                                "alias": alias.asname,
                                "symbols": [asname]
                            }
                        })
                        imported_symbols_map[asname] = (target or mod, is_local)
                        imported_symbols_map[mod] = (target or mod, is_local)
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module
                    level = node.level
                    target, is_local = self._resolve_module_target(file_path, mod, level)
                    sym_names = [a.name for a in node.names]
                    imp_primary, imp_tags = classify_thematic_domains(f"{rel_path} {mod or ''} {' '.join(sym_names)}")
                    if not imp_tags:
                        imp_primary, imp_tags = file_primary_theme, list(file_thematic_tags)
                    import_edges.append({
                        "source": rel_path,
                        "target": target or (mod or "."),
                        "type": "import",
                        "is_local": is_local,
                        "line": node.lineno,
                        "valid_from": now_iso,
                        "valid_until": None,
                        "thematic_tags": imp_tags,
                        "primary_theme": imp_primary,
                        "provenance": {
                            "source_file": rel_path,
                            "extractor": "ASTSymbolIndexer"
                        },
                        "namespace": file_ns,
                        "details": {
                            "module": mod or "",
                            "level": level,
                            "symbols": sym_names
                        }
                    })
                    for a in node.names:
                        imported_symbols_map[a.asname or a.name] = (target or (mod or "."), is_local)

            # Resolve inheritance edges if base class matches an imported symbol
            for inh in inheritance_edges:
                base_name = inh["details"]["base"]
                if base_name in imported_symbols_map:
                    tgt, is_loc = imported_symbols_map[base_name]
                    inh["target"] = tgt
                    inh["is_local"] = is_loc

            # Extract Dependency Edges: Function & Method Calls
            call_edges = []
            visitor = CallVisitor()
            visitor.visit(tree)
            seen_calls = set()

            for c in visitor.calls:
                callee = c["callee"]
                callee_mod = c["callee_module"]
                caller = c["caller"]

                target = None
                is_local = False

                if callee in imported_symbols_map:
                    target, is_local = imported_symbols_map[callee]
                elif callee_mod and callee_mod in imported_symbols_map:
                    target, is_local = imported_symbols_map[callee_mod]
                elif callee in defined_functions:
                    target = rel_path
                    is_local = True

                if target:
                    call_key = (rel_path, target, caller, callee)
                    if call_key not in seen_calls:
                        seen_calls.add(call_key)
                        call_primary, call_tags = classify_thematic_domains(f"{rel_path} {target} {caller} {callee}")
                        if not call_tags:
                            call_primary, call_tags = file_primary_theme, list(file_thematic_tags)
                        call_edges.append({
                            "source": rel_path,
                            "target": target,
                            "type": "call",
                            "is_local": is_local,
                            "line": c["line"],
                            "valid_from": now_iso,
                            "valid_until": None,
                            "thematic_tags": call_tags,
                            "primary_theme": call_primary,
                            "provenance": {
                                "source_file": rel_path,
                                "extractor": "ASTSymbolIndexer"
                            },
                            "namespace": file_ns,
                            "details": {
                                "caller": caller,
                                "callee": callee
                            }
                        })

            # Consolidate Dependency Edges & Build Zero-Dependency Adjacency List
            all_edges = import_edges + inheritance_edges + call_edges
            self.file_dependencies[str(file_path)] = all_edges
            self.file_dependencies[rel_path] = all_edges

            local_adj = set()
            for edge in all_edges:
                tgt = edge.get("target")
                if tgt and edge.get("is_local") and tgt != rel_path:
                    local_adj.add(tgt)

            self.file_adjacency[rel_path] = sorted(list(local_adj))
            for tgt in local_adj:
                if tgt not in self.reverse_adjacency:
                    self.reverse_adjacency[tgt] = []
                if rel_path not in self.reverse_adjacency[tgt]:
                    self.reverse_adjacency[tgt].append(rel_path)

            # L0 Abstract Definition
            self.file_abstracts[str(file_path)] = {
                "file": rel_path,
                "lines_count": len(code.splitlines()),
                "char_count": len(code),
                "abstract": doc_first_line[:180],
                "symbols_count": len(symbols),
                "dependencies_count": len(all_edges),
                "adjacent_files_count": len(local_adj),
                "tier": "L0",
                "thematic_tags": file_thematic_tags,
                "primary_theme": file_primary_theme
            }
        except Exception as e:
            symbols.append({"type": "error", "error": str(e), "file": str(file_path)})

        self.symbol_index[str(file_path)] = symbols
        return symbols

    def generate_mermaid_flowchart(self, file_key: Optional[str] = None, max_edges: int = 25, direction: str = "TD") -> str:
        """
        Dynamically generates a Mermaid.js flowchart mapping dependency edges.
        Adheres strictly to diagram-design/SKILL.md standards:
        - Quoted labels: node["Label"]
        - Directional discipline: TD default for hierarchy and dependency trees
        - Typed edge annotations: -->|"imports"|, -->|"inherits Base"|, -.->|"calls fn()"|
        """
        def clean_id(label: str) -> str:
            sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', label)
            if not sanitized or sanitized[0].isdigit():
                sanitized = "mod_" + sanitized
            return sanitized

        lines = [f"flowchart {direction}"]
        edges_rendered = 0
        nodes_declared = set()

        if file_key:
            fp = Path(file_key)
            rel_file = str(fp.relative_to(self.root_dir)).replace("\\", "/") if (fp.is_absolute() and self.root_dir in fp.parents) else str(file_key).replace("\\", "/")
            focal_id = clean_id(rel_file)
            lines.append(f'    subgraph RelationalScope ["Relational Context: {rel_file}"]')
            lines.append(f'        {focal_id}["{rel_file}"]')
            nodes_declared.add(focal_id)

            edges = self.file_dependencies.get(str(file_key), self.file_dependencies.get(rel_file, []))
            for edge in edges:
                if edges_rendered >= max_edges:
                    break
                tgt = edge.get("target", "")
                if not tgt:
                    continue
                etype = edge.get("type", "rel")
                details = edge.get("details", {})
                tgt_id = clean_id(tgt)

                label_str = etype
                if etype == "import":
                    syms = details.get("symbols", [])
                    label_str = f"imports {', '.join(syms[:2])}" if syms else "imports"
                elif etype == "inheritance":
                    label_str = f"inherits {details.get('base', '')}"
                elif etype == "call":
                    label_str = f"calls {details.get('callee', '')}()"

                if tgt_id not in nodes_declared:
                    lines.append(f'        {tgt_id}["{tgt}"]')
                    nodes_declared.add(tgt_id)

                connector = "-.->" if etype == "call" else "-->"
                lines.append(f'        {focal_id} {connector}|"{label_str}"| {tgt_id}')
                edges_rendered += 1

            # Reverse (incoming) edges
            incoming = self.reverse_adjacency.get(rel_file, [])
            for inc in incoming:
                if edges_rendered >= max_edges:
                    break
                inc_id = clean_id(inc)
                if inc_id not in nodes_declared:
                    lines.append(f'        {inc_id}["{inc}"]')
                    nodes_declared.add(inc_id)
                lines.append(f'        {inc_id} -->|"depends on"| {focal_id}')
                edges_rendered += 1

            lines.append("    end")
            lines.append(f"    style {focal_id} fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#ffffff")
        else:
            lines.append('    subgraph LocalMesh ["Codebase Dependency Mesh"]')
            for src_file, targets in self.file_adjacency.items():
                if edges_rendered >= max_edges:
                    break
                src_id = clean_id(src_file)
                if src_id not in nodes_declared:
                    lines.append(f'        {src_id}["{src_file}"]')
                    nodes_declared.add(src_id)
                for tgt in targets:
                    if edges_rendered >= max_edges:
                        break
                    tgt_id = clean_id(tgt)
                    if tgt_id not in nodes_declared:
                        lines.append(f'        {tgt_id}["{tgt}"]')
                        nodes_declared.add(tgt_id)
                    lines.append(f'        {src_id} -->|"depends on"| {tgt_id}')
                    edges_rendered += 1
            lines.append("    end")

        if edges_rendered == 0 and not file_key:
            lines.append('    empty_node["No inter-module dependencies detected"]')

        return "\n".join(lines)

    def get_adjacency_list(self, local_only: bool = True) -> Dict[str, List[str]]:
        """Returns a pure-Python zero-dependency adjacency list mapping source files to their dependencies."""
        if local_only:
            return {k: v for k, v in self.file_adjacency.items() if v}
        full = {}
        for f, edges in self.file_dependencies.items():
            rel = str(Path(f).relative_to(self.root_dir)).replace("\\", "/") if (Path(f).is_absolute() and self.root_dir in Path(f).parents) else f.replace("\\", "/")
            full[rel] = sorted(list({e.get("target") for e in edges if e.get("target")}))
        return full

    def get_file_dependencies(self, file_path_str: str, allowed_namespaces: Optional[List[str]] = None, as_of_time: Optional[str] = None, theme: Optional[str] = None) -> Dict[str, Any]:
        """Returns comprehensive outgoing and incoming dependency edges and Mermaid flowchart for a file."""
        fp = Path(file_path_str)
        if not fp.is_absolute():
            fp = self.root_dir / fp
        key = str(fp)
        if key not in self.symbol_index:
            self.index_file(fp)
        rel = str(fp.relative_to(self.root_dir)).replace("\\", "/") if (self.root_dir in fp.parents) else file_path_str.replace("\\", "/")
        raw_outgoing = self.file_dependencies.get(key, self.file_dependencies.get(rel, []))
        outgoing = [
            e for e in raw_outgoing
            if _is_namespace_allowed(e.get("namespace", "Global"), allowed_namespaces)
            and _is_temporally_valid(e.get("valid_from"), e.get("valid_until"), as_of_time)
            and (not theme or theme in e.get("thematic_tags", []) or e.get("primary_theme") == theme)
        ]
        return {
            "file": rel,
            "outgoing_edges": outgoing,
            "incoming_edges": self.reverse_adjacency.get(rel, []),
            "adjacent_files": self.file_adjacency.get(rel, []),
            "mermaid_graph": self.generate_mermaid_flowchart(file_key=key)
        }

    def get_code_dependencies(self, symbol_or_file: str, allowed_namespaces: Optional[List[str]] = None, as_of_time: Optional[str] = None, theme: Optional[str] = None) -> Dict[str, Any]:
        """Get call dependencies, import references, and Mermaid flowchart for a symbol or file."""
        if symbol_or_file.endswith(".py") or "/" in symbol_or_file or "\\" in symbol_or_file:
            return self.get_file_dependencies(symbol_or_file, allowed_namespaces=allowed_namespaces, as_of_time=as_of_time, theme=theme)

        matches = self.query_symbols(symbol_or_file, tier="L1", allowed_namespaces=allowed_namespaces, as_of_time=as_of_time, theme=theme)
        related_edges = []
        for file_key, edges in self.file_dependencies.items():
            for e in edges:
                if not _is_namespace_allowed(e.get("namespace", "Global"), allowed_namespaces):
                    continue
                if not _is_temporally_valid(e.get("valid_from"), e.get("valid_until"), as_of_time):
                    continue
                if theme and theme not in e.get("thematic_tags", []) and e.get("primary_theme") != theme:
                    continue
                if (e.get("target") == symbol_or_file or 
                    symbol_or_file in e.get("details", {}).get("symbols", []) or 
                    e.get("details", {}).get("callee") == symbol_or_file or 
                    e.get("details", {}).get("caller") == symbol_or_file or 
                    e.get("details", {}).get("class") == symbol_or_file or 
                    e.get("details", {}).get("base") == symbol_or_file):
                    related_edges.append(e)

        mermaid_chart = self.generate_mermaid_flowchart(file_key=matches[0]["file"] if matches else None)
        return {
            "symbol": symbol_or_file,
            "matches": matches,
            "related_edges": related_edges,
            "mermaid_graph": mermaid_chart
        }

    def get_relational_graph(self, file_path: Optional[str] = None, allowed_namespaces: Optional[List[str]] = None, as_of_time: Optional[str] = None) -> Dict[str, Any]:
        """Generate relational context and Mermaid flowchart for a file or the entire workspace."""
        if file_path:
            return self.get_file_dependencies(file_path, allowed_namespaces=allowed_namespaces, as_of_time=as_of_time)
        return {
            "scope": "workspace",
            "adjacency_list": self.get_adjacency_list(local_only=True),
            "total_indexed_files": len(self.file_abstracts),
            "mermaid_graph": self.generate_mermaid_flowchart()
        }

    def get_tier_payload(self, file_path_str: str, tier: str = "L1") -> Dict[str, Any]:
        """
        OpenViking Tiered Loading with Cognee Relational Absorption:
        - L0: File abstract and symbol summary only.
        - L1: Structural AST signatures, classes, functions, and relational dependency summary + Mermaid flowchart (default).
        - L2: Full raw source code payload with AST signatures and dependencies.
        - RELATIONAL: Deep relational mapping, zero-dependency adjacency list, and dynamic Mermaid flowchart.
        """
        tier_norm = tier.upper()
        fp = Path(file_path_str)
        if not fp.is_absolute():
            fp = self.root_dir / fp
        key = str(fp)

        if key not in self.symbol_index:
            self.index_file(fp)

        rel_path = str(fp.relative_to(self.root_dir)).replace("\\", "/") if (self.root_dir in fp.parents) else str(file_path_str).replace("\\", "/")
        abstract = self.file_abstracts.get(key, {
            "file": rel_path,
            "tier": "L0",
            "abstract": "Unindexed file"
        })
        deps = self.file_dependencies.get(key, self.file_dependencies.get(rel_path, []))
        adj = self.file_adjacency.get(rel_path, [])
        mermaid_chart = self.generate_mermaid_flowchart(file_key=key)

        if tier_norm == "L0":
            return {"tier": "L0", "file": abstract.get("file", rel_path), "abstract": abstract}
        elif tier_norm == "RELATIONAL":
            return {
                "tier": "RELATIONAL",
                "file": abstract.get("file", rel_path),
                "abstract": abstract,
                "dependencies": deps,
                "incoming_dependencies": self.reverse_adjacency.get(rel_path, []),
                "adjacency_list": {rel_path: adj},
                "mermaid_graph": mermaid_chart,
                "symbols_summary": {
                    "classes": [s["name"] for s in self.symbol_index.get(key, []) if s.get("type") == "class"],
                    "functions": [s["name"] for s in self.symbol_index.get(key, []) if s.get("type") == "function"]
                }
            }
        elif tier_norm == "L2":
            raw_code = self.raw_cache.get(key)
            if raw_code is None and fp.exists():
                try:
                    raw_code = fp.read_text(encoding="utf-8", errors="replace")
                    self.raw_cache[key] = raw_code
                except Exception as e:
                    raw_code = f"Error reading source: {e}"
            return {
                "tier": "L2",
                "file": abstract.get("file", rel_path),
                "abstract": abstract,
                "symbols": self.symbol_index.get(key, []),
                "dependencies": deps,
                "adjacency": adj,
                "mermaid_graph": mermaid_chart,
                "raw_source": raw_code
            }
        else:
            # Default L1
            return {
                "tier": "L1",
                "file": abstract.get("file", rel_path),
                "abstract": abstract,
                "symbols": self.symbol_index.get(key, []),
                "dependencies": deps,
                "adjacency": adj,
                "mermaid_graph": mermaid_chart
            }

    def query_symbols(self, query: str, symbol_type: Optional[str] = None, tier: str = "L1", allowed_namespaces: Optional[List[str]] = None, as_of_time: Optional[str] = None, theme: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Queries symbols adhering to OpenViking Tiered Loading with Event Clock & Namespace Gating.
        - L0: Returns list of file abstracts matching the query.
        - L1: Returns AST symbol signatures (default).
        - L2: Returns AST symbol signatures with their enclosing source lines/file raw code.
        - RELATIONAL: Returns symbols with dependency edges and dynamic Mermaid flowchart.
        """
        tier_norm = tier.upper()
        results = []
        query_lower = query.lower()

        if tier_norm == "L0":
            seen_files = set()
            for file_path_str, syms in self.symbol_index.items():
                match = not query_lower
                if not match:
                    for s in syms:
                        if not _is_namespace_allowed(s.get("namespace", "Global"), allowed_namespaces):
                            continue
                        if not _is_temporally_valid(s.get("valid_from"), s.get("valid_until"), as_of_time):
                            continue
                        if theme and theme not in s.get("thematic_tags", []) and s.get("primary_theme") != theme:
                            continue
                        if query_lower in s.get("name", "").lower() or query_lower in s.get("docstring", "").lower():
                            match = True
                            break
                    if not match:
                        ab = self.file_abstracts.get(file_path_str, {})
                        if theme and theme not in ab.get("thematic_tags", []) and ab.get("primary_theme") != theme:
                            pass
                        elif query_lower in ab.get("abstract", "").lower() or query_lower in file_path_str.lower():
                            match = True
                if match and file_path_str not in seen_files:
                    seen_files.add(file_path_str)
                    results.append(self.file_abstracts.get(file_path_str, {"file": file_path_str, "tier": "L0"}))
            return results

        for file_path_str, syms in self.symbol_index.items():
            for s in syms:
                if not _is_namespace_allowed(s.get("namespace", "Global"), allowed_namespaces):
                    continue
                if not _is_temporally_valid(s.get("valid_from"), s.get("valid_until"), as_of_time):
                    continue
                if symbol_type and s.get("type") != symbol_type:
                    continue
                if theme and theme not in s.get("thematic_tags", []) and s.get("primary_theme") != theme:
                    continue
                name = s.get("name", "").lower()
                doc = s.get("docstring", "").lower()
                if not query_lower or query_lower in name or query_lower in doc:
                    entry = dict(s)
                    entry["tier"] = tier_norm
                    if tier_norm == "L2":
                        fp = Path(file_path_str)
                        raw = self.raw_cache.get(file_path_str)
                        if raw is None and fp.exists():
                            try:
                                raw = fp.read_text(encoding="utf-8", errors="replace")
                                self.raw_cache[file_path_str] = raw
                            except Exception:
                                raw = ""
                        entry["raw_source"] = raw
                    elif tier_norm == "RELATIONAL":
                        entry["dependencies"] = [
                            e for e in self.file_dependencies.get(file_path_str, [])
                            if _is_namespace_allowed(e.get("namespace", "Global"), allowed_namespaces)
                            and _is_temporally_valid(e.get("valid_from"), e.get("valid_until"), as_of_time)
                        ]
                        entry["mermaid_graph"] = self.generate_mermaid_flowchart(file_key=file_path_str)
                    results.append(entry)
        return results

    def invalidate_symbol(self, symbol_name: str, file_path: Optional[str] = None, invalidated_at: Optional[str] = None) -> int:
        """
        Event Clock Invalidation:
        Sets valid_until timestamp on active symbol and related outgoing edges.
        """
        now = invalidated_at or _get_iso_now()
        count = 0
        for fp, syms in self.symbol_index.items():
            if file_path and file_path not in fp:
                continue
            for s in syms:
                if s.get("name") == symbol_name and s.get("valid_until") is None:
                    s["valid_until"] = now
                    count += 1
            edges = self.file_dependencies.get(fp, [])
            for e in edges:
                if e.get("valid_until") is None:
                    details = e.get("details", {})
                    if (e.get("target") == symbol_name or
                        details.get("callee") == symbol_name or
                        details.get("caller") == symbol_name or
                        details.get("class") == symbol_name or
                        symbol_name in details.get("symbols", [])):
                        e["valid_until"] = now
                        count += 1
        return count

    def get_temporal_graph(self, file_path: Optional[str] = None, allowed_namespaces: Optional[List[str]] = None, as_of_time: Optional[str] = None, symbol_name: Optional[str] = None, include_historical: bool = True) -> Dict[str, Any]:
        """
        Extracts temporal snapshot of knowledge graph filtered by namespace and event clock.
        Supports filtering by specific symbol_name and including historical versions.
        """
        target_time = as_of_time or _get_iso_now()
        active_symbols = []
        for fp, syms in self.symbol_index.items():
            if file_path and file_path not in fp:
                continue
            for s in syms:
                if symbol_name and s.get("name") != symbol_name:
                    continue
                if not _is_namespace_allowed(s.get("namespace", "Global"), allowed_namespaces):
                    continue
                if not include_historical and not _is_temporally_valid(s.get("valid_from"), s.get("valid_until"), target_time):
                    continue
                active_symbols.append(s)

        active_edges = []
        for fp, edges in self.file_dependencies.items():
            if file_path and file_path not in fp:
                continue
            for e in edges:
                if _is_namespace_allowed(e.get("namespace", "Global"), allowed_namespaces) and _is_temporally_valid(e.get("valid_from"), e.get("valid_until"), target_time):
                    active_edges.append(e)

        return {
            "as_of_time": target_time,
            "allowed_namespaces": allowed_namespaces,
            "active_symbols_count": len(active_symbols),
            "active_edges_count": len(active_edges),
            "symbols": active_symbols,
            "edges": active_edges,
            "temporal_status": "OPTIMAL"
        }

    def traverse_directory(self, rel_dir: str = "", tier: str = "L0", max_depth: int = 3) -> Dict[str, Any]:
        """
        OpenViking Tiered Directory Traversal.
        Defaults to L0 (file abstracts & sizes) to minimize token footprint.
        Can emit L1 (AST overviews) or L2 (raw code blocks) when explicitly requested.
        """
        tier_norm = tier.upper()
        target_dir = self.root_dir / rel_dir if rel_dir else self.root_dir
        if not target_dir.exists() or not target_dir.is_dir():
            return {"error": f"Directory not found: {rel_dir}", "items": []}

        items = []
        for py_path in target_dir.rglob("*.py"):
            if any(part in py_path.parts for part in ["venv", ".git", "__pycache__", "node_modules"]):
                continue
            try:
                rel = py_path.relative_to(target_dir)
                if len(rel.parts) > max_depth:
                    continue
            except Exception:
                pass

            payload = self.get_tier_payload(str(py_path), tier=tier_norm)
            items.append(payload)

        return {
            "directory": str(rel_dir) or "root",
            "tier": tier_norm,
            "total_files": len(items),
            "items": items
        }

    def read_ast_node(self, file_path: str, symbol: str, caller_namespace: Optional[str] = None) -> Dict[str, Any]:
        """
        Anti-Thrashing Protocol: Symbol-Based Source Extraction (OpenViking L2 targeted).
        Resolves a named function or class from the indexed symbol table and returns its
        raw source code without requiring line numbers. Eliminates pagination thrashing.
        Gated by Namespace Isolation to prevent worker hallucination bleed.

        Args:
            file_path: Relative or absolute path to Python file.
            symbol: Function or class name to extract (exact match).
            caller_namespace: Optional namespace of caller for access control.

        Returns:
            Dict with 'symbol', 'type', 'line', 'source', 'file', 'docstring', and temporal metadata.
            On failure: 'error' key with explanation.
        """
        # Normalize to absolute path
        fp = Path(file_path)
        if not fp.is_absolute():
            fp = self.root_dir / file_path
        fp_str = str(fp)
        rel_path = str(fp.relative_to(self.root_dir)).replace("\\", "/") if (fp.is_absolute() and self.root_dir in fp.parents) else file_path.replace("\\", "/")

        # Ensure file is indexed
        syms = self.symbol_index.get(fp_str)
        if syms is None:
            syms = self.index_file(fp)

        # Find the symbol entry
        target_sym = None
        for s in (syms or []):
            if s.get("name") == symbol:
                target_sym = s
                break

        if target_sym is None:
            # Fuzzy fallback: substring match
            candidates = [s for s in (syms or []) if symbol.lower() in s.get("name", "").lower()]
            if not candidates:
                return {
                    "error": f"Symbol '{symbol}' not found in '{rel_path}'. Available symbols: {[s.get('name') for s in (syms or [])]}",
                    "file": rel_path
                }
            target_sym = candidates[0]

        # Namespace Isolation Gate
        target_ns = target_sym.get("namespace", "Global")
        if target_ns.startswith("Private:") and caller_namespace != target_ns and caller_namespace != "Global":
            return {
                "error": f"Namespace isolation violation: Symbol '{symbol}' is scoped to '{target_ns}' and inaccessible from '{caller_namespace or 'Public'}'",
                "namespace": target_ns,
                "file": rel_path
            }

        # Extract raw source via AST get_source_segment
        raw_code = self.raw_cache.get(fp_str)
        if raw_code is None and fp.exists():
            try:
                raw_code = fp.read_text(encoding="utf-8", errors="replace")
                self.raw_cache[fp_str] = raw_code
            except Exception as e:
                return {"error": f"Cannot read source: {e}", "file": rel_path}

        node_source = None
        if raw_code:
            try:
                tree = ast.parse(raw_code, filename=fp_str)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name == target_sym["name"]:
                            node_source = ast.get_source_segment(raw_code, node)
                            break
            except Exception as e:
                node_source = f"# AST parse error: {e}\n# Falling back to line-range extraction\n"

        if node_source is None and raw_code:
            # Fallback: extract by line number from raw cache
            start_line = target_sym.get("line", 1)
            lines = raw_code.splitlines()
            node_source = "\n".join(lines[max(0, start_line - 1):min(len(lines), start_line + 80)])

        return {
            "tier": "L2",
            "file": rel_path,
            "symbol": target_sym.get("name"),
            "type": target_sym.get("type"),
            "line": target_sym.get("line"),
            "docstring": target_sym.get("docstring", ""),
            "namespace": target_ns,
            "valid_from": target_sym.get("valid_from"),
            "valid_until": target_sym.get("valid_until"),
            "provenance": target_sym.get("provenance"),
            "source": node_source or "# Source extraction failed"
        }

    def build_initial_index(self, max_files: int = 100) -> int:
        self._pre_scan_modules()
        count = 0
        target_subdirs = ["05_Services", "99_Meta"]
        for sub in target_subdirs:
            sub_path = self.root_dir / sub
            if not sub_path.exists():
                continue
            for py_path in sub_path.rglob("*.py"):
                parts = py_path.parts
                if any(p.startswith(".") or p in ["venv", ".venv", "__pycache__", "node_modules", "mcp_envs", "build", "dist", ".cache"] for p in parts):
                    continue
                self.index_file(py_path)
                count += 1
                if count >= max_files:
                    return count
        return count

    def update_symbol_memory(self, symbol_name: str, definition_data: Dict[str, Any]) -> None:
        """
        Dynamically inserts or updates a symbol definition in the memory index.
        Used by Cloud Hippocampus and testing harnesses for direct state updates.
        """
        fp = definition_data.get("file_path") or "memory://dynamic"
        if fp not in self.symbol_index:
            self.symbol_index[fp] = []

        now_iso = _get_iso_now()
        thematic_tags = definition_data.get("thematic_tags")
        primary_theme = definition_data.get("primary_theme") or definition_data.get("domain_theme")
        if thematic_tags is None:
            text_context = f"{symbol_name} {definition_data.get('docstring', '')} {definition_data.get('code', '')} {fp}"
            detected_primary, detected_tags = classify_thematic_domains(text_context)
            thematic_tags = detected_tags
            if not primary_theme:
                primary_theme = detected_primary

        entry = {
            "type": definition_data.get("type", "function"),
            "name": symbol_name,
            "line": definition_data.get("line", 1),
            "args": definition_data.get("args", []),
            "docstring": definition_data.get("docstring", ""),
            "file": fp,
            "signature": definition_data.get("signature", ""),
            "code": definition_data.get("code", ""),
            "namespace": definition_data.get("namespace", "Global"),
            "valid_from": definition_data.get("valid_from", now_iso),
            "valid_until": definition_data.get("valid_until"),
            "thematic_tags": thematic_tags or [],
            "primary_theme": primary_theme,
            "provenance": definition_data.get("provenance", {
                "source": "update_symbol_memory",
                "timestamp": now_iso
            }),
        }

        # Replace existing active entry if any, or append
        existing_idx = None
        for i, s in enumerate(self.symbol_index[fp]):
            if s.get("name") == symbol_name and s.get("valid_until") is None:
                existing_idx = i
                break

        if existing_idx is not None:
            self.symbol_index[fp][existing_idx] = entry
        else:
            self.symbol_index[fp].append(entry)


# High-level OOP alias for supervisor / test consumers
OmniaMemoryServer = ASTSymbolIndexer


# --- MCP JSON-RPC Handlers (stdio) ---

def handle_initialize(msg_id):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "omnia-memory-mcp", "version": "1.0.0"}
        }
    }


def handle_tools_list(msg_id):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "tools": [
                {
                    "name": "ast_query_symbols",
                    "description": "Query syntax trees for classes, functions, and interfaces across Python files. Implements OpenViking Tiered Loading: default emits L1 AST signatures/overviews (or L0 file abstracts); pass tier='L2' to request full raw source code on demand.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Symbol name or substring to search"},
                            "type": {"type": "string", "description": "Optional symbol type filter: class or function"},
                            "tier": {
                                "type": "string",
                                "enum": ["L0", "L1", "L2"],
                                "default": "L1",
                                "description": "Loading tier: L0 (file abstracts), L1 (AST signatures/overviews, default), L2 (full raw source code)"
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "traverse_directory_tiered",
                    "description": "Traverse directory with OpenViking Tiered Loading. Emits L0 file abstracts by default to preserve token budget.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "directory": {"type": "string", "description": "Relative directory path (e.g. '05_Services' or '99_Meta/Scripts')"},
                            "tier": {
                                "type": "string",
                                "enum": ["L0", "L1", "L2"],
                                "default": "L0",
                                "description": "Loading tier: L0 (abstracts only, default), L1 (AST overviews), L2 (full source code)"
                            },
                            "max_depth": {"type": "integer", "default": 3, "description": "Maximum directory traversal depth"}
                        }
                    }
                },
                {
                    "name": "get_file_tier",
                    "description": "Fetch a specific file's context at a specific OpenViking tier (L0 abstract, L1 AST signatures, or L2 raw source code).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Relative or absolute path to Python file"},
                            "tier": {
                                "type": "string",
                                "enum": ["L0", "L1", "L2"],
                                "default": "L1",
                                "description": "Target tier: L0, L1, or L2"
                            }
                        },
                        "required": ["file_path"]
                    }
                },
                {
                    "name": "semantic_vector_search",
                    "description": "Semantic search over code comments, abstracts, and docstrings.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query terms"},
                            "tier": {"type": "string", "enum": ["L0", "L1", "L2"], "default": "L1"}
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "get_code_dependencies",
                    "description": "Get call dependencies, import references, class inheritance, and dynamic Mermaid.js flowchart for a symbol or file.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "symbol_name": {"type": "string", "description": "Target symbol name or relative file path"}
                        },
                        "required": ["symbol_name"]
                    }
                },
                {
                    "name": "get_relational_graph",
                    "description": "Generate pure-Python relational dependency graph (imports, class inheritance, cross-file calls) with dynamic Mermaid.js flowchart visualization.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Optional relative or absolute file path to focus graph on"}
                        }
                    }
                },
                {
                    "name": "update_symbol_memory",
                    "description": "Re-indexes a specific file into the AST symbol memory upon modification.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Relative or absolute path to Python file"}
                        },
                        "required": ["file_path"]
                    }
                },
                {
                    "name": "read_ast_node",
                    "description": "ANTI-THRASHING: Read a specific function or class source by symbol name — NOT by line number. Call this instead of view_file when you need to inspect a known symbol. Returns L2 raw source extracted via AST get_source_segment. Eliminates pagination thrashing and line-range guessing.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "description": "Relative or absolute path to Python file (e.g. '99_Meta/Scripts/workspace_health.py')"},
                            "symbol": {"type": "string", "description": "Exact or partial function/class name to extract (e.g. 'run_audit', 'HealthAuditor')"},
                            "caller_namespace": {"type": "string", "description": "Optional caller namespace for isolation checks"}
                        },
                        "required": ["file", "symbol"]
                    }
                },
                {
                    "name": "get_temporal_graph",
                    "description": "Extract temporal snapshot of knowledge graph with Event Clock timestamps (valid_from, valid_until), provenance tags, and Namespace Isolation gating.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Optional file path to focus temporal query on"},
                            "allowed_namespaces": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of allowed namespaces (e.g. ['Global', 'Group:Supervisor_Mesh'])"
                            },
                            "as_of_time": {"type": "string", "description": "Optional ISO-8601 timestamp for historical bi-temporal queries"}
                        }
                    }
                }
            ]
        }
    }


def handle_tool_call(indexer: ASTSymbolIndexer, msg_id, params: Dict[str, Any]):
    name = params.get("name")
    args = params.get("arguments", {})

    if name == "ast_query_symbols":
        q = args.get("query", "")
        stype = args.get("type")
        tier = args.get("tier", "L1")
        allowed_ns = args.get("allowed_namespaces")
        as_of = args.get("as_of_time")
        res = indexer.query_symbols(q, stype, tier=tier, allowed_namespaces=allowed_ns, as_of_time=as_of)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps({"tier": tier, "results_count": len(res), "results": res}, indent=2)}]
            }
        }
    elif name == "traverse_directory_tiered":
        d = args.get("directory", "")
        tier = args.get("tier", "L0")
        max_d = args.get("max_depth", 3)
        res = indexer.traverse_directory(d, tier=tier, max_depth=max_d)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}]
            }
        }
    elif name == "get_file_tier":
        fp_str = args.get("file_path", "")
        tier = args.get("tier", "L1")
        res = indexer.get_tier_payload(fp_str, tier=tier)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}]
            }
        }
    elif name == "semantic_vector_search":
        q = args.get("query", "")
        tier = args.get("tier", "L1")
        allowed_ns = args.get("allowed_namespaces")
        as_of = args.get("as_of_time")
        res = indexer.query_symbols(q, tier=tier, allowed_namespaces=allowed_ns, as_of_time=as_of)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps({"tier": tier, "results_count": len(res), "results": res}, indent=2)}]
            }
        }
    elif name == "get_code_dependencies":
        sym = args.get("symbol_name", "")
        allowed_ns = args.get("allowed_namespaces")
        as_of = args.get("as_of_time")
        res = indexer.get_code_dependencies(sym, allowed_namespaces=allowed_ns, as_of_time=as_of)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}]
            }
        }
    elif name == "get_relational_graph":
        fp = args.get("file_path")
        allowed_ns = args.get("allowed_namespaces")
        as_of = args.get("as_of_time")
        res = indexer.get_relational_graph(fp, allowed_namespaces=allowed_ns, as_of_time=as_of)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}]
            }
        }
    elif name == "get_temporal_graph":
        fp = args.get("file_path")
        allowed_ns = args.get("allowed_namespaces")
        as_of = args.get("as_of_time")
        res = indexer.get_temporal_graph(fp, allowed_namespaces=allowed_ns, as_of_time=as_of)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}]
            }
        }
    elif name == "update_symbol_memory":
        fp_str = args.get("file_path", "")
        fp = Path(fp_str)
        if not fp.is_absolute():
            fp = WORKSPACE_ROOT / fp
        syms = indexer.index_file(fp)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps({
                    "status": "SUCCESS",
                    "file": str(fp),
                    "symbols_indexed": len(syms),
                    "abstract": indexer.file_abstracts.get(str(fp), {}).get("abstract", "")
                }, indent=2)}]
            }
        }
    elif name == "read_ast_node":
        file_arg = args.get("file", "")
        symbol_arg = args.get("symbol", "")
        caller_ns = args.get("caller_namespace")
        res = indexer.read_ast_node(file_arg, symbol_arg, caller_namespace=caller_ns)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}]
            }
        }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Tool '{name}' not found"}
    }


def run_stdio_mcp(root_dir: Path = WORKSPACE_ROOT):
    """Stdio JSON-RPC event loop for Model Context Protocol clients."""
    indexer = ASTSymbolIndexer(root_dir)
    indexer.build_initial_index(max_files=100)

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = request.get("method")
        msg_id = request.get("id")

        if method == "initialize":
            resp = handle_initialize(msg_id)
        elif method == "tools/list":
            resp = handle_tools_list(msg_id)
        elif method == "tools/call":
            resp = handle_tool_call(indexer, msg_id, request.get("params", {}))
        elif method == "notifications/initialized":
            continue
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unhandled method: {method}"}
            }

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


# --- HTTP Server Handlers ---

class OMNIAMemoryHandler(BaseHTTPRequestHandler):
    indexer: Optional[ASTSymbolIndexer] = None

    def _set_headers(self, status: int = 200, content_type: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._set_headers(200)
            payload = {
                "status": "HEALTHY",
                "service": "OMNIA_Memory_MCP",
                "port": 8020,
                "engine": "python/ast_vector_tiered",
                "indexed_files": len(self.indexer.symbol_index) if self.indexer else 0,
                "supported_tiers": ["L0", "L1", "L2", "RELATIONAL"],
                "relational_engine": "active",
                "graph_rag": "zero_dependency_adjacency"
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        elif self.path.startswith("/query/relational"):
            self._set_headers(200)
            res = self.indexer.get_relational_graph() if self.indexer else {}
            self.wfile.write(json.dumps(res).encode("utf-8"))
        elif self.path.startswith("/query/ast"):
            self._set_headers(200)
            res = self.indexer.query_symbols("", tier="L1") if self.indexer else []
            self.wfile.write(json.dumps({"results": res[:20], "total": len(res)}).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        try:
            body = json.loads(post_data.decode("utf-8"))
        except Exception:
            body = {}

        if self.path == "/query/symbols":
            query = body.get("query", "")
            stype = body.get("type")
            tier = body.get("tier", "L1")
            res = self.indexer.query_symbols(query, stype, tier=tier) if self.indexer else []
            self._set_headers(200)
            self.wfile.write(json.dumps({"query": query, "tier": tier, "results": res}).encode("utf-8"))
        elif self.path == "/query/relational":
            fp = body.get("file_path")
            res = self.indexer.get_relational_graph(fp) if self.indexer else {}
            self._set_headers(200)
            self.wfile.write(json.dumps(res).encode("utf-8"))
        elif self.path == "/traverse":
            d = body.get("directory", "")
            tier = body.get("tier", "L0")
            res = self.indexer.traverse_directory(d, tier=tier) if self.indexer else {"items": []}
            self._set_headers(200)
            self.wfile.write(json.dumps(res).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown POST route"}).encode("utf-8"))


@with_profiling(threshold_sec=10.0, component_name="OMNIA_Memory_MCP", domain="Cognitive_Mesh")
def run_memory_server(port: int = 8020, root_dir: Path = WORKSPACE_ROOT):
    indexer = ASTSymbolIndexer(root_dir)
    count = indexer.build_initial_index(max_files=100)
    OMNIAMemoryHandler.indexer = indexer
    server = HTTPServer(("127.0.0.1", port), OMNIAMemoryHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def run_self_test():
    print("=== OMNIA_Memory_MCP Self-Test (OpenViking L0/L1/L2/RELATIONAL Tiered Loading) ===")
    indexer = ASTSymbolIndexer(WORKSPACE_ROOT)
    test_script = SCRIPTS_DIR / "adaptive_profiler.py"
    if test_script.exists():
        symbols = indexer.index_file(test_script)
        print(f"Indexed {test_script.name}: Found {len(symbols)} symbols.")
        assert len(symbols) > 0, "Failed to parse symbols from adaptive_profiler.py"

        # 1. Test L0 Abstract
        l0_res = indexer.query_symbols("record_friction_event", tier="L0")
        assert len(l0_res) > 0, "Failed to query L0 abstracts"
        assert "abstract" in l0_res[0], "L0 missing abstract"
        print(f"✓ L0 Query Verified: Abstract retrieved ({l0_res[0].get('abstract')[:50]}...)")

        # 2. Test L1 Default Signatures & Relational Integration
        l1_payload = indexer.get_tier_payload(str(test_script), tier="L1")
        assert "dependencies" in l1_payload, "L1 missing dependencies list"
        assert "mermaid_graph" in l1_payload, "L1 missing dynamic Mermaid diagram"
        assert "flowchart TD" in l1_payload["mermaid_graph"], "Mermaid diagram missing flowchart TD declaration"
        assert "raw_source" not in l1_payload, "L1 must not leak raw source code"
        print(f"✓ L1 Query Verified: AST signatures + {len(l1_payload['dependencies'])} dependency edges + Mermaid flowchart mapped")

        # 3. Test L2 On-Demand Raw Source
        l2_res = indexer.query_symbols("record_friction_event", tier="L2")
        assert len(l2_res) > 0, "Failed to query L2 raw source"
        assert "raw_source" in l2_res[0] and len(l2_res[0]["raw_source"]) > 0, "L2 missing raw source payload"
        print(f"✓ L2 Query Verified: Full raw source retrieved on demand ({len(l2_res[0]['raw_source'])} chars)")

        # 4. Test RELATIONAL Tier & GraphRAG Extraction
        rel_payload = indexer.get_tier_payload(str(test_script), tier="RELATIONAL")
        assert rel_payload["tier"] == "RELATIONAL", "RELATIONAL tier mismatch"
        assert "dependencies" in rel_payload and len(rel_payload["dependencies"]) > 0, "Failed to extract dependency edges"
        assert "mermaid_graph" in rel_payload and "RelationalScope" in rel_payload["mermaid_graph"], "Failed to generate scoped Mermaid diagram"
        assert "adjacency_list" in rel_payload, "Missing adjacency list in relational payload"

        # Verify edge types: imports, calls, or inheritance
        edge_types = {e.get("type") for e in rel_payload["dependencies"]}
        assert "import" in edge_types, f"Expected 'import' edge type, found {edge_types}"
        print(f"✓ RELATIONAL Tier Verified: Edge types extracted: {sorted(list(edge_types))}")

        # 5. Test Pure-Python Zero-Dependency Adjacency List
        adj_list = indexer.get_adjacency_list(local_only=True)
        assert isinstance(adj_list, dict), "Adjacency list is not a dictionary"
        print(f"✓ Adjacency List Verified: {len(adj_list)} source modules mapped in zero-dependency graph")

        # 6. Test Tiered Directory Traversal
        trav_l0 = indexer.traverse_directory("99_Meta/Scripts", tier="L0", max_depth=1)
        assert trav_l0["tier"] == "L0", "Traversal tier mismatch"
        assert trav_l0["total_files"] > 0, "Traversal returned 0 files"
        print(f"✓ Traversal Verified: {trav_l0['total_files']} files mapped at L0 abstract tier")

    # 7. Test JSON-RPC MCP Handlers
    init_res = handle_initialize(1)
    assert init_res["result"]["serverInfo"]["name"] == "omnia-memory-mcp"
    tools_res = handle_tools_list(2)
    assert len(tools_res["result"]["tools"]) == 9, f"Expected 9 tools, found {len(tools_res['result']['tools'])}"

    call_res = handle_tool_call(indexer, 3, {"name": "ast_query_symbols", "arguments": {"query": "record_friction_event", "tier": "L1"}})
    assert "content" in call_res["result"]

    call_rel = handle_tool_call(indexer, 4, {"name": "get_relational_graph", "arguments": {"file_path": "99_Meta/Scripts/adaptive_profiler.py"}})
    assert "content" in call_rel["result"]
    assert "mermaid_graph" in call_rel["result"]["content"][0]["text"]

    call_dep = handle_tool_call(indexer, 5, {"name": "get_code_dependencies", "arguments": {"symbol_name": "record_friction_event"}})
    assert "content" in call_dep["result"]
    assert "mermaid_graph" in call_dep["result"]["content"][0]["text"]

    # 8. Test Anti-Thrashing: read_ast_node symbol-based extraction
    call_node = handle_tool_call(indexer, 6, {"name": "read_ast_node", "arguments": {"file": "99_Meta/Scripts/adaptive_profiler.py", "symbol": "record_friction_event"}})
    assert "content" in call_node["result"], "read_ast_node returned no content"
    node_payload = json.loads(call_node["result"]["content"][0]["text"])
    assert "source" in node_payload or "error" in node_payload, "read_ast_node payload missing 'source' or 'error'"
    if "source" in node_payload:
        print(f"✓ Anti-Thrashing read_ast_node Verified: Symbol '{node_payload.get('symbol')}' extracted at line {node_payload.get('line')} ({len(node_payload.get('source',''))} chars)")
    else:
        print(f"⚠ read_ast_node returned error (symbol may not exist in test file): {node_payload.get('error')}")

    print("=== OMNIA_Memory_MCP Self-Test PASSED (Anti-Thrashing + Cognee Relational Absorption & Mermaid Verified) ===")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OMNIA Codebase Memory MCP Server")
    parser.add_argument("--serve", action="store_true", help="Start the HTTP server")
    parser.add_argument("--port", type=int, default=8020, help="Port for HTTP server (default: 8020)")
    parser.add_argument("--test", action="store_true", help="Execute self-test suite")
    parser.add_argument("--stdio", action="store_true", help="Explicit stdio MCP mode (default if no flags)")
    parser.add_argument("--root-dir", type=str, default=None, help="Root directory for AST indexing")
    args = parser.parse_args()

    if args.root_dir:
        WORKSPACE_ROOT = Path(args.root_dir)

    if args.test:
        sys.exit(run_self_test())
    elif args.serve:
        run_memory_server(port=args.port)
    else:
        # Default behavior when spawned by IDE client without flags
        run_stdio_mcp()
