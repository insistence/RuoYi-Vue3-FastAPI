from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.runtime.job import JOB_RUNTIME, JobRuntimeService
from cli.runtime.ops import OPERATIONS_RUNTIME, OperationsRuntimeService

from .presenter import JobCommandPresenter


class JobCommandController:
    """
    定时任务命令控制器。

    该控制器负责组织 `job` 命令组的上下文准备、runtime 调用、
    payload 注入，以及基于输出格式选择 presenter 或直接返回 JSON。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: 定时任务命令文本渲染器
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: JobCommandPresenter | None = None,
        operations_runtime: OperationsRuntimeService | None = None,
        job_runtime: JobRuntimeService | None = None,
    ) -> None:
        """
        初始化定时任务命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 定时任务命令文本渲染器
        :param operations_runtime: 运维运行时服务
        :param job_runtime: 定时任务运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or JobCommandPresenter()
        self.operations_runtime = operations_runtime or OPERATIONS_RUNTIME
        self.job_runtime = job_runtime or JOB_RUNTIME

    def list(
        self,
        env: str,
        output: str,
        *,
        job_name: str,
        job_group: str,
        status: str | None,
        paged: bool,
        page_num: int,
        page_size: int,
    ) -> None:
        """
        查看定时任务列表。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param job_name: 任务名称过滤条件
        :param job_group: 任务组过滤条件
        :param status: 状态过滤条件
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(
            self.job_runtime.list_jobs(
                job_name=job_name,
                job_group=job_group,
                status=status,
                paged=paged,
                page_num=page_num,
                page_size=page_size,
            )
        )
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_job_list_text,
            text_condition=lambda result_data: bool(result_data.get('ok', False)),
        )

    def run_once(self, job_id: int, env: str, output: str, allow_prod: bool, yes: bool) -> None:
        """
        执行一次定时任务。

        :param job_id: 任务ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self.context_factory.build_dangerous(env, output, allow_prod, yes, False, command_name='job run-once')
        self.execution_service.complete_payload(
            ctx, self.execution_service.run_async(self.job_runtime.run_job_once(job_id))
        )

    def detail(self, job_id: int, env: str, output: str) -> None:
        """
        查看单个定时任务详情。

        :param job_id: 任务ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.job_runtime.get_job_detail(job_id))
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_job_detail_text,
            text_condition=lambda result_data: 'error' not in result_data,
        )

    def logs(
        self,
        env: str,
        output: str,
        *,
        job_name: str,
        job_group: str,
        status: str | None,
        begin_date: str,
        end_date: str,
        paged: bool,
        page_num: int,
        page_size: int,
    ) -> None:
        """
        查看定时任务执行日志列表。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param job_name: 任务名称过滤条件
        :param job_group: 任务组过滤条件
        :param status: 执行状态过滤条件
        :param begin_date: 查询开始日期
        :param end_date: 查询结束日期
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(
            self.job_runtime.list_job_logs(
                job_name=job_name,
                job_group=job_group,
                status=status,
                begin_date=begin_date,
                end_date=end_date,
                paged=paged,
                page_num=page_num,
                page_size=page_size,
            )
        )
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_job_logs_text,
            text_condition=lambda result_data: bool(result_data.get('ok', False)),
        )

    def pause(self, job_id: int, env: str, output: str, allow_prod: bool, yes: bool) -> None:
        """
        暂停定时任务。

        :param job_id: 任务ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self.context_factory.build_dangerous(env, output, allow_prod, yes, False, command_name='job pause')
        self.execution_service.complete_payload(
            ctx, self.execution_service.run_async(self.job_runtime.pause_job(job_id))
        )

    def resume(self, job_id: int, env: str, output: str, allow_prod: bool, yes: bool) -> None:
        """
        恢复定时任务。

        :param job_id: 任务ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self.context_factory.build_dangerous(env, output, allow_prod, yes, False, command_name='job resume')
        self.execution_service.complete_payload(
            ctx, self.execution_service.run_async(self.job_runtime.resume_job(job_id))
        )

    def sync(self, env: str, output: str, allow_prod: bool, yes: bool) -> None:
        """
        同步调度任务配置。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self.context_factory.build_dangerous(env, output, allow_prod, yes, False, command_name='job sync')
        self.execution_service.complete_payload(
            ctx,
            self.execution_service.run_async(self.operations_runtime.sync_jobs()),
        )
