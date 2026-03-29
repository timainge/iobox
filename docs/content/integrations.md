# Iobox Integration Options

This document outlines various ways to integrate Iobox with agentic AI systems, comparing different approaches and their respective trade-offs.

## Integration Options Overview

| Integration Method | Complexity | Flexibility | Performance | Use Cases |
|-------------------|------------|------------|-------------|-----------|
| Library Import | Low-Medium | High | Excellent | Direct code integration, custom workflows |
| CLI Tool | Low | Medium | Good | Quick integration, separate process execution |
| MCP Framework | Medium | High | Very Good | Complex agentic workflows, state management |
| API Wrapper | Medium | Medium | Good | Remote integration, distributed systems |

## 1. Iobox as a Library

### Overview
This approach involves directly importing Iobox modules into your Python codebase and using the components programmatically.

### Implementation

```python
from iobox.email_search import search_emails
from iobox.auth import get_gmail_service

# Authenticate with Gmail API
service = get_gmail_service()

# Search for emails
results = search_emails(service, "from:newsletter@example.com", max_results=10, days_back=7)

# Process results in your agent code
for email in results:
    # Extract subject, content, etc.
    subject = email.get('subject', 'No subject')
    
    # Perform agent-specific processing
    agent.process_email_content(subject, email)
```

### Advantages
- **Direct Access**: Full access to all functions and features
- **Performance**: No subprocess overhead or serialisation costs
- **Type Safety**: Benefit from Python's type system and editor support
- **Customisation**: Can modify behaviour for specific agent needs

### Limitations
- **Dependency Management**: Must manage Iobox dependencies alongside agent dependencies
- **Version Conflicts**: Potential conflicts between agent and Iobox dependencies
- **Coupling**: Tighter coupling between agent and Iobox codebases

### Best For
- Deep integration where the agent needs fine-grained control over email operations
- Performance-critical applications where overhead must be minimised
- Applications where emails are a core component of the agent's functionality

## 2. Iobox as a CLI Tool

### Overview
This approach involves calling the Iobox CLI from your agent using subprocess or similar mechanisms.

### Implementation with LangChain

```python
from langchain.agents import tool
import subprocess
import json

@tool
def search_emails(query: str, days: int = 7, max_results: int = 10) -> str:
    """
    Search for emails matching the specified query.
    
    Args:
        query: The Gmail search query (e.g., "from:newsletter@example.com")
        days: Number of days back to search for
        max_results: Maximum number of results to return
    
    Returns:
        A string containing the search results
    """
    try:
        result = subprocess.run(
            ["iobox", "search", "-q", query, "-d", str(days), "-m", str(max_results), "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error searching emails: {e.stderr}"

# In your agent code
emails = search_emails("label:important", days=3)
```

### Implementation with AutoGPT

```python
def search_emails(query: str, days: int = 7, max_results: int = 10) -> dict:
    """AutoGPT tool for searching emails using Iobox"""
    command = ["iobox", "search", "-q", query, "-d", str(days), "-m", str(max_results), "--json"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)}

# Register with AutoGPT
TOOLS = {
    "search_emails": search_emails,
    # Other tools...
}
```

### Advantages
- **Isolation**: Runs in a separate process, preventing dependency conflicts
- **Simplicity**: Easy to integrate without understanding Iobox internals
- **Upgradeability**: Can upgrade Iobox independently from the agent
- **Process Separation**: Failures in Iobox won't crash the agent process

### Limitations
- **Performance Overhead**: Subprocess calls add latency
- **Data Serialisation**: Data must be passed through stdout/stdin
- **Error Handling**: Less detailed error information
- **Authentication Flow**: May require separate authentication handling

### Best For
- Quick integration when the agent needs basic email functionality
- Systems where process isolation is important
- Agents where email processing is occasional rather than constant

## 3. Iobox with MCP (Modular Control Protocol)

### Overview
MCP frameworks provide structured communication between agents and tools, allowing for more complex workflows with state management.

### Implementation

```python
from mcp_framework import MCPTool, MCPState, register_tool

@register_tool
class IoboxEmailSearch(MCPTool):
    name = "email_search"
    description = "Searches for emails using Gmail search syntax"
    
    def process(self, state: MCPState, query: str, days: int = 7, max_results: int = 10):
        """Search for emails and update state with results"""
        import subprocess
        
        result = subprocess.run(
            ["iobox", "search", "-q", query, "-d", str(days), "-m", str(max_results), "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse results and update state
        emails = json.loads(result.stdout)
        state.set("email_results", emails)
        state.set("last_search_query", query)
        
        # Return summary for the agent
        return f"Found {len(emails)} emails matching '{query}'"
    
# In agent workflow definition
workflow = [
    {
        "tool": "email_search",
        "params": {"query": "{user_input}", "days": 3},
        "next_step": "email_analysis"
    },
    {
        "tool": "email_analysis",
        "params": {"emails": "{email_results}"},
        "next_step": "summary_generation"
    }
    # ...
]
```

### Advantages
- **State Management**: Maintains context between tool calls
- **Workflow Definition**: Supports complex multi-step processes
- **Declarative Approach**: Separates tool implementation from workflow logic
- **Debugging**: Better visibility into the agent's decision process

### Limitations
- **Framework Dependency**: Requires adopting specific MCP framework
- **Complexity**: More complex to set up initially
- **Learning Curve**: Developers need to understand both Iobox and MCP concepts

### Best For
- Complex agents that need to perform multi-step email processing workflows
- Applications requiring robust state management between steps
- Enterprise use cases where process tracking and debugging are important

## 4. Other Integration Options

### Web API Wrapper

Creating a lightweight API wrapper around Iobox functionality:

```python
from fastapi import FastAPI
import subprocess
import json

app = FastAPI()

@app.post("/search")
async def search_emails(query: str, days: int = 7, max_results: int = 10):
    """API endpoint to search emails using Iobox CLI"""
    result = subprocess.run(
        ["iobox", "search", "-q", query, "-d", str(days), "-m", str(max_results), "--json"],
        capture_output=True,
        text=True,
        check=True
    )
    
    return json.loads(result.stdout)

# Run with: uvicorn api:app --reload
```

Agents can then call this API using standard HTTP requests.

### Advantages
- **Network Isolation**: Complete separation between agent and Iobox
- **Language Agnostic**: Agents can be written in any language
- **Scalability**: API can be deployed independently and scaled
- **Authentication**: Can add API-level authentication/authorization

### Limitations
- **Network Overhead**: HTTP requests add latency
- **Deployment Complexity**: Requires managing an additional service
- **Authentication Flow**: More complex authentication handling

## Recommendations

### For Simple Integration

For agents that need basic email functionality with minimal setup:
- Use the **CLI Tool approach** with subprocess for quick integration
- Consider adding a thin Python wrapper around CLI calls for error handling

### For Deep Integration

For applications where email processing is a core feature:
- Use the **Library Import approach** for maximum flexibility and performance
- Create abstraction layers in your codebase to handle Iobox-specific functionality

### For Enterprise Applications

For complex enterprise agents with sophisticated workflows:
- Use the **MCP Framework approach** for robust state management and workflow definition
- Consider the **Web API approach** for multi-agent systems or cross-language integration

## Implementation Roadmap

To better support agent integration, consider these enhancements to Iobox:

1. Add a `--json` output format option to all CLI commands for easier parsing
2. Create official LangChain and AutoGPT tool wrappers in the Iobox package
3. Develop a simple MCP connector for common agent frameworks
4. Document common integration patterns with examples

## Conclusion

Iobox provides flexible options for integration with agentic systems. The best approach depends on your specific requirements around performance, isolation, and complexity. By understanding these trade-offs, you can choose the integration pattern that best suits your agent architecture.
