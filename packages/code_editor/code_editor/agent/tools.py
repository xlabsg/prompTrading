"""
LLM 工具定义和执行器

提供给 LLM 的工具集（OpenAI Function Calling 格式）
"""

import os
from typing import Dict, List, Any, Optional
from ..core.editor import replace, EditError
from ..core.patcher import apply_patch, PatchError
from ..tools.file_ops import read_file, write_file, validate_workspace_path, FileOperationError
from ..tools.search import grep, glob_files, format_grep_output, SearchError
from ..tools.bash import execute_bash, format_bash_output, BashError, AuditLogger
from ..sandbox.docker_sandbox import Sandbox, SandboxError


# ============= 工具定义（OpenAI Function Calling 格式）=============

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "读取文件内容。使用前必须先用 glob 或 grep 确认文件存在。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件的绝对路径"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始行号（可选，从 0 开始）"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "读取行数（可选）"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "修改文件内容。使用 SEARCH/REPLACE 模式，支持多级模糊匹配。必须先用 read 读取文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件的绝对路径"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要替换的文本（可以不完全精确，但需要包含足够上下文）"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的文本（必须与 old_string 不同）"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换所有出现（默认 false，只替换唯一匹配）"
                    }
                },
                "required": ["file_path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "创建新文件或覆写现有文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件的绝对路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "文件内容"
                    }
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "在代码中搜索正则表达式模式。返回匹配的文件和行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式模式"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（默认当前工作空间）"
                    },
                    "glob": {
                        "type": "string",
                        "description": "文件模式过滤（如 '*.py'）"
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "description": "是否忽略大小写"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "按文件名模式查找文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "glob 模式（如 '**/*.py' 查找所有 Python 文件）"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（默认当前工作空间）"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在沙箱中执行 Bash 命令。禁止危险命令（rm -rf /、sudo 等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 Bash 命令"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒，默认 30）"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "应用结构化补丁，支持批量修改多个文件（Add/Update/Delete）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "patch_text": {
                        "type": "string",
                        "description": "Patch 文本（*** Begin Patch ... *** End Patch 格式）"
                    },
                    "strict_add": {
                        "type": "boolean",
                        "description": "新增文件是否严格模式（存在则报错）。默认 false"
                    }
                },
                "required": ["patch_text"]
            }
        }
    }
]


# ============= 工具执行器 =============

class ToolExecutor:
    """
    工具执行器 - 解析 LLM 输出并调用对应工具
    """

    def __init__(
        self,
        workspace: str,
        session_id: str,
        sandbox: Optional[Sandbox] = None,
        audit_log_file: Optional[str] = None
    ):
        """
        初始化工具执行器

        Args:
            workspace: 工作空间根目录
            session_id: 会话 ID
            sandbox: 沙箱实例（可选，如果不需要执行 bash）
            audit_log_file: 审计日志文件路径
        """
        self.workspace = os.path.abspath(workspace)
        self.session_id = session_id
        self.sandbox = sandbox
        self.audit_logger = AuditLogger(audit_log_file) if audit_log_file else None

        # 文件内容缓存（用于 edit 工具）
        self._file_cache: Dict[str, str] = {}

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具

        Args:
            tool_name: 工具名称
            parameters: 工具参数

        Returns:
            {
                'success': bool,
                'output': str,
                'error': str (如果失败)
            }
        """
        try:
            if tool_name == "read":
                return self._execute_read(parameters)
            elif tool_name == "edit":
                return self._execute_edit(parameters)
            elif tool_name == "write":
                return self._execute_write(parameters)
            elif tool_name == "grep":
                return self._execute_grep(parameters)
            elif tool_name == "glob":
                return self._execute_glob(parameters)
            elif tool_name == "bash":
                return self._execute_bash(parameters)
            elif tool_name == "apply_patch":
                return self._execute_apply_patch(parameters)
            else:
                return {
                    'success': False,
                    'error': f"Unknown tool: {tool_name}"
                }

        except Exception as e:
            return {
                'success': False,
                'error': f"{type(e).__name__}: {str(e)}"
            }

    def _execute_read(self, params: Dict) -> Dict:
        """执行 read 工具"""
        file_path = params['file_path']
        validate_workspace_path(file_path, self.workspace)

        content = read_file(
            filepath=file_path,
            session_id=self.session_id,
            offset=params.get('offset'),
            limit=params.get('limit')
        )

        # 缓存文件内容（供 edit 使用）
        self._file_cache[file_path] = content

        return {
            'success': True,
            'output': content
        }

    def _execute_edit(self, params: Dict) -> Dict:
        """执行 edit 工具"""
        file_path = params['file_path']
        validate_workspace_path(file_path, self.workspace)

        # 读取文件内容
        if file_path not in self._file_cache:
            content = read_file(file_path, self.session_id)
        else:
            # 使用缓存的内容（去掉行号）
            cached = self._file_cache[file_path]
            content = '\n'.join(
                line.split('→', 1)[1] if '→' in line else line
                for line in cached.split('\n')
            )

        # 执行替换
        new_content = replace(
            content=content,
            old_string=params['old_string'],
            new_string=params['new_string'],
            replace_all=params.get('replace_all', False)
        )

        # 写回文件
        write_file(file_path, new_content, self.session_id)

        return {
            'success': True,
            'output': f"Successfully edited {file_path}"
        }

    def _execute_write(self, params: Dict) -> Dict:
        """执行 write 工具"""
        file_path = params['file_path']
        validate_workspace_path(file_path, self.workspace)

        write_file(file_path, params['content'], self.session_id)

        return {
            'success': True,
            'output': f"Successfully wrote {file_path}"
        }

    def _execute_grep(self, params: Dict) -> Dict:
        """执行 grep 工具"""
        path = params.get('path', self.workspace)
        validate_workspace_path(path, self.workspace)

        matches = grep(
            pattern=params['pattern'],
            path=path,
            glob=params.get('glob'),
            ignore_case=params.get('ignore_case', False)
        )

        output = format_grep_output(matches)

        return {
            'success': True,
            'output': output,
            'matches_count': len(matches)
        }

    def _execute_glob(self, params: Dict) -> Dict:
        """执行 glob 工具"""
        path = params.get('path', self.workspace)
        validate_workspace_path(path, self.workspace)

        files = glob_files(
            pattern=params['pattern'],
            path=path
        )

        return {
            'success': True,
            'output': '\n'.join(files),
            'files_count': len(files)
        }

    def _execute_bash(self, params: Dict) -> Dict:
        """执行 bash 工具"""
        if not self.sandbox:
            return {
                'success': False,
                'error': "Sandbox not initialized. Cannot execute bash commands."
            }

        result = execute_bash(
            command=params['command'],
            session_id=self.session_id,
            sandbox=self.sandbox,
            timeout=params.get('timeout', 30),
            audit_logger=self.audit_logger
        )

        output = format_bash_output(result)

        return {
            'success': result['exit_code'] == 0,
            'output': output,
            'exit_code': result['exit_code']
        }

    def _execute_apply_patch(self, params: Dict) -> Dict:
        """执行 apply_patch 工具"""
        affected = apply_patch(
            params['patch_text'],
            self.workspace,
            strict_add=params.get('strict_add', False)
        )

        summary = []
        if affected.added:
            summary.append(f"Added: {', '.join(affected.added)}")
        if affected.modified:
            summary.append(f"Modified: {', '.join(affected.modified)}")
        if affected.deleted:
            summary.append(f"Deleted: {', '.join(affected.deleted)}")

        return {
            'success': True,
            'output': '\n'.join(summary),
            'affected': {
                'added': affected.added,
                'modified': affected.modified,
                'deleted': affected.deleted
            }
        }
