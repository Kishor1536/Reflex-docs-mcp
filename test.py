import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Load environment variables (GROQ_API_KEY)
load_dotenv()

# Check for API Key
if not os.getenv("GROQ_API_KEY"):
    print("Error: GROQ_API_KEY not found in .env file")
    sys.exit(1)

from groq import AsyncGroq
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODEL = "qwen/qwen3-32b"
MAX_ITERATIONS = 5  # Prevent infinite loops

async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.reflex_docs_mcp.server"],
        env=None
    )

    print("🔌 Starting MCP Client and connecting to local server...")
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            tools = await session.list_tools()
            print(f"✅ Connected! Found {len(tools.tools)} tools: {[t.name for t in tools.tools]}")

            # Convert MCP Tools to Groq/OpenAI Format
            groq_tools = []
            for tool in tools.tools:
                groq_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })

            client = AsyncGroq()
            
            query = "How does rx.foreach work? Explain with an example."
            print(f"\n❓ User Query: {query}")
            print("🤖 Sending to Groq...")

            messages = [
                {
                    "role": "system", 
                    "content": "You are a helpful assistant with access to Reflex documentation tools. Use them to find accurate information, then provide a clear answer. After getting tool results, synthesize the information into a helpful response."
                },
                {"role": "user", "content": query}
            ]

            # Agentic Loop - keep calling tools until we get a text response
            for iteration in range(MAX_ITERATIONS):
                response = await client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=groq_tools,
                    tool_choice="auto"
                )

                response_message = response.choices[0].message
                tool_calls = response_message.tool_calls

                if not tool_calls:
                    # No tool calls = final answer!
                    print("\n" + "=" * 60)
                    print("📝 FINAL ANSWER:")
                    print("=" * 60)
                    print(response_message.content)
                    print("=" * 60)
                    break
                
                # Process tool calls
                print(f"\n� Iteration {iteration + 1}: Model requested {len(tool_calls)} tool(s)")
                messages.append(response_message)

                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = tool_call.function.arguments
                    
                    print(f"   🛠️  Calling {func_name}...")
                    
                    args = json.loads(func_args) if isinstance(func_args, str) else func_args
                    result = await session.call_tool(func_name, arguments=args)
                    
                    tool_output = result.content[0].text if result.content else "No output"
                    print(f"   ✅ Got {len(tool_output)} chars")

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": func_name,
                        "content": tool_output,
                    })
            else:
                # Hit max iterations
                print(f"\n⚠️ Hit max iterations ({MAX_ITERATIONS}). Last response:")
                print(response_message.content or "(No content)")

if __name__ == "__main__":
    asyncio.run(main())
