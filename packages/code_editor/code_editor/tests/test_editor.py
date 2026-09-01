"""
核心编辑算法测试
"""

import pytest
from code_editor.core.editor import (
    replace,
    EditError,
    levenshtein,
    simple_replacer,
    line_trimmed_replacer,
    block_anchor_replacer,
)


class TestLevenshtein:
    """测试 Levenshtein 距离算法"""

    def test_empty_strings(self):
        assert levenshtein("", "") == 0
        assert levenshtein("abc", "") == 3
        assert levenshtein("", "abc") == 3

    def test_identical_strings(self):
        assert levenshtein("hello", "hello") == 0

    def test_single_char_diff(self):
        assert levenshtein("hello", "hallo") == 1

    def test_complex_diff(self):
        assert levenshtein("kitten", "sitting") == 3


class TestSimpleReplacer:
    """测试精确匹配"""

    def test_exact_match(self):
        content = "def foo():\n    return 42"
        find = "return 42"
        matches = list(simple_replacer(content, find))
        assert len(matches) == 1
        assert matches[0] == "return 42"

    def test_no_match(self):
        content = "def foo():\n    return 42"
        find = "return 43"
        matches = list(simple_replacer(content, find))
        assert len(matches) == 1  # 总是 yield find


class TestLineTrimmedReplacer:
    """测试行尾空白容错"""

    def test_trailing_whitespace(self):
        content = "def foo():   \n    return 42   \n"
        find = "def foo():\n    return 42"
        matches = list(line_trimmed_replacer(content, find))
        assert len(matches) >= 1
        # 应该匹配，即使原文有尾部空白

    def test_indentation_preserved(self):
        content = "    def foo():\n        return 42"
        find = "def foo():\n    return 42"
        matches = list(line_trimmed_replacer(content, find))
        # 应该匹配（忽略缩进差异）
        assert len(matches) >= 1


class TestBlockAnchorReplacer:
    """测试首尾行锚定匹配"""

    def test_block_match_with_similar_middle(self):
        content = """
def calculate(x, y):
    result = x + y
    print(result)
    return result
"""
        find = """def calculate(x, y):
    result = x + y  # 这里有点不同
    return result"""

        matches = list(block_anchor_replacer(content, find))
        # 应该匹配（首尾行相同，中间行相似）
        assert len(matches) >= 1

    def test_single_candidate_low_threshold(self):
        content = """
def foo():
    a = 1
    b = 2
    return a + b
"""
        find = """def foo():
    x = 1  # 变量名不同
    return x + y"""

        matches = list(block_anchor_replacer(content, find))
        # 单候选场景，阈值为 0.0，应该匹配
        assert len(matches) >= 1


class TestReplace:
    """测试主替换函数"""

    def test_simple_replace(self):
        content = "def foo():\n    return 42"
        result = replace(content, "return 42", "return 100")
        assert "return 100" in result
        assert "return 42" not in result

    def test_replace_with_whitespace_tolerance(self):
        content = "def foo():   \n    return 42   "
        result = replace(content, "def foo():\n    return 42", "def bar():\n    return 100")
        assert "def bar()" in result

    def test_replace_all(self):
        content = "x = 1\ny = 1\nz = 1"
        result = replace(content, "= 1", "= 2", replace_all=True)
        assert result.count("= 2") == 3

    def test_same_old_new_raises_error(self):
        with pytest.raises(EditError, match="must be different"):
            replace("test", "foo", "foo")

    def test_not_found_raises_error(self):
        with pytest.raises(EditError, match="not found"):
            replace("test", "nonexistent", "new")

    def test_multiple_matches_without_replace_all(self):
        content = "foo\nfoo\nfoo"
        with pytest.raises(EditError, match="multiple matches"):
            replace(content, "foo", "bar", replace_all=False)

    def test_indentation_flexible(self):
        content = """
    def foo():
        return 42
"""
        find = """def foo():
    return 42"""  # 缩进不同

        result = replace(content, find, "def bar():\n    return 100")
        assert "def bar()" in result


class TestRealWorldScenarios:
    """真实场景测试"""

    def test_llm_generated_code_mismatch(self):
        """模拟 LLM 生成的代码与实际文件有微小差异"""
        actual_file = """
def calculate_total(items):
    total = 0
    for item in items:
        total += item.price
    return total
"""

        llm_old_string = """def calculate_total(items):
    total=0  # LLM 忘记了空格
    for item in items:
        total+=item.price  # LLM 忘记了空格
    return total"""

        new_string = """def calculate_total(items):
    return sum(item.price for item in items)"""

        # 应该能成功替换（多级容错）
        result = replace(actual_file, llm_old_string, new_string)
        assert "sum(item.price" in result

    def test_unicode_quotes_mismatch(self):
        """测试 Unicode 引号容错"""
        content = 'name = "John"'  # 普通引号
        find = 'name = "John"'  # LLM 使用了智能引号

        result = replace(content, find, 'name = "Alice"')
        assert 'Alice' in result
