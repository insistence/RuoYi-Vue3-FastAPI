import errno
import inspect
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

from plugins.core.artifacts.package import (
    ROOT_DOCUMENTS,
    _hash_stream,
    _read_limited,
    _regular_file,
    _scan_directory,
    _verify_documents,
    _verify_manifest,
    is_link_or_reparse,
    verify_artifact,
)
from plugins.core.artifacts.schema import (
    DEFAULT_LIMITS,
    DIGEST_PATTERN,
    ArtifactLimits,
    PublicKeyInput,
    StoredArtifact,
    VerifiedArtifact,
    safe_artifact_path,
    validate_path_inventory,
)

LOCK_TIMEOUT_SECONDS = 30.0
LOCK_RETRY_SECONDS = 0.025
STORED_ROOT_PARTS = 3
STORED_PLUGIN_PARTS = 5


class ArtifactStore:
    """
    不可变制品存储，每次使用时重新检查签名和内容。
    """

    def __init__(self, root: Path | str, *, limits: ArtifactLimits = DEFAULT_LIMITS) -> None:
        """
        初始化制品存储，并检查根目录及其父路径。

        :param root: 不可变制品存储的根目录
        :param limits: 文件数量、大小及压缩容器的资源上限
        :return: None
        """
        self.root = Path(os.path.abspath(root))
        self.limits = limits
        self._assert_real_path(self.root)

    @staticmethod
    def _assert_real_path(path: Path) -> None:
        """
        从文件系统根逐级检查路径，拒绝符号链接和 Windows 重解析点。

        :param path: 待处理的文件路径
        :return: None
        :raises ValueError: 路径本身或某一级父路径为链接或重解析点
        """
        for current in reversed([path, *path.parents]):
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if is_link_or_reparse(info):
                raise ValueError(f'制品存储路径不能包含链接或重解析点：{current}')

    def _mkdir(self, path: Path) -> None:
        """
        校验父路径后创建普通目录，并重新检查目录边界。

        :param path: 待创建的存储内部目录路径
        :return: None
        """
        if not path.is_relative_to(self.root):
            raise ValueError('制品存储路径越界')
        self._assert_real_path(path)
        path.mkdir(parents=True, exist_ok=True)
        self._assert_real_path(path)
        if not path.is_dir():
            raise ValueError('制品存储路径不是目录')

    def import_artifact(
        self,
        path: Path | str,
        trusted_keys: Mapping[str, PublicKeyInput],
        *,
        validate_candidate: Callable[[StoredArtifact], object] | None = None,
    ) -> StoredArtifact:
        """
        建立私有快照并验签，完成候选校验后发布到不可变目录。

        候选检查只用于平台、ABI 或 RECORD 等静态验证，不执行插件代码。
        目标已经存在时仍重新验签、核对全部字节并执行候选检查，保持目标内容不变。

        :param path: 待导入的 rpk 文件路径
        :param trusted_keys: 由宿主提供的签名密钥标识与可信公钥映射
        :param validate_candidate: 可选的同步只读检查回调，返回 False 或抛出异常时拒绝发布
        :return: 已发布或幂等复用的制品存储对象
        :raises ValueError: 制品、存储布局或候选检查不符合发布要求
        :raises TypeError: 候选检查回调返回异步对象
        """
        self._mkdir(self.root)
        staging_root = self.root / '.staging'
        self._mkdir(staging_root)
        temporary = Path(tempfile.mkdtemp(prefix='import-', dir=staging_root))
        try:
            snapshot = temporary / 'received.rpk'
            self._snapshot(Path(path), snapshot)
            verified = verify_artifact(snapshot, trusted_keys, limits=self.limits)
            candidate = temporary / 'object'
            self._extract(snapshot, candidate, verified)
            staged = self._verify_directory(candidate, trusted_keys)
            if staged.digest != verified.digest:
                raise ValueError('制品展开结果与签名容器不一致')
            self._validate_candidate(staged, trusted_keys, validate_candidate)
            destination = self.root / staged.plugin_id / staged.version / staged.digest
            self._mkdir(destination.parent)
            with self._digest_lock(staged.digest):
                self._assert_real_path(destination)
                if destination.exists():
                    existing = self.verify_stored(destination, trusted_keys)
                    self._validate_candidate(existing, trusted_keys, validate_candidate)
                    return existing
                # 锁涵盖目标检查与 rename；同一 digest 的其他导入不会覆盖或读取半成品。
                candidate.rename(destination)
                return replace(
                    staged,
                    root_path=destination,
                    plugin_path=destination / 'payload' / staged.plugin_id,
                )
        finally:
            # 只删除本次创建的临时目录；再次验证绝对目标属于预期 staging 边界。
            self._assert_real_path(temporary)
            if temporary.exists() and temporary.resolve().is_relative_to(staging_root.resolve()):
                shutil.rmtree(temporary)

    def _snapshot(self, source: Path, target: Path) -> None:
        """
        将输入容器复制到本次导入的私有文件，并检查文件类型与大小。

        :param source: 待复制内容的源文件路径
        :param target: 本次导入独占的容器快照路径
        :return: None
        """
        if _regular_file(source).st_size > self.limits.max_archive_bytes:
            raise ValueError('制品容器大小超过限制')
        with source.open('rb') as incoming, target.open('xb') as output:
            _hash_stream(incoming, self.limits.max_archive_bytes, output)

    def _extract(self, snapshot: Path, candidate: Path, verified: VerifiedArtifact) -> None:
        """
        将已验证容器展开到本次创建的候选目录。

        :param snapshot: 已经完成验签的私有容器快照路径
        :param candidate: 本次导入独占的候选根目录
        :param verified: 私有容器快照对应的验证结果
        :return: None
        """
        candidate.mkdir()
        expected = {item.path: item for item in verified.files}
        with ZipFile(snapshot) as archive:
            for name in sorted(ROOT_DOCUMENTS | set(expected)):
                target = candidate.joinpath(*safe_artifact_path(name).parts)
                if not target.resolve().is_relative_to(candidate.resolve()):
                    raise ValueError('制品解压目标越界')
                target.parent.mkdir(parents=True, exist_ok=True)
                limit = expected[name].size if name in expected else self.limits.max_metadata_bytes
                with archive.open(name) as source, target.open('xb') as output:
                    size, digest = _hash_stream(source, limit, output)
                if name in expected and (size, digest) != (expected[name].size, expected[name].sha256):
                    raise ValueError('制品快照在解压期间发生变化')

    def _validate_candidate(
        self,
        candidate: StoredArtifact,
        trusted_keys: Mapping[str, PublicKeyInput],
        callback: Callable[[StoredArtifact], object] | None,
    ) -> None:
        """
        执行可选的同步静态检查，并在回调完成后重新核对候选目录内容。

        :param candidate: 待执行静态检查的候选制品对象
        :param trusted_keys: 由宿主提供的签名密钥标识与可信公钥映射
        :param callback: 同步只读检查回调，为 None 时跳过附加检查
        :return: None
        :raises ValueError: 回调拒绝候选或修改了受保护内容
        :raises TypeError: 回调返回异步对象，无法同步完成检查
        """
        if callback is not None:
            result = callback(candidate)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError('制品静态候选检查必须同步执行')
            if result is False:
                raise ValueError('制品静态候选检查失败')
            # 检查器也不被允许修改制品，重新核对后才发布或返回已存在对象。
            checked = self._verify_directory(candidate.root_path, trusted_keys)
            if checked.digest != candidate.digest or checked.key_id != candidate.key_id:
                raise ValueError('制品静态检查改变了候选内容')

    def verify_stored(self, path_or_digest: Path | str, trusted_keys: Mapping[str, PublicKeyInput]) -> StoredArtifact:
        """
        按目录、插件目录或唯一摘要定位制品并重新验证信任和内容。

        :param path_or_digest: 摘要目录、其内部插件目录，或当前存储中唯一的制品摘要
        :param trusted_keys: 由宿主提供的签名密钥标识与可信公钥映射
        :return: 当前信任配置下通过验证的制品存储对象
        :raises ValueError: 定位结果不唯一、越过存储边界或制品验证失败
        """
        value = str(path_or_digest)
        if DIGEST_PATTERN.fullmatch(value):
            matches = list(self.root.glob(f'*/*/{value}'))
            if len(matches) != 1:
                raise ValueError('制品 digest 不存在或对应多个存储目录')
            path = matches[0]
        else:
            path = Path(path_or_digest)
            if not path.is_absolute():
                path = self.root / path
            path = Path(os.path.abspath(path))
        if not path.is_relative_to(self.root):
            raise ValueError('制品目录不属于当前存储根目录')
        self._assert_real_path(path)
        parts = path.relative_to(self.root).parts
        if len(parts) == STORED_PLUGIN_PARTS and parts[3:] == ('payload', parts[0]):
            path = path.parents[1]
            parts = parts[:STORED_ROOT_PARTS]
        if len(parts) != STORED_ROOT_PARTS or not DIGEST_PATTERN.fullmatch(parts[2]):
            raise ValueError('制品目录必须遵循 <plugin_id>/<version>/<digest> 布局')
        artifact = self._verify_directory(path, trusted_keys)
        if parts != (artifact.plugin_id, artifact.version, artifact.digest):
            raise ValueError('制品目录身份或 digest 与签名元数据不一致')
        return artifact

    def _verify_directory(self, directory: Path, trusted_keys: Mapping[str, PublicKeyInput]) -> StoredArtifact:
        """
        核对制品目录内部布局、签名文档和全部已登记文件。

        :param directory: 待验证的候选目录或已发布制品根目录
        :param trusted_keys: 由宿主提供的签名密钥标识与可信公钥映射
        :return: 通过目录完整性校验的制品存储对象
        :raises ValueError: 目录布局、签名、文件清单或实际内容不一致
        """
        self._assert_real_path(directory)
        files, directories = _scan_directory(directory, self.limits)
        if not ROOT_DOCUMENTS.issubset(files):
            raise ValueError('存储制品缺少签名文档')
        with files['artifacts.json'].open('rb') as source:
            metadata_bytes = _read_limited(source, self.limits.max_metadata_bytes)
        with files['signature.json'].open('rb') as source:
            signature_bytes = _read_limited(source, self.limits.max_signature_bytes)
        metadata, signature, digest = _verify_documents(metadata_bytes, signature_bytes, trusted_keys, self.limits)
        if set(files) != ROOT_DOCUMENTS | {item.path for item in metadata.files}:
            raise ValueError('存储制品存在额外或缺失文件')
        validate_path_inventory(tuple(files), directories)
        for item in metadata.files:
            with files[item.path].open('rb') as source:
                size, actual = _hash_stream(source, item.size)
            if (size, actual) != (item.size, item.sha256):
                raise ValueError(f'存储制品文件 SHA256 或大小不匹配：{item.path}')
        with files[f'payload/{metadata.plugin_id}/plugin.yaml'].open('rb') as source:
            manifest = _verify_manifest(_read_limited(source, self.limits.max_manifest_bytes), metadata, self.limits)
        return StoredArtifact(
            metadata.plugin_id,
            metadata.version,
            digest,
            signature.key_id,
            metadata.files,
            metadata,
            signature,
            manifest,
            directory,
            directory / 'payload' / metadata.plugin_id,
        )

    @contextmanager
    def _digest_lock(self, digest: str) -> Iterator[None]:
        """
        使用操作系统文件锁串行化同一摘要的发布，进程退出时自动释放。

        :param digest: 制品规范元数据的小写 SHA256 摘要
        :return: 持有对应摘要锁的上下文
        :raises TimeoutError: 等待同一制品摘要的文件锁超时
        """
        lock_root = self.root / '.locks'
        self._mkdir(lock_root)
        path = lock_root / f'{digest}.lock'
        self._assert_real_path(path)
        flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        descriptor = os.open(path, flags, 0o600)
        acquired = False
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('制品锁文件必须为普通文件')
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while not acquired:
                try:
                    self._lock_file(descriptor, unlock=False)
                    acquired = True
                except OSError as exc:  # noqa: PERF203 - 操作系统非阻塞锁必须重试
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError('等待制品导入锁超时') from exc
                    time.sleep(LOCK_RETRY_SECONDS)
            if not info.st_size:
                # Windows 支持锁住 EOF 之后的字节；持锁后才初始化，避免首次创建竞争。
                os.write(descriptor, b'\0')
            yield
        finally:
            if acquired:
                self._lock_file(descriptor, unlock=True)
            os.close(descriptor)

    @staticmethod
    def _lock_file(descriptor: int, *, unlock: bool) -> None:
        """
        按平台获取或释放文件描述符上的非阻塞排他锁。

        :param descriptor: 本次发布锁文件的文件描述符
        :param unlock: 是否释放已有锁，为 False 时尝试获取锁
        :return: None
        """
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == 'nt':
            import msvcrt  # noqa: PLC0415

            msvcrt.locking(descriptor, msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415

            fcntl.flock(descriptor, fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB)
