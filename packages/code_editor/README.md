# Code Editor

AI-powered code editing service with Lovable-style tool integration.

## Features

✅ **Multi-level Fuzzy Matching** - 9-tier replacer chain (ported from OpenCode)
- Simple exact match
- Line-trimmed match (trailing whitespace tolerance)
- Block anchor match (first/last line + Levenshtein distance)
- Whitespace normalization
- Indentation flexibility
- Escape character normalization
- Boundary trimming
- Context-aware matching
- Multi-occurrence handling

✅ **Structured Patch System** - Batch code modifications
- Add/Update/Delete files in one operation
- 4-level fuzzy seeking (exact → rstrip → trim → Unicode normalization)
- File move support

✅ **Ripgrep Integration** - Fast code search
- Pattern matching with JSON output
- Glob filtering
- File type filtering

✅ **Docker Sandbox** - Isolated execution
- Resource limits (CPU/memory)
- Network isolation
- Auto cleanup

✅ **Audit Logging** - Security tracking
- Command execution logs
- Dangerous command detection
- Timestamp + session tracking

✅ **File Conflict Prevention** - FileTime mechanism
- Read-time tracking
- Write-time validation
- Stale file detection

## Installation

```bash
cd packages/code_editor
pip install -e .

# Install ripgrep (required for search)
brew install ripgrep  # macOS
# or
apt install ripgrep   # Linux
```

## Quick Start

```python
from code_editor.sandbox import Sandbox
from code_editor.agent import ToolExecutor, TOOLS

# 1. Start sandbox
with Sandbox("/path/to/workspace") as sandbox:
    # 2. Create tool executor
    executor = ToolExecutor(
        workspace="/path/to/workspace",
        session_id="my_session",
        sandbox=sandbox
    )

    # 3. Execute tools
    # Read file
    result = executor.execute("read", {"file_path": "src/app.py"})

    # Edit file (fuzzy matching)
    result = executor.execute("edit", {
        "file_path": "src/app.py",
        "old_string": "def foo():\n    return 42",  # Can be imprecise!
        "new_string": "def foo():\n    return 100"
    })

    # Search code
    result = executor.execute("grep", {
        "pattern": "class.*:",
        "glob": "*.py"
    })

    # Run command
    result = executor.execute("bash", {
        "command": "python -m pytest tests/"
    })
```

## Tools for LLM

Expose these tools to your LLM (OpenAI Function Calling format):

```python
from code_editor.agent import TOOLS

# TOOLS is a list of tool definitions
# Pass to OpenAI API:
response = openai.chat.completions.create(
    model="gpt-4",
    messages=[...],
    tools=TOOLS,
    tool_choice="auto"
)
```

Available tools:
- `read` - Read file content
- `edit` - Modify file with fuzzy matching
- `write` - Create/overwrite file
- `grep` - Search code by pattern
- `glob` - Find files by pattern
- `bash` - Execute shell command (sandboxed)
- `apply_patch` - Apply structured patch

## Architecture

```
┌─────────────────────────────────────────┐
│           LLM (GPT-4/Claude)            │
└────────────────┬────────────────────────┘
                 │ Function Calling
                 ▼
┌─────────────────────────────────────────┐
│         ToolExecutor                    │
│  ┌─────────────────────────────────┐   │
│  │ read → FileTime tracking        │   │
│  │ edit → 9-tier Replacer chain    │   │
│  │ write → Conflict detection      │   │
│  │ grep → ripgrep wrapper          │   │
│  │ bash → Sandbox execution        │   │
│  │ apply_patch → Batch operations  │   │
│  └─────────────────────────────────┘   │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌────────┐  ┌────────┐  ┌──────────┐
│Workspace│  │ Docker │  │Audit Log │
│  /code/ │  │Sandbox │  │ JSON     │
└────────┘  └────────┘  └──────────┘
```

## Testing

```bash
pytest packages/code_editor/code_editor/tests/
```

## Integration with prompt-trading

Add to `services/api/app/routers/`:

```python
from code_editor.agent import ToolExecutor, TOOLS
from code_editor.sandbox import Sandbox

@router.post("/code_edit/execute")
async def execute_tool(
    tool_name: str,
    parameters: dict,
    session_id: str
):
    workspace = f"/tmp/workspace_{session_id}"

    with Sandbox(workspace) as sandbox:
        executor = ToolExecutor(workspace, session_id, sandbox)
        result = executor.execute(tool_name, parameters)
        return result
```

## Security Notes

- ✅ Workspace path validation (prevents `../` attacks)
- ✅ Dangerous command detection (blocks `rm -rf /`, `sudo`, etc.)
- ✅ Docker network isolation
- ✅ Resource limits (CPU/memory)
- ✅ Audit logging
- ⚠️ Sandbox containers are ephemeral (no persistence)
- ⚠️ Code modifications are persistent (stored in workspace)

## References

- OpenCode edit.ts - Multi-level replacer chain
- OpenCode patch/index.ts - Structured patch system
- OpenHands DockerRuntime - Sandbox architecture
