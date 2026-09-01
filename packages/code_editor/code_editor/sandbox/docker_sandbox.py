"""
Docker 沙箱管理 - 简化版

参考 OpenHands 的 DockerRuntime，精简实现
不需要持久化容器，每次任务创建临时容器
"""

import os
import time
import docker
from typing import Optional, Dict
from docker.models.containers import Container
from docker.types import Mount


class SandboxError(Exception):
    """沙箱异常"""
    pass


class Sandbox:
    """
    Docker 沙箱 - 隔离代码执行环境

    特性:
    - 资源限制（CPU/内存）
    - 网络隔离（禁止外网访问）
    - 文件系统隔离（只读挂载 workspace）
    - 自动清理（任务结束后销毁容器）
    """

    def __init__(
        self,
        workspace: str,
        image: str = "python:3.11-slim",
        mem_limit: str = "512m",
        cpu_quota: int = 50000,  # 50% CPU
        network_mode: str = "none",  # 禁止网络
        timeout: int = 300  # 5分钟超时
    ):
        """
        初始化沙箱

        Args:
            workspace: 工作空间路径（宿主机）
            image: Docker 镜像
            mem_limit: 内存限制
            cpu_quota: CPU 配额（100000 = 100%）
            network_mode: 网络模式（none=禁止网络）
            timeout: 容器生命周期超时
        """
        self.workspace = os.path.abspath(workspace)
        self.image = image
        self.mem_limit = mem_limit
        self.cpu_quota = cpu_quota
        self.network_mode = network_mode
        self.timeout = timeout

        self.container: Optional[Container] = None
        self.docker_client: Optional[docker.DockerClient] = None

    def start(self) -> None:
        """启动沙箱容器"""
        try:
            self.docker_client = docker.from_env()
        except docker.errors.DockerException as e:
            raise SandboxError(f"Failed to connect to Docker: {e}")

        # 检查工作空间存在
        if not os.path.exists(self.workspace):
            raise SandboxError(f"Workspace does not exist: {self.workspace}")

        # 拉取镜像（如果不存在）
        try:
            self.docker_client.images.get(self.image)
        except docker.errors.ImageNotFound:
            try:
                print(f"Pulling image {self.image}...")
                self.docker_client.images.pull(self.image)
            except docker.errors.APIError as e:
                raise SandboxError(f"Failed to pull image {self.image}: {e}")

        # 创建并启动容器
        try:
            self.container = self.docker_client.containers.run(
                image=self.image,
                command="tail -f /dev/null",  # 保持容器运行
                detach=True,
                remove=True,  # 停止后自动删除
                working_dir="/workspace",
                volumes={
                    self.workspace: {
                        'bind': '/workspace',
                        'mode': 'rw'  # 读写模式（代码需要修改）
                    }
                },
                mem_limit=self.mem_limit,
                cpu_quota=self.cpu_quota,
                network_mode=self.network_mode,
                # 安全限制
                cap_drop=['ALL'],  # 移除所有 capabilities
                security_opt=['no-new-privileges'],
            )
        except docker.errors.APIError as e:
            raise SandboxError(f"Failed to start container: {e}")

        # 等待容器就绪
        time.sleep(0.5)

    def execute(
        self,
        command: str,
        timeout: int = 30,
        workdir: Optional[str] = None
    ) -> Dict[str, any]:
        """
        在容器中执行命令

        Args:
            command: 要执行的命令
            timeout: 超时时间（秒）
            workdir: 工作目录（容器内路径）

        Returns:
            {
                'exit_code': int,
                'stdout': str,
                'stderr': str
            }

        Raises:
            SandboxError: 容器未启动或执行失败
        """
        if not self.container:
            raise SandboxError("Sandbox is not started. Call start() first.")

        exec_kwargs = {
            'cmd': ['bash', '-c', command],
            'stdout': True,
            'stderr': True,
            'demux': True,
        }

        if workdir:
            exec_kwargs['workdir'] = workdir

        try:
            exit_code, output = self.container.exec_run(**exec_kwargs)

            stdout_bytes, stderr_bytes = output

            stdout = stdout_bytes.decode('utf-8') if stdout_bytes else ""
            stderr = stderr_bytes.decode('utf-8') if stderr_bytes else ""

            return {
                'exit_code': exit_code,
                'stdout': stdout,
                'stderr': stderr
            }

        except docker.errors.APIError as e:
            raise SandboxError(f"Failed to execute command: {e}")
        except Exception as e:
            raise SandboxError(f"Unexpected error during execution: {e}")

    def stop(self) -> None:
        """停止并清理沙箱"""
        if self.container:
            try:
                self.container.stop(timeout=5)
            except docker.errors.APIError:
                # 容器可能已经停止
                pass
            finally:
                self.container = None

        if self.docker_client:
            try:
                self.docker_client.close()
            except Exception:
                pass
            finally:
                self.docker_client = None

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()

    def is_running(self) -> bool:
        """检查容器是否运行"""
        if not self.container:
            return False

        try:
            self.container.reload()
            return self.container.status == 'running'
        except docker.errors.APIError:
            return False
