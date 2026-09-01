"""
完整示例：使用代码编辑器
"""

import os
import tempfile
from code_editor.sandbox import Sandbox
from code_editor.agent import ToolExecutor, TOOLS


def main():
    # 创建临时工作空间
    with tempfile.TemporaryDirectory() as workspace:
        print(f"Workspace: {workspace}")

        # 1. 创建测试文件
        test_file = os.path.join(workspace, "example.py")
        with open(test_file, "w") as f:
            f.write("""
def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total

def main():
    result = calculate_sum([1, 2, 3, 4, 5])
    print(f"Sum: {result}")

if __name__ == "__main__":
    main()
""")

        # 2. 启动沙箱
        print("\n=== Starting Sandbox ===")
        with Sandbox(workspace) as sandbox:
            # 3. 创建工具执行器
            executor = ToolExecutor(
                workspace=workspace,
                session_id="demo_session",
                sandbox=sandbox,
                audit_log_file=os.path.join(workspace, "audit.log")
            )

            # 4. 演示所有工具

            # 4.1 Glob - 查找 Python 文件
            print("\n=== Tool: glob ===")
            result = executor.execute("glob", {"pattern": "**/*.py"})
            print(f"Success: {result['success']}")
            print(f"Files:\n{result['output']}")

            # 4.2 Read - 读取文件
            print("\n=== Tool: read ===")
            result = executor.execute("read", {"file_path": test_file})
            print(f"Success: {result['success']}")
            print(f"Content (first 300 chars):\n{result['output'][:300]}")

            # 4.3 Grep - 搜索代码
            print("\n=== Tool: grep ===")
            result = executor.execute("grep", {
                "pattern": "def ",
                "path": workspace
            })
            print(f"Success: {result['success']}")
            print(f"Matches: {result.get('matches_count', 0)}")
            print(f"Output:\n{result['output']}")

            # 4.4 Edit - 修改代码（使用列表推导式优化）
            print("\n=== Tool: edit ===")
            result = executor.execute("edit", {
                "file_path": test_file,
                "old_string": """def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total""",
                "new_string": """def calculate_sum(numbers):
    return sum(numbers)"""
            })
            print(f"Success: {result['success']}")
            print(f"Output: {result['output']}")

            # 验证修改
            with open(test_file, "r") as f:
                print(f"\nModified content:\n{f.read()}")

            # 4.5 Bash - 运行代码
            print("\n=== Tool: bash ===")
            result = executor.execute("bash", {
                "command": f"cd /workspace && python example.py"
            })
            print(f"Success: {result['success']}")
            print(f"Output:\n{result['output']}")

            # 4.6 Write - 创建新文件
            print("\n=== Tool: write ===")
            new_file = os.path.join(workspace, "utils.py")
            result = executor.execute("write", {
                "file_path": new_file,
                "content": """
def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
"""
            })
            print(f"Success: {result['success']}")
            print(f"Output: {result['output']}")

            # 4.7 Apply Patch - 批量修改
            print("\n=== Tool: apply_patch ===")
            patch = """
*** Begin Patch
*** Add File: config.json
+{
+  "version": "1.0.0",
+  "name": "example"
+}
*** Update File: example.py
@@ if __name__ == "__main__":
-    main()
+    import sys
+    sys.exit(main())
*** End Patch
"""
            result = executor.execute("apply_patch", {"patch_text": patch})
            print(f"Success: {result['success']}")
            print(f"Output:\n{result['output']}")

        print("\n=== Demo Complete ===")
        print(f"Check audit log: {os.path.join(workspace, 'audit.log')}")


if __name__ == "__main__":
    main()
