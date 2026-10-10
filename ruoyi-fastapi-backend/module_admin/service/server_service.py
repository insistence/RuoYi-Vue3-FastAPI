import os
import platform
import socket
import time
from datetime import datetime, timezone

import anyio
import psutil

from module_admin.entity.vo.server_vo import CpuInfo, MemoryInfo, PyInfo, ServerMonitorModel, SysFiles, SysInfo
from utils.common_util import bytes2human


class ServerService:
    """
    服务监控模块服务层
    """

    @staticmethod
    async def get_server_monitor_info() -> ServerMonitorModel:
        # CPU信息
        # 获取CPU总核心数
        cpu_num = psutil.cpu_count(logical=True)
        cpu_usage_percent = psutil.cpu_times_percent()
        cpu_used = cpu_usage_percent.user
        cpu_sys = cpu_usage_percent.system
        cpu_free = cpu_usage_percent.idle
        cpu = CpuInfo(cpuNum=cpu_num, used=cpu_used, sys=cpu_sys, free=cpu_free)

        # 内存信息
        memory_info = psutil.virtual_memory()
        memory_total = bytes2human(memory_info.total)
        memory_used = bytes2human(memory_info.used)
        memory_free = bytes2human(memory_info.free)
        memory_usage = memory_info.percent
        mem = MemoryInfo(total=memory_total, used=memory_used, free=memory_free, usage=memory_usage)

        # 主机信息
        # 获取主机名
        hostname = socket.gethostname()
        # 获取IP
        computer_ip = socket.gethostbyname(hostname)
        os_name = platform.platform()
        computer_name = platform.node()
        os_arch = platform.machine()
        user_dir = str(await anyio.Path.cwd())
        sys = SysInfo(
            computerIp=computer_ip, computerName=computer_name, osArch=os_arch, osName=os_name, userDir=user_dir
        )

        # python解释器信息
        current_pid = os.getpid()
        current_process = psutil.Process(current_pid)
        python_name = current_process.name()
        python_version = platform.python_version()
        python_home = current_process.exe()
        start_time_stamp = current_process.create_time()
        start_time = datetime.fromtimestamp(start_time_stamp, tz=timezone.utc)
        current_time_stamp = time.time()
        difference = current_time_stamp - start_time_stamp
        # 将时间差转换为天、小时和分钟数
        days = int(difference // (24 * 60 * 60))  # 每天的秒数
        hours = int((difference % (24 * 60 * 60)) // (60 * 60))  # 每小时的秒数
        minutes = int((difference % (60 * 60)) // 60)  # 每分钟的秒数
        run_time = f'{days}天{hours}小时{minutes}分钟'
        # 获取当前Python程序的pid
        pid = os.getpid()
        # 获取该进程的内存信息
        current_process_memory_info = psutil.Process(pid).memory_info()
        py = PyInfo(
            name=python_name,
            version=python_version,
            startTime=start_time,
            runTime=run_time,
            home=python_home,
            total=bytes2human(memory_info.available),
            used=bytes2human(current_process_memory_info.rss),
            free=bytes2human(memory_info.available - current_process_memory_info.rss),
            usage=round((current_process_memory_info.rss / memory_info.available) * 100, 2),
        )

        # 磁盘信息
        sys_files = ServerService._get_disk_info()

        result = ServerMonitorModel(cpu=cpu, mem=mem, sys=sys, py=py, sysFiles=sys_files)

        return result

    @classmethod
    def _get_disk_info(cls) -> list[SysFiles]:
        """
        获取可访问的磁盘信息

        :return: 磁盘信息列表
        """
        sys_files = []
        for partition in psutil.disk_partitions():
            disk_info = cls._read_disk_info(partition.device, partition.mountpoint, partition.fstype)
            if disk_info is not None:
                sys_files.append(disk_info)
        if sys_files:
            return sys_files

        # 默认分区列表会过滤overlay等容器文件系统，无可读分区时补充根文件系统
        root_path = os.path.abspath(os.sep)
        # 仅匹配根目录，避免展示proc、sysfs等虚拟挂载
        root_partition = next(
            (partition for partition in psutil.disk_partitions(all=True) if partition.mountpoint == root_path),
            None,
        )
        disk_info = cls._read_disk_info(
            root_partition.device if root_partition else root_path,
            root_path,
            root_partition.fstype if root_partition else '',
        )

        return [disk_info] if disk_info is not None else []

    @staticmethod
    def _read_disk_info(device: str, mountpoint: str, filesystem: str) -> SysFiles | None:
        """
        读取指定磁盘的容量信息

        :param device: 磁盘设备名称
        :param mountpoint: 磁盘挂载路径
        :param filesystem: 文件系统类型
        :return: 磁盘容量信息，挂载路径不可访问时返回None
        """
        try:
            disk_usage = psutil.disk_usage(mountpoint)
        except OSError:
            # 跳过不存在或无权访问的挂载路径
            return None

        return SysFiles(
            dirName=device,
            sysTypeName=filesystem,
            typeName='本地固定磁盘（' + mountpoint.replace('\\', '') + '）',
            total=bytes2human(disk_usage.total),
            used=bytes2human(disk_usage.used),
            free=bytes2human(disk_usage.free),
            usage=f'{disk_usage.percent}%',
        )
