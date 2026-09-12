from utils.time_util import TimezoneUtil


def job(*args, **kwargs) -> None:
    """
    定时任务执行同步函数示例
    """
    print(args)
    print(kwargs)
    print(f'{TimezoneUtil.format_rfc3339(TimezoneUtil.utc_now())}同步函数执行了')


async def async_job(*args, **kwargs) -> None:
    """
    定时任务执行异步函数示例
    """
    print(args)
    print(kwargs)
    print(f'{TimezoneUtil.format_rfc3339(TimezoneUtil.utc_now())}异步函数执行了')
