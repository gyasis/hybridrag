# Tests

Test suite for HybridRAG system components.

## Test Files

- `test_hybridrag.py` - Integration tests for full system
- `test_multiprocess.py` - Tests for multiprocess architecture
- `test_athena_mcp_client.py` - MCP client integration tests
- `test_query.py` / `test_query_fixed.py` - Query interface tests
- `test_simple.py` - Basic functionality tests

## Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_hybridrag.py

# Run with verbose output
pytest -v tests/
```

## Test Coverage

Tests cover:
- Data ingestion pipeline
- Query interface (all modes: local/global/hybrid/naive/mix)
- LightRAG integration
- Multiprocess coordination
- MCP tool integration
- Error handling and edge cases
