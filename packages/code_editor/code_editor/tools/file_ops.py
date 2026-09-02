"""
文件操作工具 - 防止并发写入冲突（FileTime 机制：读取时记录时间戳，写入前校验）
"""

import os
import time
from typing import Optional
from pathlib import Path
from threading import Lock


class FileOperationError(Exception):
    """文件操作异常"""
    pass


class StaleFileError(FileOperationError):
    """文件已被其他会话修改（脏读）"""
    pass


class FileTime:
    """
    文件读取时间追踪器 - 防止脏写

    机制：
    1. read_file() 时记录文件的 mtime
    2. write_file() 前检查 mtime 是否变化
    3. 如果变化，说明其他会话修改过，抛出异常
    """

    _read_times: dict[tuple[str, str], float] = {}  # {(session_id, filepath): mtime}
    _locks: dict[str, Lock] = {}  # {filepath: Lock}
    _global_lock = Lock()

    @classmethod
    def _get_lock(cls, filepath: str) -> Lock:
        """获取文件的锁对象"""
        with cls._global_lock:
            if filepath not in cls._locks:
                cls._locks[filepath] = Lock()
            return cls._locks[filepath]

    @classmethod
    def record_read(cls, session_id: str, filepath: str) -> None:
        """记录文件读取时间"""
        try:
            mtime = os.path.getmtime(filepath)
            cls._read_times[(session_id, filepath)] = mtime
        except OSError:
            # 文件不存在，记录为 -1（新建场景）
            cls._read_times[(session_id, filepath)] = -1

    @classmethod
    def assert_fresh(cls, session_id: str, filepath: str) -> None:
        """
        断言文件未被修改

        Raises:
            StaleFileError: 文件已被其他会话修改
        """
        key = (session_id, filepath)
        if key not in cls._read_times:
            raise FileOperationError(
                f"File {filepath} was not read in session {session_id}. "
                "You must use read_file() before write_file()."
            )

        last_read_time = cls._read_times[key]

        try:
            current_mtime = os.path.getmtime(filepath)
        except OSError:
            current_mtime = -1

        if last_read_time != current_mtime:
            raise StaleFileError(
                f"File {filepath} has been modified by another session. "
                f"Last read: {last_read_time}, current: {current_mtime}"
            )

    @classmethod
    def clear_session(cls, session_id: str) -> None:
        """清除会话的所有文件追踪记录"""
        keys_to_remove = [key for key in cls._read_times if key[0] == session_id]
        for key in keys_to_remove:
            del cls._read_times[key]


def read_file(
    filepath: str,
    session_id: str,
    offset: Optional[int] = None,
    limit: Optional[int] = None
) -> str:
    """
    读取文件内容（带时间追踪）

    Args:
        filepath: 文件绝对路径
        session_id: 会话 ID（用于追踪读写）
        offset: 起始行号（可选，从 0 开始）
        limit: 读取行数（可选）

    Returns:
        文件内容（带行号）

    Raises:
        FileOperationError: 文件不存在或不可读
    """
    filepath = os.path.abspath(filepath)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise FileOperationError(f"File not found: {filepath}")
    except PermissionError:
        raise FileOperationError(f"Permission denied: {filepath}")
    except Exception as e:
        raise FileOperationError(f"Failed to read {filepath}: {e}")

    # 应用偏移和限制
    if offset is not None:
        lines = lines[offset:]
    if limit is not None:
        lines = lines[:limit]

    # 记录读取时间
    FileTime.record_read(session_id, filepath)

    # 格式化输出（带行号）
    start_line = (offset or 0) + 1
    formatted_lines = []
    for i, line in enumerate(lines):
        line_no = start_line + i
        # 去除原始换行符，统一格式
        line_content = line.rstrip('\n')
        formatted_lines.append(f"{line_no:6d}→{line_content}")

    return '\n'.join(formatted_lines)


def write_file(
    filepath: str,
    content: str,
    session_id: str,
    create_dirs: bool = True
) -> None:
    """
    写入文件内容（带冲突检测）

    Args:
        filepath: 文件绝对路径
        content: 文件内容
        session_id: 会话 ID
        create_dirs: 是否自动创建父目录

    Raises:
        StaleFileError: 文件已被其他会话修改
        FileOperationError: 写入失败
    """
    filepath = os.path.abspath(filepath)
    file_lock = FileTime._get_lock(filepath)

    with file_lock:
        # 检查文件是否已被修改（如果之前读取过）
        key = (session_id, filepath)
        if key in FileTime._read_times:
            FileTime.assert_fresh(session_id, filepath)

        # 创建父目录
        if create_dirs:
            parent_dir = os.path.dirname(filepath)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

        # 写入文件
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
        except PermissionError:
            raise FileOperationError(f"Permission denied: {filepath}")
        except Exception as e:
            raise FileOperationError(f"Failed to write {filepath}: {e}")

        # 更新读取时间（写入后重新记录）
        FileTime.record_read(session_id, filepath)


def validate_workspace_path(filepath: str, workspace: str) -> None:
    """
    验证文件路径在工作空间内（防止路径遍历攻击）

    Args:
        filepath: 文件路径
        workspace: 工作空间根目录

    Raises:
        FileOperationError: 路径不在工作空间内
    """
    abs_filepath = os.path.abspath(filepath)
    abs_workspace = os.path.abspath(workspace)

    # 检查路径是否以工作空间为前缀
    try:
        Path(abs_filepath).relative_to(abs_workspace)
    except ValueError:
        raise FileOperationError(
            f"Path {filepath} is outside workspace {workspace}. "
            "Path traversal attacks are not allowed."
        )
