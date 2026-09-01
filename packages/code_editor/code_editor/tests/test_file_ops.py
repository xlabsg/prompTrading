"""
文件操作测试
"""

import os
import tempfile
import pytest
from code_editor.tools.file_ops import (
    read_file,
    write_file,
    validate_workspace_path,
    FileTime,
    StaleFileError,
    FileOperationError,
)


@pytest.fixture
def temp_workspace():
    """创建临时工作空间"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestFileTime:
    """测试文件时间追踪"""

    def test_record_and_assert_fresh(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "test.txt")
        with open(filepath, "w") as f:
            f.write("original")

        # 记录读取时间
        FileTime.record_read("session1", filepath)

        # 应该通过检查
        FileTime.assert_fresh("session1", filepath)

    def test_stale_file_detection(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "test.txt")
        with open(filepath, "w") as f:
            f.write("original")

        # 记录读取时间
        FileTime.record_read("session1", filepath)

        # 模拟其他会话修改文件
        import time
        time.sleep(0.01)
        with open(filepath, "w") as f:
            f.write("modified")

        # 应该检测到文件已修改
        with pytest.raises(StaleFileError, match="has been modified"):
            FileTime.assert_fresh("session1", filepath)

    def test_clear_session(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "test.txt")
        with open(filepath, "w") as f:
            f.write("test")

        FileTime.record_read("session1", filepath)
        FileTime.clear_session("session1")

        # 清除后应该抛出异常
        with pytest.raises(FileOperationError, match="was not read"):
            FileTime.assert_fresh("session1", filepath)


class TestReadFile:
    """测试文件读取"""

    def test_read_simple_file(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "test.py")
        content = "def foo():\n    return 42"
        with open(filepath, "w") as f:
            f.write(content)

        result = read_file(filepath, "session1")
        assert "def foo():" in result
        assert "return 42" in result
        assert "→" in result  # 行号分隔符

    def test_read_with_offset_and_limit(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "test.py")
        content = "\n".join([f"line {i}" for i in range(10)])
        with open(filepath, "w") as f:
            f.write(content)

        result = read_file(filepath, "session1", offset=2, limit=3)
        assert "line 2" in result
        assert "line 3" in result
        assert "line 4" in result
        assert "line 0" not in result

    def test_read_nonexistent_file(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "nonexistent.py")
        with pytest.raises(FileOperationError, match="not found"):
            read_file(filepath, "session1")


class TestWriteFile:
    """测试文件写入"""

    def test_write_new_file(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "new.py")
        write_file(filepath, "print('hello')", "session1")

        assert os.path.exists(filepath)
        with open(filepath, "r") as f:
            assert f.read() == "print('hello')"

    def test_write_creates_parent_dirs(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "subdir/nested/file.py")
        write_file(filepath, "test", "session1")

        assert os.path.exists(filepath)

    def test_write_after_read_succeeds(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "test.py")
        with open(filepath, "w") as f:
            f.write("original")

        # 先读取
        read_file(filepath, "session1")

        # 再写入应该成功
        write_file(filepath, "modified", "session1")

        with open(filepath, "r") as f:
            assert f.read() == "modified"

    def test_write_detects_stale_file(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "test.py")
        with open(filepath, "w") as f:
            f.write("original")

        # Session1 读取
        read_file(filepath, "session1")

        # Session2 修改
        import time
        time.sleep(0.01)
        write_file(filepath, "modified by session2", "session2")

        # Session1 尝试写入应该失败
        with pytest.raises(StaleFileError):
            write_file(filepath, "modified by session1", "session1")


class TestValidateWorkspacePath:
    """测试路径验证"""

    def test_valid_path(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "test.py")
        validate_workspace_path(filepath, temp_workspace)  # 不应抛出异常

    def test_path_traversal_attack(self, temp_workspace):
        filepath = os.path.join(temp_workspace, "../../../etc/passwd")
        with pytest.raises(FileOperationError, match="outside workspace"):
            validate_workspace_path(filepath, temp_workspace)

    def test_absolute_path_outside_workspace(self, temp_workspace):
        with pytest.raises(FileOperationError, match="outside workspace"):
            validate_workspace_path("/etc/passwd", temp_workspace)
