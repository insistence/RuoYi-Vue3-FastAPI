import os
from types import SimpleNamespace
from unittest.mock import Mock, call

import psutil
import pytest

from module_admin.service.server_service import ServerService
from utils.common_util import bytes2human

ROOT_PATH = os.path.abspath(os.sep)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('devices', 'mountpoints', 'filesystem'),
    [
        (('/dev/vda1', '/dev/vdb1'), ('/', '/srv/data'), 'ext4'),
        (('C:\\', 'D:\\'), ('C:\\', 'D:\\'), 'NTFS'),
    ],
    ids=['linux', 'windows'],
)
async def test_server_disks_sample_each_mountpoint_once(
    monkeypatch: pytest.MonkeyPatch, devices: tuple[str, str], mountpoints: tuple[str, str], filesystem: str
) -> None:
    """设备名与挂载点不同的 Linux 分区和 Windows 盘符均返回完整容量快照。"""
    partitions = Mock(
        return_value=[
            SimpleNamespace(device=device, mountpoint=mountpoint, fstype=filesystem)
            for device, mountpoint in zip(devices, mountpoints, strict=True)
        ]
    )
    usage = Mock(
        side_effect=[
            SimpleNamespace(total=1024**3, used=256 * 1024**2, free=768 * 1024**2, percent=25.0),
            SimpleNamespace(total=2 * 1024**3, used=1024**3, free=1024**3, percent=50.0),
        ]
    )
    monkeypatch.setattr(psutil, 'disk_partitions', partitions)
    monkeypatch.setattr(psutil, 'disk_usage', usage)

    result = await ServerService.get_server_monitor_info()

    partitions.assert_called_once_with()
    assert usage.call_args_list == [call(mountpoint) for mountpoint in mountpoints]
    assert [disk.model_dump(by_alias=True) for disk in result.sys_files] == [
        {
            'dirName': devices[0],
            'sysTypeName': filesystem,
            'typeName': '本地固定磁盘（' + mountpoints[0].replace('\\', '') + '）',
            'total': '1.0GB',
            'used': '256.0MB',
            'free': '768.0MB',
            'usage': '25.0%',
        },
        {
            'dirName': devices[1],
            'sysTypeName': filesystem,
            'typeName': '本地固定磁盘（' + mountpoints[1].replace('\\', '') + '）',
            'total': '2.0GB',
            'used': '1.0GB',
            'free': '1.0GB',
            'usage': '50.0%',
        },
    ]


def test_unreadable_mount_does_not_hide_other_disks(monkeypatch: pytest.MonkeyPatch) -> None:
    """失效挂载点单独跳过，后续可读磁盘仍保留。"""
    partitions = Mock(
        return_value=[
            SimpleNamespace(device='/dev/removed', mountpoint='/removed', fstype='ext4'),
            SimpleNamespace(device='/dev/data', mountpoint='/data', fstype='ext4'),
        ]
    )
    usage = Mock(
        side_effect=[FileNotFoundError('unmounted'), SimpleNamespace(total=1024, used=256, free=768, percent=25.0)]
    )
    monkeypatch.setattr(psutil, 'disk_partitions', partitions)
    monkeypatch.setattr(psutil, 'disk_usage', usage)

    disks = ServerService._get_disk_info()

    assert [disk.dir_name for disk in disks] == ['/dev/data']
    assert usage.call_args_list == [call('/removed'), call('/data')]
    partitions.assert_called_once_with()


@pytest.mark.parametrize(
    'unreadable_physical_disk', [False, True], ids=['no-physical-disk', 'unreadable-physical-disk']
)
def test_container_root_filesystem_is_sampled_when_physical_disks_are_unavailable(
    monkeypatch: pytest.MonkeyPatch, unreadable_physical_disk: bool
) -> None:
    """容器物理磁盘不可见时只回退到根 overlay，排除 proc 等虚拟挂载。"""
    root = ROOT_PATH
    physical = [SimpleNamespace(device='/dev/host', mountpoint='/host', fstype='ext4')]
    partitions = Mock(
        side_effect=[
            physical if unreadable_physical_disk else [],
            [
                SimpleNamespace(device='proc', mountpoint='/proc', fstype='proc'),
                SimpleNamespace(device='overlay', mountpoint=root, fstype='overlay'),
            ],
        ]
    )
    snapshot = SimpleNamespace(total=1024**3, used=256 * 1024**2, free=768 * 1024**2, percent=25.0)
    usage = Mock(side_effect=[PermissionError('not exposed'), snapshot] if unreadable_physical_disk else [snapshot])
    monkeypatch.setattr(psutil, 'disk_partitions', partitions)
    monkeypatch.setattr(psutil, 'disk_usage', usage)

    disks = ServerService._get_disk_info()

    assert partitions.call_args_list == [call(), call(all=True)]
    assert usage.call_args_list == ([call('/host')] if unreadable_physical_disk else []) + [call(root)]
    assert len(disks) == 1
    assert disks[0].dir_name == 'overlay'
    assert disks[0].sys_type_name == 'overlay'
    assert disks[0].total == '1.0GB'
    assert disks[0].used == '256.0MB'
    assert disks[0].free == '768.0MB'
    assert disks[0].usage == '25.0%'


def test_missing_mount_metadata_still_reads_real_root_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    """挂载清单为空时仍以真实 psutil 读取当前根目录，且不虚构文件系统类型。"""
    root = ROOT_PATH
    expected = psutil.disk_usage(root)
    monkeypatch.setattr(psutil, 'disk_partitions', Mock(return_value=[]))

    disks = ServerService._get_disk_info()

    assert len(disks) == 1
    assert disks[0].dir_name == root
    assert disks[0].sys_type_name == ''
    assert disks[0].total == bytes2human(expected.total)
    assert disks[0].used
    assert disks[0].free
    assert disks[0].usage.endswith('%')


@pytest.mark.asyncio
async def test_server_monitor_retains_other_metrics_when_all_disks_are_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """分区和根目录都无读取权限时返回空列表，CPU 等其它监控仍可用。"""
    root = ROOT_PATH
    partition = SimpleNamespace(device='overlay', mountpoint=root, fstype='overlay')
    partitions = Mock(side_effect=[[], [partition]])
    usage = Mock(side_effect=PermissionError('filesystem not accessible'))
    monkeypatch.setattr(psutil, 'disk_partitions', partitions)
    monkeypatch.setattr(psutil, 'disk_usage', usage)

    result = await ServerService.get_server_monitor_info()

    assert result.sys_files == []
    assert result.cpu.cpu_num > 0
    assert result.mem.total
    assert result.sys.os_name
    assert result.py.version
    usage.assert_called_once_with(root)


def test_unexpected_disk_sampling_errors_are_not_silently_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """只处理文件系统访问错误，采样逻辑异常不能被伪装成无磁盘。"""
    monkeypatch.setattr(psutil, 'disk_usage', Mock(side_effect=ValueError('invalid disk snapshot')))

    with pytest.raises(ValueError, match='invalid disk snapshot'):
        ServerService._read_disk_info('/dev/data', '/data', 'ext4')
