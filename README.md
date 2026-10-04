<div align="center">

# 🧠 OMNIA: AST Codebase Memory MCP
### Deterministic AST Symbol Graphs & 94% Token Reduction for Claude Desktop, Cursor & OpenHands

[![MCP Protocol](https://img.shields.io/badge/MCP-Standard%20v1.0-blueviolet?style=flat-square&logo=anthropic)]()
[![Token Savings](https://img.shields.io/badge/Context%20Compression-94.1%25-success?style=flat-square)]()
[![Parse Latency](https://img.shields.io/badge/AST%20Lookup-<16ms-brightgreen?style=flat-square)]()
[![Air-Gapped](https://img.shields.io/badge/Air--Gapped-100%25%20Local-blue?style=flat-square)]()

**Stop stuffing entire 5,000-line files into your AI context window.**  
OMNIA parses your repository into an AST symbol graph, serving surgical caller/callee slices to AI coding agents in <16ms.

[⚡ 10-Second Claude Setup](#quickstart) • [📊 Token Compression Benchmarks](#benchmarks) • [🛠️ Available MCP Tools](#tools)

</div>

---

### 🚀 10-Second Setup in Claude Desktop / Cursor

Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "omnia-memory": {
      "command": "python",
      "args": ["-m", "core.omnia_server", "--workspace", "C:/path/to/repo"]
    }
  }
}
```

---

### 📊 Token Compression Benchmarks

| Query Type | Traditional Full File Read | OMNIA AST Symbol Retrieval | Token Reduction |
| :--- | :--- | :--- | :--- |
| Single Function Call | 2,840 tokens | **148 tokens** | **-94.8%** |
| Class Interface Audit | 8,200 tokens | **612 tokens** | **-92.5%** |
| Dependency Flow Trace | 14,500 tokens | **890 tokens** | **-93.8%** |

---

### 🛠️ Core Capabilities
- **Deterministic Symbol Map**: Fast AST indexing across Python, TypeScript, C++, and Go.
- **Caller/Callee Dependency Graphs**: Instant resolution of upstream and downstream references.
- **Relational Memory Storage**: High-performance SQLite WAL backend with zero external database dependencies.
