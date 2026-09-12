from typing import Any

from apscheduler.triggers.date import DateTrigger


class TaskDateTrigger(DateTrigger):
    """
    携带任务原始时区的单次触发器
    """

    def __init__(
        self,
        task_timezone: str,
        *,
        task_job_id: int | None = None,
        task_job_group: str = 'default',
        execution_id: str | None = None,
        dispatch_token: str | None = None,
        **kwargs,
    ) -> None:
        """
        初始化保留任务时区的单次触发器

        :param task_timezone: 任务原始IANA时区名称
        :param task_job_id: 关联的逻辑任务ID
        :param task_job_group: 业务分组快照
        :param execution_id: 执行ID
        :param dispatch_token: 本次派发的领取凭据
        :param kwargs: 传递给DateTrigger的执行时刻及其他配置
        :return: None
        """
        super().__init__(**kwargs)
        self.task_timezone = task_timezone
        self.task_job_id = task_job_id
        self.task_job_group = task_job_group
        self.execution_id = execution_id
        self.dispatch_token = dispatch_token

    def __getstate__(self) -> dict[str, Any]:
        """
        序列化单次触发器及任务时区

        :return: 可供持久化任务仓库存储的触发器状态
        """
        return {
            **super().__getstate__(),
            'task_timezone': self.task_timezone,
            'task_job_id': self.task_job_id,
            'task_job_group': self.task_job_group,
            'execution_id': self.execution_id,
            'dispatch_token': self.dispatch_token,
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        """
        从持久化状态恢复触发器和任务时区

        :param state: 已序列化的触发器状态
        :return: None
        """
        super().__setstate__(state)
        self.task_timezone = state['task_timezone']
        self.task_job_id = state.get('task_job_id')
        self.task_job_group = state.get('task_job_group', 'default')
        self.execution_id = state.get('execution_id')
        self.dispatch_token = state.get('dispatch_token')


def trigger_timezone(trigger: Any) -> str | None:
    """
    读取触发器携带的任务时区

    :param trigger: Cron、单次或组合触发器
    :return: 任务时区名称，未携带时区时返回None
    """
    if hasattr(trigger, 'task_timezone'):
        return trigger.task_timezone
    if hasattr(trigger, 'timezone'):
        return str(trigger.timezone)
    for child in getattr(trigger, 'triggers', ()):
        if value := trigger_timezone(child):
            return value
    return None
