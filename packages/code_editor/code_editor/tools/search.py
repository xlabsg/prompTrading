"""
搜索工具 - 封装 ripgrep
"""

import subprocess
import json
import shutil
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


class SearchError(Exception):
    """搜索异常"""
    pass


@dataclass
class Match:
    """搜索匹配结果"""
    file_path: str
    line_number: int
    line_content: str
    match_start: int
    match_end: int


def ensure_ripgrep_installed() -> str:
    """
    确保 ripgrep 已安装

    Returns:
        ripgrep 可执行文件路径

    Raises:
        SearchError: ripgrep 未安装
    """
    rg_path = shutil.which('rg')
    if not rg_path:
        raise SearchError(
            "ripgrep (rg) is not installed. "
            "Install it via: brew install ripgrep (macOS) or apt install ripgrep (Linux)"
        )
    return rg_path


def grep(
    pattern: str,
    path: str,
    glob: Optional[str] = None,
    file_type: Optional[str] = None,
    ignore_case: bool = False,
    context_before: int = 0,
    context_after: int = 0,
    max_results: int = 0
) -> List[Match]:
    """
    使用 ripgrep 搜索代码

    JSON 输出解析。

    Args:
        pattern: 正则表达式模式
        path: 搜索路径
        glob: 文件模式过滤（如 "*.py"）
        file_type: 文件类型过滤（如 "py", "js"）
        ignore_case: 是否忽略大小写
        context_before: 前文行数
        context_after: 后文行数
        max_results: 最大结果数（0 为无限制）

    Returns:
        匹配结果列表
    """
    rg_path = ensure_ripgrep_installed()

    cmd = [rg_path, '--json', pattern, path]

    if glob:
        cmd.extend(['--glob', glob])

    if file_type:
        cmd.extend(['--type', file_type])

    if ignore_case:
        cmd.append('-i')

    if context_before > 0:
        cmd.extend(['-B', str(context_before)])

    if context_after > 0:
        cmd.extend(['-A', str(context_after)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
    except subprocess.TimeoutExpired:
        raise SearchError("Search timeout after 30 seconds")
    except Exception as e:
        raise SearchError(f"Failed to run ripgrep: {e}")

    # 解析 JSON 输出
    matches = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get('type') == 'match':
            match_data = data['data']
            submatches = match_data.get('submatches', [])

            if submatches:
                first_submatch = submatches[0]
                matches.append(Match(
                    file_path=match_data['path']['text'],
                    line_number=match_data['line_number'],
                    line_content=match_data['lines']['text'].rstrip('\n'),
                    match_start=first_submatch['start'],
                    match_end=first_submatch['end']
                ))

        if max_results > 0 and len(matches) >= max_results:
            break

    return matches


def glob_files(
    pattern: str,
    path: str,
    max_results: int = 100
) -> List[str]:
    """
    使用 ripgrep 查找文件

    定位可执行的 ripgrep 二进制。

    Args:
        pattern: glob 模式（如 "**/*.py"）
        path: 搜索路径
        max_results: 最大结果数

    Returns:
        文件路径列表
    """
    rg_path = ensure_ripgrep_installed()

    cmd = [
        rg_path,
        '--files',
        '--glob', pattern,
        path
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
    except subprocess.TimeoutExpired:
        raise SearchError("File search timeout after 30 seconds")
    except Exception as e:
        raise SearchError(f"Failed to run ripgrep: {e}")

    files = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]

    if max_results > 0:
        files = files[:max_results]

    return files


def format_grep_output(matches: List[Match], show_line_numbers: bool = True) -> str:
    """
    格式化搜索结果为可读字符串

    Args:
        matches: 搜索匹配结果
        show_line_numbers: 是否显示行号

    Returns:
        格式化后的输出
    """
    if not matches:
        return "No matches found."

    # 按文件分组
    grouped: Dict[str, List[Match]] = {}
    for match in matches:
        if match.file_path not in grouped:
            grouped[match.file_path] = []
        grouped[match.file_path].append(match)

    lines = []
    for file_path, file_matches in grouped.items():
        lines.append(f"\n{file_path}")
        lines.append("-" * 60)

        for match in file_matches:
            if show_line_numbers:
                lines.append(f"{match.line_number:6d}→{match.line_content}")
            else:
                lines.append(match.line_content)

    return "\n".join(lines)
