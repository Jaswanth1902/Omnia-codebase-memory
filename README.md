# 🧠 OMNIA — AST-Grounded Codebase Memory MCP Server

[![MCP Protocol](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol%20(MCP)-blueviolet?style=flat-square)](https://github.com/Jaswanth1902/omnia-codebase-memory)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue?style=flat-square&logo=python)](https://github.com/Jaswanth1902/omnia-codebase-memory)
[![AST Indexing](https://img.shields.io/badge/Lookup%20Latency-%3C10ms-brightgreen?style=flat-square)](https://github.com/Jaswanth1902/omnia-codebase-memory)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

**OMNIA** is a deterministic, high-velocity **Codebase Memory & Symbol Navigation MCP Server** designed for AI coding agents (Claude Desktop, Cursor, Antigravity IDE, Windsurf). Instead of bloating context windows with brute-force grep and multi-megabyte markdown summaries, OMNIA extracts exact **Abstract Syntax Tree (AST)** symbol topologies, call graphs, and incremental delta updates on file save.

```
       ┌─────────────────────────────────────────────────────────────┐
       │                   AI Coding Agent Client                    │
       │           (Claude Code / Cursor / Antigravity)              │
       └──────────────────────────────┬──────────────────────────────┘
                                      │ Stdio / HTTP MCP Protocol
                                      ▼
       ┌─────────────────────────────────────────────────────────────┐
       │             OMNIA Memory MCP Server Engine                  │
       ├──────────────────────────────┬──────────────────────────────┤
       │  AST Symbol Extraction Engine │  Local Vector Store Adapter  │
       │  (Functions, Classes, Imports)│  (Qdrant / Episodic SQLite) │
       └──────────────────────────────┴──────────────────────────────┘
```

---

## 💡 Why I Built This

As someone learning to build with modern AI coding tools (Claude, Cursor, Windsurf), I noticed how quickly agent workflows slow down and burn through expensive token limits by blindly grepping files or dumping giant markdown files into context.

I built **OMNIA** to improve developer Quality of Life (QOL) with a clean, creative solution:
- **Instant & Deterministic**: Uses Python's native AST parser to locate exact function and class signatures in `<10ms` without token waste.
- **Zero Heavyweight Bloat**: Built purely on Python standard library AST — no massive Language Server Protocol (LSP) daemons or compilation steps.
- **Plug-and-Play**: Connects seamlessly to Claude Desktop, Cursor, or custom agents with standard Model Context Protocol (MCP).

This project is open-source and free for anyone who wants their AI coding assistants to be faster, sharper, and lighter!

---

## ⚡ Why OMNIA?

Traditional agent memory systems either suffer from **Markdown Context Bloat** (dumping raw docs into the prompt) or **Grep Blindness** (failing on multi-line signatures, inheritance, and indirect references).

- **Syntactic Grounding**: Traverses Python ASTs natively using the standard library `ast` module. No compilation or heavyweight Language Server Protocol (LSP) dependencies required.
- **Zero-Latency Invalidation**: Incremental single-file re-indexing triggers upon file save (`<10ms` response).
- **Dual Transport Protocols**: Runs via standard **Stdio** (for local IDE plugins) and **HTTP REST** (for containerized or network agent swarms).
- **Episodic & Vector Dual-Memory**: Ships with built-in adapters for local **Qdrant** vector search and SQLite episodic trajectory memory (`engrim`).

---

## 🛠️ MCP Tools Provided

| MCP Tool | Description | Input Arguments |
| :--- | :--- | :--- |
| `query_symbol_definitions` | Retrieve exact line ranges, docstrings, and signatures for a symbol. | `symbol_name`, `file_pattern` |
| `find_symbol_references` | Trace all callers, invocations, and imports of a class or function. | `symbol_name`, `max_depth` |
| `get_codebase_graph` | Export a high-level AST dependency graph of a target module. | `root_directory`, `format` |
| `semantic_code_search` | Natural language semantic search across indexed symbols. | `query`, `top_k` |
| `update_symbol_memory` | Incrementally re-index modified files into the vector/AST cache. | `file_path`, `content` |

---

## 🚀 Quickstart

### 1. Installation
```bash
git clone https://github.com/Jaswanth1902/omnia-codebase-memory.git
cd omnia-codebase-memory

# Install in editable mode
pip install -e .
```

### 2. Run via Stdio (CLI)
```bash
python omnia_cli.py
```

### 3. Run as Standalone HTTP Server
```bash
python omnia_cli.py --serve --port 8020
```

---

## 🔌 IDE & Client Configuration

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "omnia-memory": {
      "command": "python",
      "args": [
        "-m",
        "omnia.server"
      ],
      "env": {
        "WORKSPACE_ROOT": "C:\\path\\to\\your\\project"
      }
    }
  }
}
```

### Cursor / Antigravity IDE (`mcp_config.json`)
```json
{
  "mcpServers": {
    "omnia-memory": {
      "command": "omnia-memory",
      "args": [],
      "env": {
        "WORKSPACE_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

---

## 📁 Repository Structure

```text
omnia-codebase-memory/
├── omnia/
│   ├── __init__.py          # Package initialization
│   ├── server.py            # Core AST parsing & MCP protocol handler
│   ├── engrim_adapter.py    # Episodic SQLite memory driver
│   └── qdrant_adapter.py    # Semantic vector search connector
├── docs/
│   ├── PRD.md               # Product Requirements Document
│   ├── architecture.md      # Detailed system architecture
│   └── Architecture-essentials.md
├── omnia_cli.py             # CLI runner entrypoint
├── pyproject.toml           # Packaging and build specification
├── LICENSE                  # MIT License
└── README.md
```

---

## 📄 License

Distributed under the [MIT License](LICENSE). Copyright (c) 2026 Jaswanth Reddy.
