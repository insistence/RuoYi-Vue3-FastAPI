import json
import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.core.management.entity.do.models import SysPlugin
from plugins.core.management.entity.do.release_models import SysPluginArtifact, SysPluginRelease, SysPluginWorker
from utils.time_util import TimezoneUtil


class PluginReleaseConflictError(ValueError):
    """
    发布代际或维护证据发生并发变化，需要调用方重新读取并确认目标。
    """


def _check_digest(value: str) -> None:
    """
    校验制品摘要是否为64位小写 SHA256 字符串。

    :param value: 待校验的制品摘要
    :return: None
    :raises ValueError: 摘要不是64位小写十六进制字符串
    """
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('制品digest必须是小写SHA256')


def _check_generation(value: str) -> None:
    """
    校验发布代际或进程标识是否为32位小写 UUID 十六进制字符串。

    :param value: 待校验的发布代际或宿主进程标识
    :return: None
    :raises ValueError: 标识不是32位小写十六进制字符串
    """
    if not re.fullmatch(r'[0-9a-f]{32}', value):
        raise ValueError('发布代际或worker ID必须是32位小写UUID十六进制字符串')


async def _insert_if_missing(db: AsyncSession, model: Any, values: dict[str, Any]) -> None:
    """
    使用数据库方言提供的幂等插入保留调用方事务边界。

    避免唯一键竞争回滚外层事务，也避免 SQLite 首个保存点导致提前提交。

    :param db: 当前操作使用的数据库会话
    :param model: 待插入记录的 ORM 模型类
    :param values: 字段名与待插入值组成的字典
    :return: None
    :raises ValueError: 当前数据库方言不受制品发布模块支持
    """
    dialect = db.get_bind().dialect.name
    primary_keys = [column.name for column in model.__table__.primary_key]
    if dialect == 'mysql':
        statement = mysql_insert(model).values(**values)
        statement = statement.on_duplicate_key_update(**{primary_keys[0]: getattr(model, primary_keys[0])})
    elif dialect == 'postgresql':
        statement = pg_insert(model).values(**values).on_conflict_do_nothing(index_elements=primary_keys)
    elif dialect == 'sqlite':
        statement = sqlite_insert(model).values(**values).on_conflict_do_nothing(index_elements=primary_keys)
    else:
        raise ValueError(f'制品发布不支持数据库方言：{dialect}')
    await db.execute(statement)


class PluginReleaseDao:
    """
    制品、发布目标及进程报告的数据访问层，事务提交由调用方负责。
    """

    @classmethod
    async def register_artifact(
        cls,
        db: AsyncSession,
        *,
        digest: str,
        plugin_id: str,
        version: str,
        key_id: str,
        relative_path: str,
        manifest_json: str,
        created_by: str | None = None,
    ) -> SysPluginArtifact:
        """
        首次登记或严格幂等复用制品记录，拒绝覆盖相同摘要的不同元数据。

        :param db: 当前操作使用的数据库会话
        :param digest: 制品规范元数据的小写 SHA256 摘要
        :param plugin_id: 插件ID
        :param version: 插件制品版本
        :param key_id: 签名公钥在宿主信任配置中的标识
        :param relative_path: 制品在不可变存储中的规范相对目录
        :param manifest_json: 已验证插件清单的 JSON 对象文本
        :param created_by: 首次登记制品的操作人
        :return: 已登记且元数据一致的制品记录
        :raises ValueError: 摘要、目录或清单无效，或已有同摘要记录的元数据不一致
        """
        _check_digest(digest)
        path = PurePosixPath(relative_path)
        if (
            not relative_path
            or path.is_absolute()
            or '\\' in relative_path
            or ':' in relative_path
            or any(part in {'', '.', '..'} for part in relative_path.split('/'))
        ):
            raise ValueError('制品目录必须是存储内的规范相对路径')
        manifest = json.loads(manifest_json)
        if not isinstance(manifest, dict):
            raise ValueError('制品清单必须是JSON对象')
        values = {
            'plugin_id': plugin_id,
            'version': version,
            'key_id': key_id,
            'relative_path': relative_path,
            'manifest_json': json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        }
        artifact = await cls.get_artifact(db, digest)
        if artifact is None:
            await _insert_if_missing(db, SysPluginArtifact, {'digest': digest, 'created_by': created_by, **values})
            artifact = (
                await db.scalars(select(SysPluginArtifact).where(SysPluginArtifact.digest == digest).with_for_update())
            ).one()
        if any(getattr(artifact, key) != value for key, value in values.items()):
            raise ValueError('已存在制品digest的元数据不一致，拒绝覆盖')
        return artifact

    @staticmethod
    async def get_artifact(db: AsyncSession, digest: str) -> SysPluginArtifact | None:
        """
        根据制品摘要查询不可变制品索引。

        :param db: 当前操作使用的数据库会话
        :param digest: 制品规范元数据的小写 SHA256 摘要
        :return: 制品记录，不存在时为 None
        """
        return await db.get(SysPluginArtifact, digest)

    @staticmethod
    async def list_artifacts(db: AsyncSession, plugin_id: str | None = None) -> list[SysPluginArtifact]:
        """
        按插件ID和摘要顺序查询制品列表。

        :param db: 当前操作使用的数据库会话
        :param plugin_id: 可选的插件ID过滤条件，为 None 时查询全部记录
        :return: 匹配过滤条件的制品记录列表
        """
        statement = select(SysPluginArtifact).order_by(SysPluginArtifact.plugin_id, SysPluginArtifact.digest)
        if plugin_id is not None:
            statement = statement.where(SysPluginArtifact.plugin_id == plugin_id)
        return list((await db.scalars(statement)).all())

    @classmethod
    async def ensure_release(cls, db: AsyncSession, plugin_id: str, *, actor: str | None = None) -> SysPluginRelease:
        """
        查询或幂等创建插件发布记录，不提交调用方事务。

        :param db: 当前操作使用的数据库会话
        :param plugin_id: 插件ID
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :return: 已存在或新创建的插件发布记录
        """
        release = await cls.get_release(db, plugin_id)
        if release is None:
            await _insert_if_missing(
                db,
                SysPluginRelease,
                {
                    'plugin_id': plugin_id,
                    'generation': uuid4().hex,
                    'expected_workers': 1,
                    'prepare_status': 'idle',
                    'create_by': actor,
                    'update_by': actor,
                },
            )
            release = (
                await db.scalars(
                    select(SysPluginRelease).where(SysPluginRelease.plugin_id == plugin_id).with_for_update()
                )
            ).one()
        return release

    @staticmethod
    async def get_release(db: AsyncSession, plugin_id: str) -> SysPluginRelease | None:
        """
        重新读取指定插件的发布记录，刷新会话中的已有状态。

        :param db: 当前操作使用的数据库会话
        :param plugin_id: 插件ID
        :return: 插件发布记录，不存在时为 None
        """
        return await db.get(SysPluginRelease, plugin_id, populate_existing=True)

    @staticmethod
    async def list_releases(db: AsyncSession) -> list[SysPluginRelease]:
        """
        按插件ID顺序查询全部发布目标。

        :param db: 当前操作使用的数据库会话
        :return: 插件发布记录列表
        """
        return list((await db.scalars(select(SysPluginRelease).order_by(SysPluginRelease.plugin_id))).all())

    @classmethod
    async def set_preparation_status(
        cls,
        db: AsyncSession,
        plugin_id: str,
        *,
        status: str,
        prepared_digest: str | None = None,
        prepared_version: str | None = None,
        last_error: str | None = None,
        actor: str | None = None,
        expected_generation: str | None = None,
    ) -> SysPluginRelease:
        """
        在匹配代际下更新维护准备证据，失败或重新准备时清除旧证据。

        :param db: 当前操作使用的数据库会话
        :param plugin_id: 插件ID
        :param status: 维护准备状态
        :param prepared_digest: 维护准备成功的制品摘要
        :param prepared_version: 维护准备确认的数据结构安装版本
        :param last_error: 最近一次维护准备失败的错误说明
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :param expected_generation: 预期发布代际，未提供时使用刚读取的当前代际
        :return: 更新后的发布记录
        :raises ValueError: 准备状态或成功证据不完整，或制品不属于该插件
        :raises PluginReleaseConflictError: 维护结果写入前发布代际发生变化
        """
        if status not in {'idle', 'preparing', 'prepared', 'failed'}:
            raise ValueError('非法维护准备状态')
        if status == 'prepared':
            if not prepared_digest or not prepared_version:
                raise ValueError('准备成功必须提供制品digest和数据结构安装版本')
            artifact = await cls.get_artifact(db, prepared_digest)
            if artifact is None or artifact.plugin_id != plugin_id:
                raise ValueError('准备制品不存在或不属于该插件')
        else:
            prepared_digest = prepared_version = None
        release = await cls.ensure_release(db, plugin_id, actor=actor)
        expected_generation = expected_generation or release.generation
        statement = (
            update(SysPluginRelease)
            .where(SysPluginRelease.plugin_id == plugin_id, SysPluginRelease.generation == expected_generation)
            .values(
                prepare_status=status,
                prepared_digest=prepared_digest,
                prepared_version=prepared_version,
                last_error=last_error,
                update_by=actor,
            )
        )
        result = await db.execute(statement.execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise PluginReleaseConflictError('发布代际已变化，维护准备结果未写入')
        await db.flush()
        await db.refresh(release)
        return release

    @classmethod
    async def select_target(
        cls,
        db: AsyncSession,
        plugin_id: str,
        *,
        target_digest: str,
        expected_generation: str,
        expected_workers: int = 1,
        actor: str | None = None,
    ) -> SysPluginRelease:
        """
        以比较并更新方式切换代码目标，保留已安装数据结构版本和进程报告。

        :param db: 当前操作使用的数据库会话
        :param plugin_id: 插件ID
        :param target_digest: 当前发布目标的制品摘要
        :param expected_generation: 调用方读取并确认的发布代际，用于并发状态校验
        :param expected_workers: 预期启动并报告当前目标的宿主进程数量
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :return: 目标和代际更新后的发布记录
        :raises ValueError: 目标制品、准备证据、已安装版本或预期进程数量不合法
        :raises PluginReleaseConflictError: 发布代际或维护准备状态在目标切换前发生变化
        """
        _check_digest(target_digest)
        _check_generation(expected_generation)
        if isinstance(expected_workers, bool) or not isinstance(expected_workers, int) or expected_workers < 1:
            raise ValueError('expected_workers必须为正整数')
        artifact = await cls.get_artifact(db, target_digest)
        release = await cls.get_release(db, plugin_id)
        if artifact is None or artifact.plugin_id != plugin_id:
            raise ValueError('目标制品不存在或不属于该插件')
        if release is None or release.generation != expected_generation:
            raise PluginReleaseConflictError('发布代际已变化，请重新读取目标')
        if release.prepare_status != 'prepared' or release.prepared_digest != target_digest:
            raise ValueError('目标制品尚未完成维护准备')
        installed_version = await db.scalar(select(SysPlugin.installed_version).where(SysPlugin.plugin_id == plugin_id))
        if not installed_version or release.prepared_version != installed_version:
            raise ValueError('维护准备版本与当前数据结构安装版本不一致')
        installed_matches = (
            select(SysPlugin.plugin_id)
            .where(SysPlugin.plugin_id == plugin_id, SysPlugin.installed_version == SysPluginRelease.prepared_version)
            .exists()
        )
        statement = (
            update(SysPluginRelease)
            .where(
                SysPluginRelease.plugin_id == plugin_id,
                SysPluginRelease.generation == expected_generation,
                SysPluginRelease.prepare_status == 'prepared',
                SysPluginRelease.prepared_digest == target_digest,
                installed_matches,
            )
            .values(
                previous_digest=release.target_digest
                if target_digest != release.target_digest
                else release.previous_digest,
                target_digest=target_digest,
                generation=uuid4().hex,
                expected_workers=expected_workers,
                update_by=actor,
                last_error=None,
            )
        )
        result = await db.execute(statement.execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise PluginReleaseConflictError('发布代际或维护准备状态已变化，目标未切换')
        await db.flush()
        await db.refresh(release)
        return release

    @staticmethod
    async def upsert_worker_report(
        db: AsyncSession,
        *,
        worker_id: str,
        plugin_id: str,
        state: str,
        heartbeat_time: datetime,
        artifact_digest: str | None = None,
        version: str | None = None,
        generation: str | None = None,
        error: str | None = None,
    ) -> SysPluginWorker:
        """
        登记进程实际加载状态，阻止较旧心跳覆盖较新的报告。

        :param db: 当前操作使用的数据库会话
        :param worker_id: 宿主进程的32位小写 UUID 标识
        :param plugin_id: 插件ID，宿主进程本身使用 __runtime__
        :param state: 进程当前状态
        :param heartbeat_time: 本次报告的带时区心跳时间，将统一为 UTC 毫秒精度
        :param artifact_digest: 进程实际加载的制品摘要，宿主报告不设置此值
        :param version: 进程实际加载的制品版本，宿主报告不设置此值
        :param generation: 进程实际加载的发布代际，宿主报告不设置此值
        :param error: 进程加载或运行失败的错误说明
        :return: 插入或更新后的进程报告记录
        :raises ValueError: 报告标识、状态、时间或宿主与插件字段组合不合法
        """
        _check_generation(worker_id)
        if generation is not None:
            _check_generation(generation)
        if artifact_digest is not None:
            _check_digest(artifact_digest)
        if state not in {'starting', 'ready', 'failed', 'stopped'}:
            raise ValueError('非法worker状态')
        heartbeat_time = TimezoneUtil.to_utc_milliseconds(heartbeat_time)
        if plugin_id == '__runtime__' and any(value is not None for value in (artifact_digest, version, generation)):
            raise ValueError('宿主worker报告不能声明插件制品或代际')
        values = {
            'artifact_digest': artifact_digest,
            'version': version,
            'generation': generation,
            'state': state,
            'heartbeat_time': heartbeat_time,
            'error': error,
        }
        identity = (worker_id, plugin_id)
        worker = await db.get(SysPluginWorker, identity)
        if worker is None:
            await _insert_if_missing(db, SysPluginWorker, {'worker_id': worker_id, 'plugin_id': plugin_id, **values})
            worker = (
                await db.scalars(
                    select(SysPluginWorker)
                    .where(SysPluginWorker.worker_id == worker_id, SysPluginWorker.plugin_id == plugin_id)
                    .with_for_update()
                )
            ).one()
        await db.execute(
            update(SysPluginWorker)
            .where(
                SysPluginWorker.worker_id == worker_id,
                SysPluginWorker.plugin_id == plugin_id,
                SysPluginWorker.heartbeat_time <= heartbeat_time,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await db.flush()
        await db.refresh(worker)
        return worker

    @staticmethod
    async def list_worker_reports(db: AsyncSession, plugin_id: str | None = None) -> list[SysPluginWorker]:
        """
        查询进程报告，指定插件时同时包含宿主运行状态行。

        :param db: 当前操作使用的数据库会话
        :param plugin_id: 可选的插件ID过滤条件，为 None 时查询全部记录
        :return: 匹配过滤条件的宿主和插件报告列表
        """
        statement = select(SysPluginWorker).order_by(SysPluginWorker.worker_id, SysPluginWorker.plugin_id)
        if plugin_id is not None:
            statement = statement.where(SysPluginWorker.plugin_id.in_([plugin_id, '__runtime__']))
        return list((await db.scalars(statement)).all())
