"""
核心编辑算法 - 多级模糊匹配链，实现9种 Replacer 策略
"""

from typing import Generator, Callable
import re


class EditError(Exception):
    """编辑操作失败异常"""
    pass


# Type alias
Replacer = Callable[[str, str], Generator[str, None, None]]


def levenshtein(a: str, b: str) -> int:
    """
    Levenshtein 距离算法（编辑距离）
    参考 edit.ts 第 156-172 行
    """
    if not a or not b:
        return max(len(a), len(b))

    matrix = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]

    # 初始化第一行和第一列
    for i in range(len(a) + 1):
        matrix[i][0] = i
    for j in range(len(b) + 1):
        matrix[0][j] = j

    # 动态规划填充矩阵
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,      # 删除
                matrix[i][j - 1] + 1,      # 插入
                matrix[i - 1][j - 1] + cost  # 替换
            )

    return matrix[len(a)][len(b)]


# ============= Replacer 实现 =============

def simple_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略1: 精确匹配
    参考 edit.ts 第 174-176 行
    """
    yield find


def line_trimmed_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略2: 逐行 trim 匹配（处理行尾空白）
    参考 edit.ts 第 178-216 行
    """
    original_lines = content.split('\n')
    search_lines = find.split('\n')

    # 移除末尾空行
    if search_lines and search_lines[-1] == '':
        search_lines.pop()

    # 滑动窗口匹配
    for i in range(len(original_lines) - len(search_lines) + 1):
        matches = True

        for j in range(len(search_lines)):
            original_trimmed = original_lines[i + j].strip()
            search_trimmed = search_lines[j].strip()

            if original_trimmed != search_trimmed:
                matches = False
                break

        if matches:
            # 计算匹配区域的起止索引
            match_start_index = sum(len(line) + 1 for line in original_lines[:i])
            match_end_index = match_start_index

            for k in range(len(search_lines)):
                match_end_index += len(original_lines[i + k])
                if k < len(search_lines) - 1:
                    match_end_index += 1  # 换行符

            yield content[match_start_index:match_end_index]


def block_anchor_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略3: 首尾行锚定 + 中间行 Levenshtein 相似度匹配
    参考 edit.ts 第 218-351 行（最复杂的 Replacer）
    """
    SINGLE_CANDIDATE_THRESHOLD = 0.0
    MULTIPLE_CANDIDATES_THRESHOLD = 0.3

    original_lines = content.split('\n')
    search_lines = find.split('\n')

    if len(search_lines) < 3:
        return

    if search_lines and search_lines[-1] == '':
        search_lines.pop()

    first_line_search = search_lines[0].strip()
    last_line_search = search_lines[-1].strip()
    search_block_size = len(search_lines)

    # 收集所有候选匹配位置（首尾行都匹配）
    candidates = []
    for i in range(len(original_lines)):
        if original_lines[i].strip() != first_line_search:
            continue

        # 查找匹配的尾行
        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_line_search:
                candidates.append({'start_line': i, 'end_line': j})
                break

    if not candidates:
        return

    # 单候选场景（宽松阈值）
    if len(candidates) == 1:
        start_line = candidates[0]['start_line']
        end_line = candidates[0]['end_line']
        actual_block_size = end_line - start_line + 1

        similarity = 0.0
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)

        if lines_to_check > 0:
            for j in range(1, min(search_block_size - 1, actual_block_size - 1)):
                original_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                max_len = max(len(original_line), len(search_line))

                if max_len == 0:
                    continue

                distance = levenshtein(original_line, search_line)
                similarity += (1 - distance / max_len) / lines_to_check

                # 提前退出
                if similarity >= SINGLE_CANDIDATE_THRESHOLD:
                    break
        else:
            similarity = 1.0

        if similarity >= SINGLE_CANDIDATE_THRESHOLD:
            match_start_index = sum(len(line) + 1 for line in original_lines[:start_line])
            match_end_index = match_start_index
            for k in range(start_line, end_line + 1):
                match_end_index += len(original_lines[k])
                if k < end_line:
                    match_end_index += 1

            yield content[match_start_index:match_end_index]
        return

    # 多候选场景（选择最佳匹配）
    best_match = None
    max_similarity = -1.0

    for candidate in candidates:
        start_line = candidate['start_line']
        end_line = candidate['end_line']
        actual_block_size = end_line - start_line + 1

        similarity = 0.0
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)

        if lines_to_check > 0:
            for j in range(1, min(search_block_size - 1, actual_block_size - 1)):
                original_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                max_len = max(len(original_line), len(search_line))

                if max_len == 0:
                    continue

                distance = levenshtein(original_line, search_line)
                similarity += 1 - distance / max_len

            similarity /= lines_to_check
        else:
            similarity = 1.0

        if similarity > max_similarity:
            max_similarity = similarity
            best_match = candidate

    if max_similarity >= MULTIPLE_CANDIDATES_THRESHOLD and best_match:
        start_line = best_match['start_line']
        end_line = best_match['end_line']

        match_start_index = sum(len(line) + 1 for line in original_lines[:start_line])
        match_end_index = match_start_index
        for k in range(start_line, end_line + 1):
            match_end_index += len(original_lines[k])
            if k < end_line:
                match_end_index += 1

        yield content[match_start_index:match_end_index]


def whitespace_normalized_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略4: 空白字符标准化匹配
    参考 edit.ts 第 353-395 行
    """
    def normalize_whitespace(text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

    normalized_find = normalize_whitespace(find)

    # 单行匹配
    lines = content.split('\n')
    for line in lines:
        if normalize_whitespace(line) == normalized_find:
            yield line
        else:
            # 子串匹配
            normalized_line = normalize_whitespace(line)
            if normalized_find in normalized_line:
                words = find.strip().split()
                if words:
                    pattern = r'\s+'.join(re.escape(word) for word in words)
                    try:
                        match = re.search(pattern, line)
                        if match:
                            yield match.group(0)
                    except re.error:
                        pass

    # 多行匹配
    find_lines = find.split('\n')
    if len(find_lines) > 1:
        for i in range(len(lines) - len(find_lines) + 1):
            block = '\n'.join(lines[i:i + len(find_lines)])
            if normalize_whitespace(block) == normalized_find:
                yield block


def indentation_flexible_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略5: 缩进容错匹配
    参考 edit.ts 第 397-423 行
    """
    def remove_indentation(text: str) -> str:
        lines = text.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]

        if not non_empty_lines:
            return text

        min_indent = min(
            len(line) - len(line.lstrip())
            for line in non_empty_lines
        )

        return '\n'.join(
            line if not line.strip() else line[min_indent:]
            for line in lines
        )

    normalized_find = remove_indentation(find)
    content_lines = content.split('\n')
    find_lines = find.split('\n')

    for i in range(len(content_lines) - len(find_lines) + 1):
        block = '\n'.join(content_lines[i:i + len(find_lines)])
        if remove_indentation(block) == normalized_find:
            yield block


def escape_normalized_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略6: 转义字符标准化匹配
    参考 edit.ts 第 425-472 行
    """
    def unescape_string(s: str) -> str:
        replacements = {
            r'\n': '\n',
            r'\t': '\t',
            r'\r': '\r',
            r"\'": "'",
            r'\"': '"',
            r'\`': '`',
            r'\\': '\\',
            r'\$': '$',
        }
        result = s
        for escaped, unescaped in replacements.items():
            result = result.replace(escaped, unescaped)
        return result

    unescaped_find = unescape_string(find)

    # 直接匹配
    if unescaped_find in content:
        yield unescaped_find

    # 逐块匹配
    lines = content.split('\n')
    find_lines = unescaped_find.split('\n')

    for i in range(len(lines) - len(find_lines) + 1):
        block = '\n'.join(lines[i:i + len(find_lines)])
        unescaped_block = unescape_string(block)

        if unescaped_block == unescaped_find:
            yield block


def trimmed_boundary_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略7: 边界空白容错匹配
    参考 edit.ts 第 488-512 行
    """
    trimmed_find = find.strip()

    if trimmed_find == find:
        return

    # 直接匹配
    if trimmed_find in content:
        yield trimmed_find

    # 块匹配
    lines = content.split('\n')
    find_lines = find.split('\n')

    for i in range(len(lines) - len(find_lines) + 1):
        block = '\n'.join(lines[i:i + len(find_lines)])
        if block.strip() == trimmed_find:
            yield block


def context_aware_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略8: 上下文智能匹配（>=50% 中间行匹配）
    参考 edit.ts 第 514-570 行
    """
    find_lines = find.split('\n')
    if len(find_lines) < 3:
        return

    if find_lines and find_lines[-1] == '':
        find_lines.pop()

    content_lines = content.split('\n')
    first_line = find_lines[0].strip()
    last_line = find_lines[-1].strip()

    for i in range(len(content_lines)):
        if content_lines[i].strip() != first_line:
            continue

        for j in range(i + 2, len(content_lines)):
            if content_lines[j].strip() == last_line:
                block_lines = content_lines[i:j + 1]
                block = '\n'.join(block_lines)

                if len(block_lines) == len(find_lines):
                    matching_lines = 0
                    total_non_empty_lines = 0

                    for k in range(1, len(block_lines) - 1):
                        block_line = block_lines[k].strip()
                        find_line = find_lines[k].strip()

                        if block_line or find_line:
                            total_non_empty_lines += 1
                            if block_line == find_line:
                                matching_lines += 1

                    if total_non_empty_lines == 0 or matching_lines / total_non_empty_lines >= 0.5:
                        yield block
                        break
                break


def multi_occurrence_replacer(content: str, find: str) -> Generator[str, None, None]:
    """
    策略9: 多次出现枚举（用于 replace_all）
    参考 edit.ts 第 474-486 行
    """
    start_index = 0

    while True:
        index = content.find(find, start_index)
        if index == -1:
            break

        yield find
        start_index = index + len(find)


# ============= 主函数 =============

def replace(content: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """
    多级模糊匹配替换

    参考 edit.ts 第 608-645 行

    Args:
        content: 文件原始内容
        old_string: 要替换的文本（允许不精确）
        new_string: 替换后的文本
        replace_all: 是否替换所有出现（默认 False，只替换唯一匹配）

    Returns:
        替换后的内容

    Raises:
        EditError: 找不到匹配或匹配不唯一
    """
    if old_string == new_string:
        raise EditError("old_string and new_string must be different")

    replacers = [
        simple_replacer,
        line_trimmed_replacer,
        block_anchor_replacer,
        whitespace_normalized_replacer,
        indentation_flexible_replacer,
        escape_normalized_replacer,
        trimmed_boundary_replacer,
        context_aware_replacer,
        multi_occurrence_replacer,
    ]

    not_found = True

    for replacer in replacers:
        for search in replacer(content, old_string):
            index = content.find(search)
            if index == -1:
                continue

            not_found = False

            if replace_all:
                return content.replace(search, new_string)

            # 检查唯一性
            last_index = content.rfind(search)
            if index != last_index:
                continue

            # 唯一匹配，执行替换
            return content[:index] + new_string + content[index + len(search):]

    if not_found:
        raise EditError("old_string not found in content")

    raise EditError(
        "Found multiple matches for old_string. "
        "Provide more surrounding lines in old_string to identify the correct match."
    )
