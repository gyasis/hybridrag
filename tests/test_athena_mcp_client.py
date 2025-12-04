#!/usr/bin/env python3
"""
Athena MCP Server Test Client with PromptChain + AgenticStepProcessor
===================================================================
Test client to diagnose and fix the Athena LightRAG MCP server connection issues.
Uses PromptChain with AgenticStepProcessor for iterative debugging and problem solving.
"""

import asyncio
import sys
import logging
import os
from pathlib import Path

# Add parent directory for PromptChain imports
sys.path.append(str(Path(__file__).parent.parent))

from promptchain.utils.promptchaining import PromptChain
from promptchain.utils.agentic_step_processor import AgenticStepProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("AthenaMCPTest")

async def test_athena_mcp_server_direct():
    """Test the Athena MCP server by running it directly to see error messages."""
    logger.info("Testing Athena MCP server direct execution...")
    
    try:
        # Test server directly
        import subprocess
        import json
        
        server_path = "/home/gyasis/Documents/code/PromptChain/athena-lightrag/athena_mcp_server.py"
        python_path = "/home/gyasis/Documents/code/PromptChain/athena-lightrag/.venv/bin/python3"
        
        logger.info(f"Testing server at: {server_path}")
        logger.info(f"Using Python: {python_path}")
        
        # Check if files exist
        if not Path(server_path).exists():
            logger.error(f"Server file not found: {server_path}")
            return False
            
        if not Path(python_path).exists():
            logger.error(f"Python interpreter not found: {python_path}")
            return False
        
        # Try to run the server with a timeout
        logger.info("Attempting to start server process...")
        
        process = await asyncio.create_subprocess_exec(
            python_path, server_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/home/gyasis/Documents/code/PromptChain/athena-lightrag"
        )
        
        # Wait a few seconds to see if it starts
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)
            
            logger.info("=== SERVER STDOUT ===")
            if stdout:
                logger.info(stdout.decode())
            else:
                logger.info("No stdout output")
                
            logger.info("=== SERVER STDERR ===")
            if stderr:
                logger.error(stderr.decode())
                return False
            else:
                logger.info("No stderr output")
                
            return True
            
        except asyncio.TimeoutError:
            logger.info("Server process started but didn't exit (this might be good)")
            process.terminate()
            await process.wait()
            return True
            
    except Exception as e:
        logger.error(f"Direct server test failed: {e}")
        return False

async def create_mcp_diagnostic_chain():
    """Create a PromptChain with AgenticStepProcessor for MCP server diagnosis."""
    
    # Create agentic step processor for iterative problem solving
    diagnostic_step = AgenticStepProcessor(
        objective="""
        Diagnose and fix the Athena LightRAG MCP server connection issues.
        
        The server is failing to start properly based on these logs:
        - "Client closed for command" - server process exits immediately
        - "server stored: false" - connection not maintained  
        - "No server info found" - server not responsive
        
        Working server shows:
        - "Successfully connected to stdio server"
        - "server stored: true"
        - "Found 2 tools and 0 prompts"
        
        Your goal is to identify the root cause and suggest specific fixes.
        """,
        max_internal_steps=8,
        model_name="openai/gpt-4o-mini"
    )
    
    # Create the diagnostic chain
    chain = PromptChain(
        models=["openai/gpt-4o-mini"],
        instructions=[
            """
            You are a debugging expert analyzing MCP server connection failures.
            
            The user will provide test results and error information.
            Use your reasoning to identify the problem and suggest specific solutions.
            
            Focus on:
            1. Missing module dependencies
            2. Path and environment issues
            3. FastMCP configuration problems
            4. Python environment conflicts
            
            Input: {input}
            """,
            diagnostic_step,
            """
            Based on the diagnostic analysis, provide:
            1. Root cause identification
            2. Specific fix recommendations
            3. Commands to execute
            4. Verification steps
            
            Input: {input}
            """
        ],
        verbose=True
    )
    
    return chain

async def main():
    """Main test function with iterative problem solving."""
    
    print("🔧 Athena MCP Server Diagnostic Tool")
    print("=" * 50)
    
    # Step 1: Test server directly
    print("\n📋 Step 1: Testing server direct execution...")
    server_works = await test_athena_mcp_server_direct()
    
    # Step 2: Examine the actual server file for missing dependencies
    print("\n📋 Step 2: Checking server dependencies...")
    
    server_path = "/home/gyasis/Documents/code/PromptChain/athena-lightrag/athena_mcp_server.py"
    try:
        with open(server_path, 'r') as f:
            server_content = f.read()
            
        # Look for import statements
        import_lines = [line.strip() for line in server_content.split('\n') if line.strip().startswith('from') or line.strip().startswith('import')]
        
        print("Found imports in server file:")
        for imp in import_lines[:20]:  # Show first 20 imports
            print(f"  {imp}")
            
        # Check for potentially missing modules
        missing_modules = []
        critical_imports = [
            'from lightrag_core import',
            'from agentic_lightrag import', 
            'from context_processor import'
        ]
        
        for critical in critical_imports:
            if critical in server_content:
                module_name = critical.split('from ')[1].split(' import')[0]
                missing_modules.append(module_name)
        
        if missing_modules:
            print(f"\n❌ Potentially missing modules: {missing_modules}")
        
    except Exception as e:
        print(f"❌ Failed to read server file: {e}")
    
    # Step 3: Create diagnostic chain for problem solving
    print("\n📋 Step 3: Running AI diagnostic analysis...")
    
    try:
        chain = await create_mcp_diagnostic_chain()
        
        diagnostic_input = f"""
        MCP Server Diagnosis Results:
        
        Server Path: /home/gyasis/Documents/code/PromptChain/athena-lightrag/athena_mcp_server.py
        Python Path: /home/gyasis/Documents/code/PromptChain/athena-lightrag/.venv/bin/python3
        
        Direct Execution Result: {'SUCCESS' if server_works else 'FAILED'}
        
        Potentially Missing Modules: {missing_modules if 'missing_modules' in locals() else 'Unknown'}
        
        Error Pattern:
        - Client process starts but immediately closes
        - "No server info found" errors
        - Unlike working server that shows "Successfully connected to stdio server"
        
        The server appears to be a FastMCP 2.0 server trying to import custom modules:
        - lightrag_core
        - agentic_lightrag  
        - context_processor
        
        These modules likely don't exist in the athena-lightrag directory.
        
        Provide specific steps to fix this issue.
        """
        
        result = await chain.process_prompt_async(diagnostic_input)
        
        print("\n🤖 AI Diagnostic Analysis:")
        print("=" * 50)
        print(result)
        
        # Step 4: Offer to implement suggested fixes
        print("\n📋 Step 4: Implementation Options")
        print("Based on the analysis above, would you like to:")
        print("1. Create the missing module files")
        print("2. Modify the server to use working dependencies")
        print("3. Test with a simpler MCP server configuration")
        print("\nChoose an option (1-3) or press Enter to skip:")
        
        # For automated testing, we'll choose option 2
        choice = "2"
        print(f"Automatically selecting option {choice}")
        
        if choice == "2":
            await create_simplified_mcp_server()
            
    except Exception as e:
        print(f"❌ Diagnostic chain failed: {e}")
        import traceback
        traceback.print_exc()

async def create_simplified_mcp_server():
    """Create a simplified working MCP server for testing."""
    
    print("\n🛠️  Creating simplified MCP server...")
    
    simplified_server_code = '''#!/usr/bin/env python3
"""
Simplified Athena MCP Server for Testing
======================================
Basic MCP server that works without complex dependencies.
"""

import asyncio
import logging
import json
import sys
from pathlib import Path

# Configure logging to file to avoid stdio conflicts
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='/tmp/simple_athena_mcp.log',
    filemode='w'
)
logger = logging.getLogger(__name__)

try:
    # Try FastMCP first
    from mcp.server.fastmcp.server import FastMCP
    
    mcp = FastMCP("Simple Athena Test Server")
    
    @mcp.tool()
    async def test_query(query: str) -> dict:
        """Simple test query function."""
        logger.info(f"Test query received: {query}")
        return {
            "success": True,
            "result": f"Test response for: {query}",
            "server": "simplified-athena"
        }
    
    @mcp.tool()
    async def server_status() -> dict:
        """Get server status."""
        return {
            "status": "running",
            "server": "simplified-athena",
            "tools": ["test_query", "server_status"]
        }
    
    if __name__ == "__main__":
        logger.info("Starting simplified Athena MCP server...")
        print("Simple Athena MCP Server starting...", file=sys.stderr)
        asyncio.run(mcp.run())

except ImportError as e:
    logger.error(f"FastMCP not available: {e}")
    
    # Fallback to basic stdio MCP
    class SimpleMCPServer:
        def __init__(self):
            self.tools = {
                "test_query": self.test_query,
                "server_status": self.server_status
            }
        
        async def test_query(self, query: str):
            return {
                "success": True,
                "result": f"Fallback response for: {query}",
                "server": "simplified-athena-fallback"
            }
        
        async def server_status(self):
            return {
                "status": "running",
                "server": "simplified-athena-fallback",
                "tools": list(self.tools.keys())
            }
        
        async def run(self):
            logger.info("Starting fallback MCP server...")
            print("Fallback Athena MCP Server starting...", file=sys.stderr)
            
            # Basic MCP protocol handler
            while True:
                try:
                    line = input()
                    if not line:
                        break
                        
                    request = json.loads(line)
                    
                    if request.get("method") == "initialize":
                        response = {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            "result": {
                                "serverInfo": {
                                    "name": "simplified-athena",
                                    "version": "1.0.0"
                                },
                                "capabilities": {
                                    "tools": {}
                                }
                            }
                        }
                        print(json.dumps(response))
                        
                except EOFError:
                    break
                except Exception as e:
                    logger.error(f"Protocol error: {e}")
                    break
    
    if __name__ == "__main__":
        server = SimpleMCPServer()
        asyncio.run(server.run())
'''
    
    # Write simplified server
    simplified_path = "/home/gyasis/Documents/code/PromptChain/athena-lightrag/simple_athena_mcp_server.py"
    
    try:
        with open(simplified_path, 'w') as f:
            f.write(simplified_server_code)
        
        print(f"✅ Created simplified server at: {simplified_path}")
        
        # Test the simplified server
        print("\n🧪 Testing simplified server...")
        await test_simplified_server(simplified_path)
        
    except Exception as e:
        print(f"❌ Failed to create simplified server: {e}")

async def test_simplified_server(server_path):
    """Test the simplified MCP server."""
    
    try:
        python_path = "/home/gyasis/Documents/code/PromptChain/athena-lightrag/.venv/bin/python3"
        
        process = await asyncio.create_subprocess_exec(
            python_path, server_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/home/gyasis/Documents/code/PromptChain/athena-lightrag"
        )
        
        # Give it time to start
        await asyncio.sleep(2)
        
        if process.returncode is None:
            print("✅ Simplified server started successfully!")
            process.terminate()
            await process.wait()
            
            # Now test with PromptChain client
            await test_with_promptchain_client(server_path)
        else:
            stdout, stderr = await process.communicate()
            print(f"❌ Simplified server failed:")
            if stdout:
                print(f"STDOUT: {stdout.decode()}")
            if stderr:
                print(f"STDERR: {stderr.decode()}")
        
    except Exception as e:
        print(f"❌ Simplified server test failed: {e}")

async def test_with_promptchain_client(server_path):
    """Test MCP connection using PromptChain client."""
    
    print("\n🔗 Testing with PromptChain MCP client...")
    
    try:
        # Configure MCP server for PromptChain
        mcp_config = [{
            "id": "athena_test_server",
            "type": "stdio",
            "command": "/home/gyasis/Documents/code/PromptChain/athena-lightrag/.venv/bin/python3",
            "args": [server_path],
            "env": {}
        }]
        
        # Create PromptChain with MCP
        chain = PromptChain(
            models=["openai/gpt-4o-mini"],
            instructions=[
                "You have access to MCP tools. Test the connection by using available tools.",
                "Use any available tools to verify the MCP server is working: {input}"
            ],
            mcp_servers=mcp_config,
            verbose=True
        )
        
        # Connect to MCP
        await chain.connect_mcp_async()
        
        # Test with a simple query
        result = await chain.process_prompt_async("Test the MCP server connection")
        
        print("✅ PromptChain MCP test successful!")
        print(f"Result: {result}")
        
        # Clean up
        await chain.close_mcp_async()
        
    except Exception as e:
        print(f"❌ PromptChain MCP test failed: {e}")
        import traceback
        traceback.print_exc()

# Mark first task as complete and move to next
async def update_progress():
    """Update the todo list progress."""
    # This would be called to mark tasks complete
    pass

if __name__ == "__main__":
    asyncio.run(main())