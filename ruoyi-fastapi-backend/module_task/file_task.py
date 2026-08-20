from config.database import DataSourceRegistry
from module_admin.service.file_business_service import FileRetentionNoticeService
from module_admin.service.file_service import FileLifecycleService, FileReconcileService
from utils.log_util import logger

MAX_TASK_BATCHES = 100


async def scan_retention_reminders(remind_days: int = 7, batch_size: int = 500) -> None:
    """
    扫描文件保留期限并生成提醒

    :param remind_days: 提前提醒天数
    :param batch_size: 单类提醒单批处理数量
    :return: None
    """
    expiring_count = 0
    expired_count = 0
    async with DataSourceRegistry.session() as query_db:
        for _ in range(MAX_TASK_BATCHES):
            scan_result = await FileRetentionNoticeService.scan_file_retention_notices_services(
                query_db,
                remind_days=remind_days,
                batch_size=batch_size,
            )
            expiring_count += scan_result.expiring_count
            expired_count += scan_result.expired_count
            if scan_result.expiring_count < batch_size and scan_result.expired_count < batch_size:
                break
        else:
            logger.warning('文件保留期限提醒扫描达到最大批次数，请检查待处理文件数量')
    logger.info(f'文件保留期限提醒扫描完成，即将到期{expiring_count}个，已到期{expired_count}个')


async def purge_recycle_bin(retention_days: int = 30, batch_size: int = 100) -> None:
    """
    永久清理超过保留期限的回收站文件

    :param retention_days: 回收站保留天数
    :param batch_size: 单批处理数量
    :return: None
    """
    purge_count = 0
    async with DataSourceRegistry.session() as query_db:
        for _ in range(MAX_TASK_BATCHES):
            current_count = await FileLifecycleService.purge_recycle_bin_services(
                query_db,
                retention_days=retention_days,
                batch_size=batch_size,
            )
            purge_count += current_count
            if current_count < batch_size:
                break
        else:
            logger.warning('回收站永久清理达到最大批次数，请检查待处理文件数量')
    logger.info(f'回收站永久清理完成，共清理{purge_count}个文件')


async def reconcile_file_storage(check_hash: bool = False) -> None:
    """
    执行数据库和本地文件系统双向对账

    :param check_hash: 是否校验文件SHA-256
    :return: None
    """
    await FileReconcileService.run_scheduled_reconcile_services(check_hash)
