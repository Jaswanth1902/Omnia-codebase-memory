import os
import sys
from pathlib import Path, PureWindowsPath, PurePosixPath
import pytest

from cartograph.server import (
    ASTSymbolIndexer,
    _determine_namespace,
    handle_initialize,
    handle_tools_list,
    handle_tool_call,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def indexer(repo_root: Path) -> ASTSymbolIndexer:
    return ASTSymbolIndexer(repo_root)


def test_determine_namespace_cross_platform():
    """Verify namespace determination works identically across Windows and Unix paths."""
    # Group namespaces
    assert _determine_namespace("05_Services/Mesh/node.py") == "Group:Mesh"
    assert _determine_namespace("05_Services\\Mesh\\node.py") == "Group:Mesh"
    assert _determine_namespace("01_Projects/Omnia/core.py") == "Group:Omnia"
    assert _determine_namespace("01_Projects\\Omnia\\core.py") == "Group:Omnia"

    # Private scratchpads
    assert _determine_namespace("scratch/test.py") == "Private:scratch"
    assert _determine_namespace("temp\\.cache\\file.py") == "Private:scratch"

    # Private symbols
    assert _determine_namespace("cartograph/server.py", "_internal") == "Private:cartograph/server.py:_internal"
    assert _determine_namespace("cartograph\\server.py", "_internal") == "Private:cartograph/server.py:_internal"

    # Global
    assert _determine_namespace("cartograph/server.py") == "Global"
    assert _determine_namespace("cartograph\\server.py") == "Global"


def test_canonical_key_standardization(indexer: ASTSymbolIndexer, repo_root: Path):
    """Verify _canonical_key produces deterministic POSIX paths regardless of input formatting."""
    server_path = repo_root / "cartograph" / "server.py"
    expected_rel = "cartograph/server.py"

    # Path object
    assert indexer._canonical_key(server_path) == expected_rel

    # Relative forward slashes
    assert indexer._canonical_key("cartograph/server.py") == expected_rel

    # Relative backslashes (Windows-style)
    assert indexer._canonical_key("cartograph\\server.py") == expected_rel

    # Absolute path
    assert indexer._canonical_key(server_path.resolve()) == expected_rel

    # URI / Dynamic schemas preserved
    assert indexer._canonical_key("memory://dynamic") == "memory://dynamic"


def test_symbol_indexing_and_cache_parity(indexer: ASTSymbolIndexer, repo_root: Path):
    """Verify AST indexing caches using canonical POSIX keys without duplicate entries."""
    server_path = repo_root / "cartograph" / "server.py"
    canonical_key = "cartograph/server.py"

    # Index using Path object
    symbols_1 = indexer.index_file(server_path)
    assert len(symbols_1) > 0

    # Ensure key in symbol_index, file_abstracts, raw_cache is canonical POSIX
    assert canonical_key in indexer.symbol_index
    assert canonical_key in indexer.file_abstracts
    assert canonical_key in indexer.raw_cache
    assert canonical_key in indexer.file_dependencies

    # Verify no raw backslash keys leaked into cache
    assert not any("\\" in k for k in indexer.symbol_index.keys() if "://" not in k)
    assert not any("\\" in k for k in indexer.file_abstracts.keys() if "://" not in k)

    # Re-indexing with Windows backslashes should update the same canonical entry (no duplicates)
    symbols_2 = indexer.index_file("cartograph\\server.py")
    assert len(symbols_2) == len(symbols_1)
    assert len([k for k in indexer.symbol_index.keys() if "cartograph" in k and "server.py" in k]) == 1


def test_get_tier_payload_cross_platform(indexer: ASTSymbolIndexer):
    """Verify get_tier_payload resolves both slash formats seamlessly without cache miss."""
    payload_forward = indexer.get_tier_payload("cartograph/server.py", tier="L1")
    payload_backward = indexer.get_tier_payload("cartograph\\server.py", tier="L1")

    assert payload_forward["tier"] == "L1"
    assert payload_backward["tier"] == "L1"
    assert payload_forward["file"] == "cartograph/server.py"
    assert payload_backward["file"] == "cartograph/server.py"
    assert len(payload_forward["symbols"]) == len(payload_backward["symbols"])
    assert "mermaid_graph" in payload_forward
    assert "flowchart TD" in payload_forward["mermaid_graph"]


def test_read_ast_node_cross_platform(indexer: ASTSymbolIndexer):
    """Verify read_ast_node extracts symbol source using both forward and backward slashes."""
    node_fwd = indexer.read_ast_node("cartograph/server.py", "ASTSymbolIndexer")
    node_bwd = indexer.read_ast_node("cartograph\\server.py", "ASTSymbolIndexer")

    assert "error" not in node_fwd
    assert "error" not in node_bwd
    assert node_fwd["symbol"] == "ASTSymbolIndexer"
    assert node_bwd["symbol"] == "ASTSymbolIndexer"
    assert node_fwd["file"] == "cartograph/server.py"
    assert node_bwd["file"] == "cartograph/server.py"
    assert node_fwd["line"] == node_bwd["line"]
    assert node_fwd["source"] == node_bwd["source"]


def test_get_file_dependencies_cross_platform(indexer: ASTSymbolIndexer):
    """Verify relational dependencies and flowchart mapping work across path styles."""
    dep_fwd = indexer.get_file_dependencies("cartograph/server.py")
    dep_bwd = indexer.get_file_dependencies("cartograph\\server.py")

    assert dep_fwd["file"] == "cartograph/server.py"
    assert dep_bwd["file"] == "cartograph/server.py"
    assert len(dep_fwd["outgoing_edges"]) == len(dep_bwd["outgoing_edges"])
    assert "mermaid_graph" in dep_fwd
    assert "flowchart TD" in dep_fwd["mermaid_graph"]


def test_invalidate_symbol_cross_platform(indexer: ASTSymbolIndexer, repo_root: Path):
    """Verify invalidate_symbol correctly invalidates when given backslash or forward slash path."""
    server_path = repo_root / "cartograph" / "server.py"
    indexer.index_file(server_path)

    # Invalidate using backslash path
    invalidated = indexer.invalidate_symbol("ASTSymbolIndexer", file_path="cartograph\\server.py")
    assert invalidated > 0

    # Temporal graph should reflect invalidation
    temporal = indexer.get_temporal_graph(file_path="cartograph/server.py", symbol_name="ASTSymbolIndexer", include_historical=True)
    assert temporal["active_symbols_count"] > 0
    symbols = temporal["symbols"]
    assert any(s["name"] == "ASTSymbolIndexer" and s["valid_until"] is not None for s in symbols)


def test_traverse_directory_standardized_paths(indexer: ASTSymbolIndexer):
    """Verify traverse_directory returns POSIX file paths across all tiers."""
    res = indexer.traverse_directory("cartograph", tier="L0", max_depth=2)
    assert res["tier"] == "L0"
    assert res["total_files"] > 0
    for item in res["items"]:
        assert "\\" not in item["file"]
        assert item["file"].startswith("cartograph/") or item["file"] == "cartograph"


def test_mcp_handlers_path_standardization(indexer: ASTSymbolIndexer, repo_root: Path):
    """Verify JSON-RPC MCP handlers handle Windows and POSIX paths properly."""
    # get_file_tier with backslashes
    call_res = handle_tool_call(indexer, 10, {
        "name": "get_file_tier",
        "arguments": {"file_path": "cartograph\\server.py", "tier": "L1"}
    })
    assert "result" in call_res
    import json
    parsed = json.loads(call_res["result"]["content"][0]["text"])
    assert parsed["file"] == "cartograph/server.py"

    # read_ast_node with backslashes
    call_node = handle_tool_call(indexer, 11, {
        "name": "read_ast_node",
        "arguments": {"file": "cartograph\\server.py", "symbol": "ASTSymbolIndexer"}
    })
    assert "result" in call_node
    node_data = json.loads(call_node["result"]["content"][0]["text"])
    assert node_data["file"] == "cartograph/server.py"
    assert node_data["symbol"] == "ASTSymbolIndexer"

    # update_symbol_memory with backslashes
    call_update = handle_tool_call(indexer, 12, {
        "name": "update_symbol_memory",
        "arguments": {"file_path": "cartograph\\server.py"}
    })
    assert "result" in call_update
    update_data = json.loads(call_update["result"]["content"][0]["text"])
    assert update_data["status"] == "SUCCESS"
    assert update_data["file"] == "cartograph/server.py"
