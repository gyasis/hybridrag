#!/usr/bin/env python3
"""
HybridRAG MCP Server Tests
==========================
Test suite for validating MCP server functionality.

Tests cover:
- Server initialization
- Tool discovery
- Query execution
- Error handling
- Multi-instance scenarios
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

import pytest


# =============================================================================
# Test Configuration
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
MCP_SERVER_PATH = PROJECT_ROOT / "hybridrag_mcp_server.py"
TEST_DB_PATH = PROJECT_ROOT / "databases" / "test_db"


# =============================================================================
# Helper Functions
# =============================================================================

class MCPServerProcess:
    """Context manager for MCP server process"""

    def __init__(self, working_dir: str, name: str = "test"):
        self.working_dir = working_dir
        self.name = name
        self.process = None

    def __enter__(self):
        """Start MCP server"""
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(MCP_SERVER_PATH),
                "--working-dir", self.working_dir,
                "--name", self.name,
                "--log-level", "ERROR"
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        # Wait for server to initialize
        time.sleep(2)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop MCP server"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)

    def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send MCP request and get response"""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }

        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()

        response_line = self.process.stdout.readline()
        return json.loads(response_line)


def create_test_database():
    """Create minimal test database for MCP server"""
    TEST_DB_PATH.mkdir(parents=True, exist_ok=True)

    # Create minimal LightRAG structure
    (TEST_DB_PATH / "vdb_chunks.json").write_text(json.dumps([
        {
            "id": "test1",
            "content": "Test content about authentication using JWT tokens",
            "metadata": {"source": "test"}
        }
    ]))


# =============================================================================
# Tests
# =============================================================================

class TestMCPServerInitialization:
    """Test server initialization and startup"""

    def test_server_requires_working_dir(self):
        """Test that server fails without working directory"""
        result = subprocess.run(
            [sys.executable, str(MCP_SERVER_PATH), "--name", "test"],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0
        assert "required" in result.stderr.lower()

    def test_server_validates_working_dir_exists(self):
        """Test that server validates working directory exists"""
        result = subprocess.run(
            [
                sys.executable, str(MCP_SERVER_PATH),
                "--working-dir", "/nonexistent/path",
                "--name", "test"
            ],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0
        assert "does not exist" in result.stderr.lower()

    def test_server_starts_with_valid_config(self):
        """Test server starts successfully with valid configuration"""
        create_test_database()

        proc = subprocess.Popen(
            [
                sys.executable, str(MCP_SERVER_PATH),
                "--working-dir", str(TEST_DB_PATH),
                "--name", "test"
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            # Wait for initialization
            time.sleep(2)

            # Check process is running
            assert proc.poll() is None, "Server process terminated unexpectedly"

        finally:
            proc.terminate()
            proc.wait(timeout=5)


class TestMCPToolDiscovery:
    """Test MCP tool discovery and listing"""

    def test_list_tools_returns_all_tools(self):
        """Test that list_tools returns all 4 expected tools"""
        create_test_database()

        with MCPServerProcess(str(TEST_DB_PATH)) as server:
            response = server.send_request("tools/list")

            assert "result" in response
            assert "tools" in response["result"]

            tools = response["result"]["tools"]
            tool_names = [t["name"] for t in tools]

            # Verify all 4 tools are present
            expected_tools = [
                "lightrag_local_query",
                "lightrag_global_query",
                "lightrag_hybrid_query",
                "get_database_info"
            ]

            for expected in expected_tools:
                assert expected in tool_names, f"Tool {expected} not found"

    def test_tools_have_descriptions(self):
        """Test that all tools have proper descriptions"""
        create_test_database()

        with MCPServerProcess(str(TEST_DB_PATH)) as server:
            response = server.send_request("tools/list")
            tools = response["result"]["tools"]

            for tool in tools:
                assert "name" in tool
                assert "description" in tool
                assert len(tool["description"]) > 10, f"Tool {tool['name']} has no description"

    def test_tools_have_input_schema(self):
        """Test that all tools have input schemas"""
        create_test_database()

        with MCPServerProcess(str(TEST_DB_PATH)) as server:
            response = server.send_request("tools/list")
            tools = response["result"]["tools"]

            for tool in tools:
                assert "inputSchema" in tool
                assert "type" in tool["inputSchema"]
                assert tool["inputSchema"]["type"] == "object"


class TestMCPQueryExecution:
    """Test query tool execution"""

    def test_get_database_info_succeeds(self):
        """Test get_database_info tool execution"""
        create_test_database()

        with MCPServerProcess(str(TEST_DB_PATH), "test-project") as server:
            response = server.send_request("tools/call", {
                "name": "get_database_info",
                "arguments": {}
            })

            assert "result" in response
            result = response["result"]

            assert result["success"] is True
            assert result["project_name"] == "test-project"
            assert "working_dir" in result
            assert str(TEST_DB_PATH) in result["working_dir"]

    def test_hybrid_query_executes(self):
        """Test hybrid query execution (most common use case)"""
        create_test_database()

        with MCPServerProcess(str(TEST_DB_PATH)) as server:
            response = server.send_request("tools/call", {
                "name": "lightrag_hybrid_query",
                "arguments": {
                    "query": "authentication",
                    "top_k": 10
                }
            })

            assert "result" in response
            result = response["result"]

            assert result["success"] is True
            assert result["mode"] == "hybrid"
            assert "result" in result

    def test_query_with_invalid_parameters_fails_gracefully(self):
        """Test that invalid parameters are handled gracefully"""
        create_test_database()

        with MCPServerProcess(str(TEST_DB_PATH)) as server:
            response = server.send_request("tools/call", {
                "name": "lightrag_local_query",
                "arguments": {
                    "query": "test",
                    "top_k": "not_a_number"  # Invalid type
                }
            })

            # Should return error, not crash
            assert "error" in response or "result" in response


class TestMCPErrorHandling:
    """Test error handling scenarios"""

    def test_uninitialized_rag_returns_error(self):
        """Test that queries return error if LightRAG fails to initialize"""
        # This test would need to mock initialization failure
        # Skipping for now as it requires more complex setup
        pass

    def test_invalid_tool_name_returns_error(self):
        """Test calling nonexistent tool"""
        create_test_database()

        with MCPServerProcess(str(TEST_DB_PATH)) as server:
            response = server.send_request("tools/call", {
                "name": "nonexistent_tool",
                "arguments": {}
            })

            assert "error" in response


class TestMultiInstance:
    """Test multiple MCP server instances"""

    def test_multiple_servers_different_databases(self):
        """Test running multiple servers with different databases"""
        # Create two test databases
        db1 = TEST_DB_PATH.parent / "test_db1"
        db2 = TEST_DB_PATH.parent / "test_db2"

        for db in [db1, db2]:
            db.mkdir(parents=True, exist_ok=True)
            (db / "vdb_chunks.json").write_text(json.dumps([]))

        # Start two servers
        server1 = MCPServerProcess(str(db1), "project1")
        server2 = MCPServerProcess(str(db2), "project2")

        with server1, server2:
            # Query both servers
            info1 = server1.send_request("tools/call", {
                "name": "get_database_info",
                "arguments": {}
            })
            info2 = server2.send_request("tools/call", {
                "name": "get_database_info",
                "arguments": {}
            })

            # Verify different projects
            assert info1["result"]["project_name"] == "project1"
            assert info2["result"]["project_name"] == "project2"


# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """Test performance characteristics"""

    def test_server_startup_time(self):
        """Test server starts within reasonable time"""
        create_test_database()

        start = time.time()

        proc = subprocess.Popen(
            [
                sys.executable, str(MCP_SERVER_PATH),
                "--working-dir", str(TEST_DB_PATH),
                "--name", "test"
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            # Wait for initialization message
            stderr_output = []
            while True:
                line = proc.stderr.readline()
                stderr_output.append(line)
                if "MCP server ready" in line:
                    break
                if time.time() - start > 30:
                    pytest.fail("Server took too long to start (>30s)")

            startup_time = time.time() - start
            print(f"\nServer startup time: {startup_time:.2f}s")

            assert startup_time < 10, f"Server startup took {startup_time}s (expected <10s)"

        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_query_response_time(self):
        """Test query responses within reasonable time"""
        create_test_database()

        with MCPServerProcess(str(TEST_DB_PATH)) as server:
            start = time.time()

            server.send_request("tools/call", {
                "name": "lightrag_hybrid_query",
                "arguments": {"query": "test"}
            })

            response_time = time.time() - start
            print(f"\nQuery response time: {response_time:.2f}s")

            assert response_time < 30, f"Query took {response_time}s (expected <30s)"


# =============================================================================
# Main Test Runner
# =============================================================================

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
