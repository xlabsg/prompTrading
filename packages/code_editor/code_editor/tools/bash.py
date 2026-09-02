"""
Bash 命令执行工具 - 带安全审计
"""

import re
import json
import logging
from typing import Optional, Dict
from datetime import datetime


class BashError(Exception):
    """Bash 执行异常"""
    pass


class DangerousCommandError(BashError):
    """危险命令异常"""
    pass


# 危险命令黑名单（正则模式）
DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\s+/',  # 删除根目录
    r'\bmkfs\b',  # 格式化文件系统
    r'\bdd\s+if=.*of=/dev/',  # 覆写磁盘
    r'\b:(){.*};\s*:',  # Fork bomb
    r'\bchmod\s+777\s+/',  # 修改根目录权限
    r'\bchown\s+.*\s+/',  # 修改根目录所有者
    r'\bcurl.*\|\s*bash',  # 执行远程脚本
    r'\bwget.*\|\s*bash',
    r'\biptables\b',  # 防火墙修改
    r'\bsudo\b',  # 提权
    r'\bsu\s+',
]


def detect_dangerous_command(command: str) -> Optional[str]:
    """
    检测危险命令

    Args:
        command: 要执行的命令

    Returns:
        匹配的危险模式（如果有），否则 None
    """
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return pattern
    return None


class AuditLogger:
    """审计日志记录器"""

    def __init__(self, log_file: Optional[str] = None):
        """
        初始化审计日志

        Args:
            log_file: 日志文件路径（None 则只输出到 stdout）
        """
        self.logger = logging.getLogger('code_editor.bash_audit')
        self.logger.setLevel(logging.INFO)

        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s [AUDIT] %(message)s'
        ))
        self.logger.addHandler(console_handler)

        # 文件输出
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s [AUDIT] %(message)s'
            ))
            self.logger.addHandler(file_handler)

    def log_command(
        self,
        session_id: str,
        command: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration_ms: int,
        is_dangerous: bool = False
    ) -> None:
        """
        记录命令执行

        Args:
            session_id: 会话 ID
            command: 执行的命令
            exit_code: 退出码
            stdout: 标准输出
            stderr: 标准错误
            duration_ms: 执行时长（毫秒）
            is_dangerous: 是否为危险命令
        """
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'session_id': session_id,
            'command': command,
            'exit_code': exit_code,
            'stdout_length': len(stdout),
            'stderr_length': len(stderr),
            'duration_ms': duration_ms,
            'is_dangerous': is_dangerous
        }

        # 截断过长的输出
        if len(stdout) > 1000:
            log_entry['stdout_preview'] = stdout[:1000] + '...'
        else:
            log_entry['stdout'] = stdout

        if len(stderr) > 1000:
            log_entry['stderr_preview'] = stderr[:1000] + '...'
        elif stderr:
            log_entry['stderr'] = stderr

        self.logger.info(json.dumps(log_entry, ensure_ascii=False))


def execute_bash(
    command: str,
    session_id: str,
    sandbox,  # Sandbox instance
    timeout: int = 30,
    workdir: Optional[str] = None,
    audit_logger: Optional[AuditLogger] = None,
    allow_dangerous: bool = False
) -> Dict[str, any]:
    """
    执行 Bash 命令（带安全检查和审计）

    Args:
        command: 要执行的命令
        session_id: 会话 ID
        sandbox: 沙箱实例
        timeout: 超时时间（秒）
        workdir: 工作目录
        audit_logger: 审计日志记录器
        allow_dangerous: 是否允许危险命令（默认禁止）

    Returns:
        {
            'exit_code': int,
            'stdout': str,
            'stderr': str,
            'duration_ms': int
        }

    Raises:
        DangerousCommandError: 检测到危险命令
        BashError: 执行失败
    """
    # 安全检查
    dangerous_pattern = detect_dangerous_command(command)
    if dangerous_pattern and not allow_dangerous:
        error_msg = f"Dangerous command detected: {dangerous_pattern}"
        if audit_logger:
            audit_logger.log_command(
                session_id=session_id,
                command=command,
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                duration_ms=0,
                is_dangerous=True
            )
        raise DangerousCommandError(error_msg)

    # 执行命令
    start_time = datetime.utcnow()

    try:
        result = sandbox.execute(command, timeout=timeout, workdir=workdir)
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # 记录审计日志
        if audit_logger:
            audit_logger.log_command(
                session_id=session_id,
                command=command,
                exit_code=result['exit_code'],
                stdout=result['stdout'],
                stderr=result['stderr'],
                duration_ms=duration_ms,
                is_dangerous=bool(dangerous_pattern)
            )

        result['duration_ms'] = duration_ms
        return result

    except Exception as e:
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        error_msg = str(e)
        if audit_logger:
            audit_logger.log_command(
                session_id=session_id,
                command=command,
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                duration_ms=duration_ms,
                is_dangerous=bool(dangerous_pattern)
            )

        raise BashError(f"Command execution failed: {error_msg}")


def format_bash_output(result: Dict[str, any]) -> str:
    """
    格式化 Bash 输出为可读字符串

    Args:
        result: execute_bash() 的返回值

    Returns:
        格式化后的输出
    """
    lines = []

    if result['stdout']:
        lines.append("=== STDOUT ===")
        lines.append(result['stdout'])

    if result['stderr']:
        lines.append("=== STDERR ===")
        lines.append(result['stderr'])

    lines.append(f"\nExit code: {result['exit_code']}")
    lines.append(f"Duration: {result.get('duration_ms', 0)}ms")

    return "\n".join(lines)
