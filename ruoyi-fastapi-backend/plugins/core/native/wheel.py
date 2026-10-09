import base64
import csv
import hashlib
import importlib.metadata
import io
import platform
import shutil
import stat
from email.parser import Parser
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import ZipFile, ZipInfo

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import parse_tag, sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

from plugins.core.manifest.schema import PluginManifest

MAX_WHEEL_FILES = 10000
MAX_WHEEL_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
RECORD_COLUMN_COUNT = 3


def _matching_rank(path: Path, manifest: PluginManifest) -> int:
    """
    校验 wheel 身份并计算当前解释器支持的最佳平台标签优先级。

    :param path: 待处理的文件路径
    :param manifest: 插件清单对象
    :return: 匹配标签在解释器支持列表中的最小序号
    :raises ValueError: wheel 身份不匹配或当前解释器、ABI、平台不受支持
    """
    name, version, _, tags = parse_wheel_filename(path.name)
    if name != canonicalize_name(manifest.backend.native.distribution) or version != Version(manifest.version):
        raise ValueError('wheel 名称或版本与插件清单不一致')
    ranks = [
        index for index, tag in enumerate(sys_tags()) if tag in tags and tag.abi != 'none' and tag.platform != 'any'
    ]
    if not ranks:
        raise ValueError('wheel 不支持当前 Python、ABI 或平台')
    return min(ranks)


def select_native_wheel(directory: Path, manifest: PluginManifest) -> Path:
    """
    从目录中选择名称、版本及解释器平台标签均匹配的原生 wheel。

    :param directory: 包含待选择 wheel 文件的目录
    :param manifest: 插件清单对象
    :return: 兼容性优先级最高的 wheel 文件路径
    :raises ValueError: 插件不是原生类型或目录中没有匹配的 wheel
    """
    if manifest.runtime_kind != 'native':
        raise ValueError('仅 native 插件可选择 wheel')

    def candidate(path: Path) -> tuple[int, str, Path] | None:
        """
        尝试生成单个 wheel 的排序候选，忽略不兼容的文件。

        :param path: 待处理的文件路径
        :return: 标签优先级、文件名和路径，不兼容时为 None
        """
        try:
            return _matching_rank(path, manifest), path.name, path
        except ValueError:
            return None

    candidates = [item for path in directory.glob('*.whl') if (item := candidate(path)) is not None]
    if not candidates:
        raise ValueError('未找到与当前解释器及插件版本匹配的原生 wheel')
    return min(candidates)[2]


def _safe_member(name: str) -> PurePosixPath:
    """
    校验 wheel 内相对路径，拒绝目录穿越及 Windows 路径歧义。

    :param name: wheel 中的原始条目名称
    :return: 通过校验的 POSIX 相对路径
    :raises ValueError: 条目路径不符合跨平台安全要求
    """
    parts = name.rstrip('/').split('/')
    path = PurePosixPath(name)
    if (
        not parts
        or path.is_absolute()
        or '\\' in name
        or ':' in name
        or any(
            part in {'', '.', '..'} or part.endswith((' ', '.')) or PureWindowsPath(part).is_reserved()
            for part in parts
        )
    ):
        raise ValueError(f'wheel 中包含不安全路径：{name}')
    return path


def _inventory(archive: ZipFile, manifest: PluginManifest) -> tuple[dict[str, ZipInfo], str]:
    """
    检查压缩条目、资源上限及允许的模块边界，并定位唯一元数据目录。

    :param archive: 已打开的 ZIP 压缩容器
    :param manifest: 插件清单对象
    :return: 文件条目映射与 dist-info 目录名
    :raises ValueError: 压缩条目、文件类型、资源用量或顶层模块范围不合法
    """
    entries = archive.infolist()
    if len(entries) > MAX_WHEEL_FILES or sum(item.file_size for item in entries) > MAX_WHEEL_BYTES:
        raise ValueError('wheel 文件数量或解压大小超过限制')
    names: dict[str, str] = {}
    files = {}
    for entry in entries:
        path = _safe_member(entry.filename)
        normalized = str(path).casefold()
        if normalized in names:
            raise ValueError(f'wheel 包含重复或大小写冲突路径：{entry.filename}')
        names[normalized] = entry.filename
        mode = entry.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
            raise ValueError('wheel 不能包含链接或特殊文件')
        if entry.file_size > MAX_MEMBER_BYTES or entry.flag_bits & 1:
            raise ValueError('wheel 包含超限或加密文件')
        if not entry.is_dir():
            files[entry.filename] = entry

    wheel_files = [name for name in files if name.endswith('.dist-info/WHEEL') and name.count('/') == 1]
    if len(wheel_files) != 1:
        raise ValueError('wheel 必须包含唯一的发行包元数据')
    metadata_root = wheel_files[0].split('/')[0]
    allowed_roots = {manifest.backend.module, metadata_root}
    if any(PurePosixPath(name).parts[0] not in allowed_roots for name in names.values()):
        raise ValueError('wheel 只能包含插件模块及其 dist-info；不支持 .data 或其他顶层模块')
    return files, metadata_root


def _verify_dependency(value: str) -> None:
    """
    要求宿主已安装满足约束的依赖，不隐式联网安装。

    :param value: METADATA 中的单条 Requires-Dist 依赖声明
    :return: None
    :raises ValueError: 依赖使用未锁定 URL、尚未安装或版本不满足要求
    """
    requirement = Requirement(value)
    if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
        return
    if requirement.url:
        raise ValueError('原生 wheel 依赖不能使用未锁定的 URL')
    try:
        installed = importlib.metadata.version(requirement.name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValueError(f'宿主缺少 wheel 依赖：{requirement.name}') from exc
    if not requirement.specifier.contains(installed):
        raise ValueError(f'宿主 wheel 依赖版本不匹配：{requirement}')


def _verify_metadata(archive: ZipFile, metadata_root: str, wheel: Path, manifest: PluginManifest) -> None:
    """
    核对 wheel 发行包身份、版本、Python 要求及已安装依赖。

    :param archive: 已打开的 ZIP 压缩容器
    :param metadata_root: wheel 内唯一的 dist-info 元数据目录名
    :param wheel: 待验证或展开的原生 wheel 文件路径
    :param manifest: 插件清单对象
    :return: None
    :raises ValueError: 发行包元数据、平台标签或宿主依赖不匹配
    """
    metadata_path = f'{metadata_root}/METADATA'
    record_path = f'{metadata_root}/RECORD'
    if metadata_path not in archive.namelist() or record_path not in archive.namelist():
        raise ValueError('wheel 缺少 METADATA 或 RECORD')
    metadata = Parser().parsestr(archive.read(metadata_path).decode('utf-8'))
    if canonicalize_name(metadata.get('Name', '')) != canonicalize_name(manifest.backend.native.distribution):
        raise ValueError('wheel METADATA 的发行包名称不匹配')
    if Version(metadata.get('Version', '')) != Version(manifest.version):
        raise ValueError('wheel METADATA 的版本不匹配')
    if metadata.get('Requires-Python') and not SpecifierSet(metadata['Requires-Python']).contains(
        platform.python_version()
    ):
        raise ValueError('wheel Requires-Python 与当前解释器不兼容')
    for value in metadata.get_all('Requires-Dist', []):
        _verify_dependency(value)
    wheel_metadata = Parser().parsestr(archive.read(f'{metadata_root}/WHEEL').decode('utf-8'))
    declared_tags = set().union(*(parse_tag(value) for value in wheel_metadata.get_all('Tag', [])))
    if (
        declared_tags != parse_wheel_filename(wheel.name)[3]
        or wheel_metadata.get('Root-Is-Purelib', '').lower() != 'false'
    ):
        raise ValueError('WHEEL 的 tag 或原生安装布局不匹配')


def _verify_record(archive: ZipFile, files: dict[str, ZipInfo], record_path: str) -> None:
    """
    按 RECORD 校验完整文件清单、大小和 SHA256，拒绝未登记文件。

    :param archive: 已打开的 ZIP 压缩容器
    :param files: 通过安全清单校验的 wheel 文件条目映射
    :param record_path: wheel 内 RECORD 文件的相对路径
    :return: None
    :raises ValueError: RECORD 文件清单、大小或 SHA256 与实际内容不一致
    """
    records = {}
    for row in csv.reader(io.StringIO(archive.read(record_path).decode('utf-8'))):
        if len(row) != RECORD_COLUMN_COUNT or row[0] in records:
            raise ValueError('RECORD 存在非法或重复条目')
        records[row[0]] = (row[1], row[2])
    if set(records) != set(files):
        raise ValueError('RECORD 必须完整覆盖 wheel 文件，且不能引用包外文件')
    for name, entry in files.items():
        digest, size = records[name]
        if name == record_path:
            if digest or size:
                raise ValueError('RECORD 自身不应声明摘要或大小')
            continue
        if not digest.startswith('sha256=') or size != str(entry.file_size):
            raise ValueError(f'RECORD 缺少 SHA256 或大小不一致：{name}')
        hasher = hashlib.sha256()
        with archive.open(entry) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(chunk)
        actual = base64.urlsafe_b64encode(hasher.digest()).rstrip(b'=').decode('ascii')
        if digest != f'sha256={actual}':
            raise ValueError(f'wheel 文件摘要不匹配：{name}')


def install_native_wheel(wheel: Path, destination: Path, manifest: PluginManifest) -> None:
    """
    验证原生 wheel 后展开到全新目录，不覆盖已有版本或执行安装脚本。

    RECORD 只证明包内一致性，发布者身份由后续制品签名层验证。
    展开失败时仅清理本次创建的目标目录。

    :param wheel: 待验证或展开的原生 wheel 文件路径
    :param destination: 尚不存在的原生插件安装目录
    :param manifest: 插件清单对象
    :return: None
    :raises ValueError: wheel 类型、兼容性、文件内容或展开路径校验失败
    :raises FileExistsError: 目标目录已经存在，不能覆盖安装
    """
    if manifest.runtime_kind != 'native':
        raise ValueError('仅 native 插件可安装 wheel')
    target = destination.resolve()
    if target.exists():
        raise FileExistsError('原生安装目录已存在，请使用新目录并通过重启切换版本')
    with ZipFile(wheel) as archive:
        _matching_rank(wheel, manifest)
        files, metadata_root = _inventory(archive, manifest)
        _verify_metadata(archive, metadata_root, wheel, manifest)
        _verify_record(archive, files, f'{metadata_root}/RECORD')
        target.mkdir(parents=True, exist_ok=False)
        try:
            for name in files:
                path = target.joinpath(*PurePosixPath(name).parts)
                if not path.resolve().is_relative_to(target):
                    raise ValueError('wheel 解压目标越过安装目录')
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, path.open('xb') as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        except BaseException:
            # target 是本次创建且已解析的目录，所有写入都验证过边界。
            shutil.rmtree(target)
            raise
