---
title: "OMNIA-Antigravity Ecosystem Assimilation: Product Requirements Document"
type: "Product Requirements Document"
status: "Active"
version: "1.0.0"
date: "2026-09-06"
tags:
  - "omnia"
  - "antigravity"
  - "prd"
  - "quota-arbitrage"
  - "architecture"
---

# Product Requirements Document: OMNIA-Antigravity Ecosystem Assimilation

## 1. Executive Summary & Core Objective

The **OMNIA-Antigravity Ecosystem Assimilation** unifies cloud-hosted Antigravity GUI model quotas (Google Gemini 3.1 Pro / 3.8 Flash, Anthropic Claude Sonnet 4.6, GPT-OSS 120B) with the **OMNIA Vault** execution architecture. 

Historically, cognitive tasks were fragmented: Antigravity IDE leveraged GUI quota pools for conversational reasoning and high-level directives, while Obsidian maintained markdown-centric Second Brain nodes without programmatic AST indexing. This PRD defines the operational unification where Antigravity acts as the cognitive supervisor and orchestrator, routing tasks directly into the **OMNIA Vault**—a unified, AST-grounded, high-velocity codebase execution environment powered by dedicated Model Context Protocol (MCP) daemons and local inference physics.

---

## 2. Problem Statement & Strategic Drivers

1. **Quota Fragmentation & Burn**: Premium cloud LLM quotas (Claude Sonnet 4.6, Gemini 3.1 Pro) are frequently exhausted by low-level code navigation, file parsing, and repetitive search tasks that do not require multi-billion parameter frontier models.
2. **Obsidian Structural Limits**: Obsidian vaults provide excellent human readability but suffer severe friction when acting as programmatic memory for autonomous agents:
   - Text regex and grep fail on complex code symbol relationships.
   - Wiki-links require manual authoring and lack automatic syntactic type checking.
   - Large context windows are bloated by raw markdown ingestion.
3. **Execution Gap**: Disconnection between GUI agent ideation and local containerized deployment (Coolify, Langflow, vLLM) results in manual copy-paste overhead and out-of-sync configuration drifts.

---

## 3. Product Vision & Persona Matrix

### 3.1 Vision Statement
Transform Antigravity from a desktop agent into an integrated hyper-cluster node that drives the OMNIA Vault: an autonomous, self-indexing, self-healing code synthesis and knowledge engine that executes zero-permission development cycles under strict FinOps token ceilings.

### 3.2 User & Agent Personas
| Persona | Classification | Role in Ecosystem |
| :--- | :--- | :--- |
| **Human Operator** | Human-in-the-Loop | High-level directive author, intent specifier (`/build`, `/ship`), strategic stakeholder. |
| **Supervisor Mesh** | Frontier Cloud LLM (`Gemini 3.1 Pro`) | Architectural planning, AST breakdown, verification audit, Genesis interview compiler. |
| **NVIDIA Hermes Agent** | Local High-Throughput Worker | High-velocity code generation, refactoring, and AST transformations on local compute. |
| **PROMPT MASTER** | Compiler Agent | System prompt hardening, few-shot exemplar compiler, JSON schema enforcement. |
| **ECC Harness** | Governance & Consistency Daemon | Stateful checkpointing, TDD sandboxing, rollback execution, and invariant enforcement. |

---

## 4. Functional Requirements

### 4.1 Quota Arbitrage & Adaptive Routing
- **FR-01: Complexity Scoring**: Every user intent or subtask must be evaluated by `hybrid_router.py` with a complexity score (1–10).
- **FR-02: Routing Matrix**:
  - Score $\ge 5$: Route to Cloud Frontier Models (Gemini 3.1 Pro / Claude Sonnet 4.6).
  - Score $< 5$: Route to Local Inference Engines (`vLLM` EAGLE speculative decoding or Ollama).
- **FR-03: Cloud Quota Protection**: When Claude Sonnet 4.6 or Gemini 3.1 Pro reaches $>80\%$ rate limits, the gateway automatically shifts execution bursts to GPT-OSS 120B and local speculative draft heads.

### 4.2 OMNIA Vault Memory & AST Grounding
- **FR-04: Codebase-Memory-MCP**: Transition canonical system memory from raw markdown parsing to `OMNIA_Memory_MCP`.
- **FR-05: Real-Time AST Indexing**: Expose `ast_query_symbols` to inspect classes, functions, interfaces, and decorators across Python, TypeScript, and Rust without loading entire file payloads into LLM context.
- **FR-06: Semantic Vector Store**: Local vector search (`semantic_vector_search`) over code embeddings with sub-100ms similarity retrieval.

### 4.3 Sensory Ingestion & Multimodal Tools
- **FR-07: Sensory MCP Integration**: Expose web extraction via `Crawl4AI`, visual flow automation via `Maxun`, and audio synthesis via `Voice-Box` as native callable tools within the Antigravity agent toolchain.
- **FR-08: Skill Ingestion**: Provide pluggable support for external specialized skills (`humanlayer/skills` and `andrej-karpathy-skills`).

### 4.4 Sandboxing, State Checkpoints & Rollback
- **FR-09: Isolated TDD Sandbox**: Isolated test execution via `tdd_sandbox.py` using isolated Python virtual environments.
- **FR-10: Stateful Rollback**: Automatic checkpoint snapshot before file mutation; rollback on two consecutive test failures.

---

## 5. Non-Functional Requirements & Invariants

- **NFR-01: Latency**: Local routing decisions must resolve in $\le 30\text{ ms}$.
- **NFR-02: Token Overhead Reduction**: AST-guided context extraction must reduce prompt token consumption by $\ge 65\%$ compared to full-file reading.
- **NFR-03: Offline Operation**: Local codebase search, AST navigation, and TDD sandboxing must remain 100% operational in disconnected/offline environments.
- **NFR-04: Zero-Permission Execution**: Strict adherence to AGENT.md Section 22—all operations run autonomously with automated session logging.

---

## 6. Success Metrics & Key Performance Indicators (KPIs)

1. **Quota Efficiency**: $\ge 60\%$ reduction in premium cloud token consumption for structural codebase navigation.
2. **Context Compression**: Token density reduced to $< 25\%$ of raw workspace size via AST symbol projection.
3. **Build Velocity**: Zero-friction `/build` completion from intent ingestion to verified deployment in $< 120\text{ seconds}$.
4. **Reliability**: $100\%$ pass rate across Delivery Gates 1 through 5, with 0 unhandled runtime crashes.
