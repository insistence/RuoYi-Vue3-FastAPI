import os
import platform
import socket
import time
from dataclasses import dataclass
from importlib import metadata
from typing import Any

from cli.exit_codes import RUNTIME_ERROR

from .gateway import OperationsInfrastructureGateway


@dataclass(frozen=True)
class OperationsDependencySpec:
    """
    运维依赖检查项定义。

    :param package_name: CLI 展示用包名
    :param distribution: Python 分发名称
    :param required: 是否为必需依赖
    :param version: 显式版本，存在时跳过环境读取
    """

    package_name: str
    distribution: str
    required: bool
    version: str | None = None


class OperationsDependencyInspector:
    """
    运维依赖检查器。

    该对象负责核心依赖声明、版本探测与依赖检查结果构建，
    使运行时 facade 不再直接维护细碎依赖定义。
    """

    @staticmethod
    def read_package_version(distribution_name: str) -> str | None:
        """
        读取指定 Python 包的已安装版本号。

        :param distribution_name: Python 包分发名称
        :return: 已安装版本号，未安装时返回 `None`
        """
        try:
            return metadata.version(distribution_name)
        except metadata.PackageNotFoundError:
            return None

    @staticmethod
    def build_dependency_specs(*, include_dev: bool = False) -> list[OperationsDependencySpec]:
        """
        构建当前依赖检查项列表。

        :param include_dev: 是否附带开发阶段依赖
        :return: 依赖检查项列表
        """
        dependency_specs = [
            OperationsDependencySpec('python', '', True, platform.python_version()),
            OperationsDependencySpec('fastapi', 'fastapi', True),
            OperationsDependencySpec('uvicorn', 'uvicorn', True),
            OperationsDependencySpec('sqlalchemy', 'SQLAlchemy', True),
            OperationsDependencySpec('alembic', 'alembic', True),
            OperationsDependencySpec('redis', 'redis', True),
            OperationsDependencySpec('pydantic', 'pydantic', True),
            OperationsDependencySpec('pydantic-settings', 'pydantic-settings', True),
            OperationsDependencySpec('typer', 'typer', True),
        ]
        if include_dev:
            dependency_specs.extend(
                [
                    OperationsDependencySpec('pytest', 'pytest', False),
                    OperationsDependencySpec('ruff', 'ruff', False),
                ]
            )
        return dependency_specs

    def inspect(self, *, include_dev: bool = False) -> dict[str, Any]:
        """
        读取 CLI 和后端运行所依赖的核心 Python 包版本。

        :param include_dev: 是否附带开发阶段依赖
        :return: 依赖检查结果
        """
        packages: dict[str, dict[str, Any]] = {}
        missing_required: list[str] = []
        for dependency_spec in self.build_dependency_specs(include_dev=include_dev):
            version = dependency_spec.version or self.read_package_version(dependency_spec.distribution)
            installed = bool(version)
            package_payload = {
                'installed': installed,
                'version': version or '',
                'required': dependency_spec.required,
            }
            if dependency_spec.distribution:
                package_payload['distribution'] = dependency_spec.distribution
            packages[dependency_spec.package_name] = package_payload
            if dependency_spec.required and not installed:
                missing_required.append(dependency_spec.package_name)

        if missing_required:
            return {
                'ok': False,
                'message': '存在缺失的核心运行依赖',
                'missingRequired': missing_required,
                'includeDev': include_dev,
                'packages': packages,
                'exit_code': RUNTIME_ERROR,
            }

        return {
            'ok': True,
            'message': '核心运行依赖已安装',
            'missingRequired': [],
            'includeDev': include_dev,
            'packages': packages,
        }


class OperationsServerInfoSupport:
    """
    运维服务器信息支持对象。

    该对象负责 CLI 兜底服务器信息构建与 IP 解析逻辑，
    避免主运行时服务继续承载大量平台采集细节。

    :param infrastructure_gateway: 运维基础设施网关
    """

    def __init__(self, infrastructure_gateway: OperationsInfrastructureGateway) -> None:
        """
        初始化服务器信息支持对象。

        :param infrastructure_gateway: 运维基础设施网关
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway

    def resolve_server_ip(self, hostname: str) -> str:
        """
        解析服务器 IP，优先使用主机名解析，失败时回退到网卡地址。

        :param hostname: 当前主机名
        :return: 可用的 IPv4 地址
        """
        psutil = self.infrastructure_gateway.get_psutil_module()
        try:
            resolved_ip = socket.gethostbyname(hostname)
            if resolved_ip:
                return resolved_ip
        except OSError:
            pass

        for interface_addresses in psutil.net_if_addrs().values():
            for address_info in interface_addresses:
                if (
                    address_info.family == socket.AF_INET
                    and address_info.address
                    and not address_info.address.startswith('127.')
                ):
                    return address_info.address

        return '127.0.0.1'

    def build_server_info_fallback(self) -> dict[str, Any]:
        """
        构建 CLI 使用的服务器运行信息兜底数据。

        :return: 与原服务输出结构兼容的服务器运行信息字典
        """
        psutil = self.infrastructure_gateway.get_psutil_module()
        bytes2human = self.infrastructure_gateway.get_bytes2human()
        cpu_num = psutil.cpu_count(logical=True)
        cpu_usage_percent = psutil.cpu_times_percent()
        memory_info = psutil.virtual_memory()

        hostname = socket.gethostname()
        current_process = psutil.Process(os.getpid())
        start_time_stamp = current_process.create_time()
        current_time_stamp = time.time()
        difference = current_time_stamp - start_time_stamp
        days = int(difference // (24 * 60 * 60))
        hours = int((difference % (24 * 60 * 60)) // (60 * 60))
        minutes = int((difference % (60 * 60)) // 60)
        process_memory_info = current_process.memory_info()

        sys_files: list[dict[str, Any]] = []
        for partition in psutil.disk_partitions():
            try:
                disk_usage = psutil.disk_usage(partition.mountpoint)
            except Exception:
                continue

            mountpoint = partition.mountpoint.replace('\\', '')
            sys_files.append(
                {
                    'dirName': partition.device,
                    'sysTypeName': partition.fstype,
                    'typeName': f'本地固定磁盘（{mountpoint}）',
                    'total': bytes2human(disk_usage.total),
                    'used': bytes2human(disk_usage.used),
                    'free': bytes2human(disk_usage.free),
                    'usage': f'{disk_usage.percent}%',
                }
            )

        return {
            'cpu': {
                'cpuNum': cpu_num,
                'used': cpu_usage_percent.user,
                'sys': cpu_usage_percent.system,
                'free': cpu_usage_percent.idle,
            },
            'mem': {
                'total': bytes2human(memory_info.total),
                'used': bytes2human(memory_info.used),
                'free': bytes2human(memory_info.free),
                'usage': memory_info.percent,
            },
            'sys': {
                'computerIp': self.resolve_server_ip(hostname),
                'computerName': platform.node(),
                'osArch': platform.machine(),
                'osName': platform.platform(),
                'userDir': os.getcwd(),
            },
            'py': {
                'name': current_process.name(),
                'version': platform.python_version(),
                'startTime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time_stamp)),
                'runTime': f'{days}天{hours}小时{minutes}分钟',
                'home': current_process.exe(),
                'total': bytes2human(memory_info.available),
                'used': bytes2human(process_memory_info.rss),
                'free': bytes2human(memory_info.available - process_memory_info.rss),
                'usage': round((process_memory_info.rss / memory_info.available) * 100, 2),
            },
            'sysFiles': sys_files,
        }
