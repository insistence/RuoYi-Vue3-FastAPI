from typing import Any

from cli.exit_codes import DATABASE_ERROR
from cli.runtime.base import RUNTIME_ENVIRONMENT, RuntimeEnvironmentService

from .gateway import DatabaseInfrastructureGateway
from .support import DatabaseAlembicCommandSupport, DatabaseRevisionSupport


class DatabaseRuntimeService:
    """
    数据库运行时服务。

    该服务作为数据库运行时 facade，对外统一暴露数据库连通性检查、
    Alembic 版本读取与迁移命令执行入口。

    :param runtime_environment: 运行时环境服务
    :param infrastructure_gateway: 数据库基础设施网关
    :param revision_support: 数据库迁移版本支持对象
    :param alembic_command_support: 数据库 Alembic 命令支持对象
    """

    def __init__(
        self,
        *,
        runtime_environment: RuntimeEnvironmentService | None = None,
        infrastructure_gateway: DatabaseInfrastructureGateway | None = None,
        revision_support: DatabaseRevisionSupport | None = None,
        alembic_command_support: DatabaseAlembicCommandSupport | None = None,
    ) -> None:
        """
        初始化数据库运行时服务。

        :param runtime_environment: 运行时环境服务
        :param infrastructure_gateway: 数据库基础设施网关
        :param revision_support: 数据库迁移版本支持对象
        :param alembic_command_support: 数据库 Alembic 命令支持对象
        :return: None
        """
        self.runtime_environment = runtime_environment or RUNTIME_ENVIRONMENT
        self.infrastructure_gateway = infrastructure_gateway or DatabaseInfrastructureGateway()
        self.revision_support = revision_support or DatabaseRevisionSupport(
            self.infrastructure_gateway,
            self.runtime_environment,
        )
        self.alembic_command_support = alembic_command_support or DatabaseAlembicCommandSupport(
            self.runtime_environment
        )

    async def ping_database(self) -> dict[str, Any]:
        """
        检查数据库连通性。

        :return: 数据库检查结果
        """
        create_async_db_engine = self.infrastructure_gateway.get_async_db_engine_factory()
        text = self.infrastructure_gateway.get_sqlalchemy_text()
        engine = create_async_db_engine(echo=False)
        try:
            async with engine.connect() as connection:
                await connection.execute(text('SELECT 1'))
            return {'ok': True, 'message': '数据库连接成功'}
        except Exception as exc:
            return {'ok': False, 'message': '数据库连接失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        finally:
            await engine.dispose()

    def get_current_revision(self) -> dict[str, Any]:
        """
        获取数据库当前迁移版本。

        :return: 当前迁移版本信息
        """
        create_sync_db_engine = self.infrastructure_gateway.get_sync_db_engine_factory()
        text = self.infrastructure_gateway.get_sqlalchemy_text()
        engine = create_sync_db_engine(echo=False)
        try:
            with engine.connect() as connection:
                revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
            return {'ok': True, 'currentRevision': revision}
        except Exception as exc:
            return {'ok': False, 'message': '读取数据库迁移版本失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        finally:
            engine.dispose()

    def upgrade_database(self, revision: str = 'head', *, dry_run: bool = False) -> dict[str, Any]:
        """
        执行数据库迁移升级。

        :param revision: 目标迁移版本，默认为 `head`
        :param dry_run: 是否仅演练执行
        :return: 数据库迁移执行结果
        """
        return self.alembic_command_support.run_alembic_command(
            'upgrade',
            revision,
            success_message=f'数据库已升级到 {revision}',
            failure_message='数据库升级失败',
            dry_run=dry_run,
        )

    def init_database(self, *, dry_run: bool = False) -> dict[str, Any]:
        """
        初始化数据库到最新迁移版本。

        :param dry_run: 是否仅演练执行
        :return: 数据库初始化结果
        """
        return self.alembic_command_support.run_alembic_command(
            'upgrade',
            'head',
            success_message='数据库初始化完成，当前版本已同步到 head',
            failure_message='数据库初始化失败',
            dry_run=dry_run,
        )

    def downgrade_database(self, revision: str = '-1', *, dry_run: bool = False) -> dict[str, Any]:
        """
        执行数据库回退。

        :param revision: 目标回退版本，默认为 `-1`
        :param dry_run: 是否仅演练执行
        :return: 数据库回退结果
        """
        return self.alembic_command_support.run_alembic_command(
            'downgrade',
            revision,
            success_message=f'数据库已回退到 {revision}',
            failure_message='数据库回退失败',
            dry_run=dry_run,
        )

    def create_revision(self, message: str, *, autogenerate: bool = False, dry_run: bool = False) -> dict[str, Any]:
        """
        创建新的 Alembic 迁移版本文件。

        :param message: 迁移说明
        :param autogenerate: 是否自动生成变更
        :param dry_run: 是否仅演练执行
        :return: 迁移版本创建结果
        """
        arguments: list[str] = ['-m', message]
        if autogenerate:
            arguments.append('--autogenerate')
        return self.alembic_command_support.run_alembic_command(
            'revision',
            *arguments,
            success_message='数据库迁移版本文件创建完成',
            failure_message='数据库迁移版本文件创建失败',
            dry_run=dry_run,
        )

    def get_alembic_heads(self) -> dict[str, Any]:
        """
        读取当前代码仓库中的 Alembic heads 信息。

        :return: Alembic heads 结果
        """
        try:
            script_directory = self.revision_support.build_alembic_script_directory()
            items = [
                self.revision_support.serialize_revision(revision)
                for revision in script_directory.get_revisions('heads')
            ]
            return {
                'ok': True,
                'message': '已读取 Alembic heads',
                'count': len(items),
                'items': items,
            }
        except Exception as exc:
            return {'ok': False, 'message': '读取 Alembic heads 失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

    def get_alembic_history(self, *, limit: int = 20) -> dict[str, Any]:
        """
        读取当前代码仓库中的 Alembic 历史版本信息。

        :param limit: 返回的最大历史记录数量
        :return: Alembic 历史版本结果
        """
        try:
            script_directory = self.revision_support.build_alembic_script_directory()
            history_items = [
                self.revision_support.serialize_revision(revision) for revision in script_directory.walk_revisions()
            ]
            limited_items = history_items[:limit]
            return {
                'ok': True,
                'message': '已读取 Alembic 历史版本',
                'count': len(limited_items),
                'totalCount': len(history_items),
                'limit': limit,
                'items': limited_items,
            }
        except Exception as exc:
            return {'ok': False, 'message': '读取 Alembic 历史版本失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}


DATABASE_RUNTIME = DatabaseRuntimeService()
