import asyncio
import hashlib
import json
import os
import uuid
from typing import Any

from fastapi import Request
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import CrudResponseModel, PageModel
from config.database import AsyncSessionLocal
from config.env import LogConfig
from exceptions.exception import ServiceException
from middlewares.trace_middleware.ctx import TraceCtx
from module_admin.dao.log_dao import LoginLogDao, OperationLogDao
from module_admin.entity.vo.log_vo import (
    DeleteLoginLogModel,
    DeleteOperLogModel,
    LogininforModel,
    LoginLogPageQueryModel,
    OperLogModel,
    OperLogPageQueryModel,
    UnlockUser,
)
from module_admin.service.dict_service import DictDataService
from utils.excel_util import ExcelUtil
from utils.log_util import logger


class OperationLogService:
    """
    操作日志管理模块服务层
    """

    @classmethod
    async def get_operation_log_list_services(
        cls, query_db: AsyncSession, query_object: OperLogPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取操作日志列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 操作日志列表信息对象
        """
        operation_log_list_result = await OperationLogDao.get_operation_log_list(query_db, query_object, is_page)

        return operation_log_list_result

    @classmethod
    async def add_operation_log_services(cls, query_db: AsyncSession, page_object: OperLogModel) -> CrudResponseModel:
        """
        新增操作日志service

        :param query_db: orm对象
        :param page_object: 新增操作日志对象
        :return: 新增操作日志校验结果
        """
        try:
            await OperationLogDao.add_operation_log_dao(query_db, page_object)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def delete_operation_log_services(
        cls, query_db: AsyncSession, page_object: DeleteOperLogModel
    ) -> CrudResponseModel:
        """
        删除操作日志信息service

        :param query_db: orm对象
        :param page_object: 删除操作日志对象
        :return: 删除操作日志校验结果
        """
        if page_object.oper_ids:
            oper_id_list = page_object.oper_ids.split(',')
            try:
                for oper_id in oper_id_list:
                    await OperationLogDao.delete_operation_log_dao(query_db, OperLogModel(operId=oper_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入操作日志id为空')

    @classmethod
    async def clear_operation_log_services(cls, query_db: AsyncSession) -> CrudResponseModel:
        """
        清除操作日志信息service

        :param query_db: orm对象
        :return: 清除操作日志校验结果
        """
        try:
            await OperationLogDao.clear_operation_log_dao(query_db)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='清除成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def export_operation_log_list_services(cls, request: Request, operation_log_list: list) -> bytes:
        """
        导出操作日志信息service

        :param request: Request对象
        :param operation_log_list: 操作日志信息列表
        :return: 操作日志信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'operId': '日志编号',
            'title': '系统模块',
            'businessType': '操作类型',
            'method': '方法名称',
            'requestMethod': '请求方式',
            'operName': '操作人员',
            'deptName': '部门名称',
            'operUrl': '请求URL',
            'operIp': '操作地址',
            'operLocation': '操作地点',
            'operParam': '请求参数',
            'jsonResult': '返回参数',
            'status': '操作状态',
            'error_msg': '错误消息',
            'operTime': '操作日期',
            'costTime': '消耗时间（毫秒）',
        }

        operation_type_list = await DictDataService.query_dict_data_list_from_cache_services(
            request.app.state.redis, dict_type='sys_oper_type'
        )
        operation_type_option = [
            {'label': item.get('dictLabel'), 'value': item.get('dictValue')} for item in operation_type_list
        ]
        operation_type_option_dict = {item.get('value'): item for item in operation_type_option}

        for item in operation_log_list:
            if item.get('status') == 0:
                item['status'] = '成功'
            else:
                item['status'] = '失败'
            if str(item.get('businessType')) in operation_type_option_dict:
                item['businessType'] = operation_type_option_dict.get(str(item.get('businessType'))).get('label')
        binary_data = ExcelUtil.export_list2excel(operation_log_list, mapping_dict)

        return binary_data


class LoginLogService:
    """
    登录日志管理模块服务层
    """

    @classmethod
    async def get_login_log_list_services(
        cls, query_db: AsyncSession, query_object: LoginLogPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取登录日志列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 登录日志列表信息对象
        """
        operation_log_list_result = await LoginLogDao.get_login_log_list(query_db, query_object, is_page)

        return operation_log_list_result

    @classmethod
    async def add_login_log_services(cls, query_db: AsyncSession, page_object: LogininforModel) -> CrudResponseModel:
        """
        新增登录日志service

        :param query_db: orm对象
        :param page_object: 新增登录日志对象
        :return: 新增登录日志校验结果
        """
        try:
            await LoginLogDao.add_login_log_dao(query_db, page_object)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def delete_login_log_services(
        cls, query_db: AsyncSession, page_object: DeleteLoginLogModel
    ) -> CrudResponseModel:
        """
        删除操作日志信息service

        :param query_db: orm对象
        :param page_object: 删除操作日志对象
        :return: 删除操作日志校验结果
        """
        if page_object.info_ids:
            info_id_list = page_object.info_ids.split(',')
            try:
                for info_id in info_id_list:
                    await LoginLogDao.delete_login_log_dao(query_db, LogininforModel(infoId=info_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入登录日志id为空')

    @classmethod
    async def clear_login_log_services(cls, query_db: AsyncSession) -> CrudResponseModel:
        """
        清除操作日志信息service

        :param query_db: orm对象
        :return: 清除操作日志校验结果
        """
        try:
            await LoginLogDao.clear_login_log_dao(query_db)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='清除成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def unlock_user_services(cls, request: Request, unlock_user: UnlockUser) -> CrudResponseModel:
        locked_user = await request.app.state.redis.get(f'account_lock:{unlock_user.user_name}')
        if locked_user:
            await request.app.state.redis.delete(f'account_lock:{unlock_user.user_name}')
            return CrudResponseModel(is_success=True, message='解锁成功')
        raise ServiceException(message='该用户未锁定')

    @staticmethod
    async def export_login_log_list_services(login_log_list: list) -> bytes:
        """
        导出登录日志信息service

        :param login_log_list: 登录日志信息列表
        :return: 登录日志信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'infoId': '访问编号',
            'userName': '用户名称',
            'ipaddr': '登录地址',
            'loginLocation': '登录地点',
            'browser': '浏览器',
            'os': '操作系统',
            'status': '登录状态',
            'msg': '操作信息',
            'loginTime': '登录日期',
        }

        for item in login_log_list:
            if item.get('status') == '0':
                item['status'] = '成功'
            else:
                item['status'] = '失败'
        binary_data = ExcelUtil.export_list2excel(login_log_list, mapping_dict)

        return binary_data


class LogQueueService:
    """
    日志队列服务
    """

    @classmethod
    def _build_event_id(cls, request_id: str, log_type: str, source: str) -> str:
        """
        生成日志事件唯一标识

        :param request_id: 请求唯一标识
        :param log_type: 日志类型
        :param source: 日志来源
        :return: 事件唯一标识
        """
        if not request_id:
            return uuid.uuid4().hex
        base = f'{request_id}:{log_type}:{source}'
        return hashlib.md5(base.encode('utf-8')).hexdigest()

    @classmethod
    async def _xadd_event(cls, redis: aioredis.Redis, event_type: str, payload: dict, source: str) -> None:
        """
        写入日志事件到Redis Streams

        :param redis: Redis连接对象
        :param event_type: 事件类型
        :param payload: 事件负载
        :param source: 日志来源
        :return: None
        """
        request_id = TraceCtx.get_request_id()
        trace_id = TraceCtx.get_trace_id()
        span_id = TraceCtx.get_span_id()
        event_id = cls._build_event_id(request_id, event_type, source)
        await redis.xadd(
            LogConfig.log_stream_key,
            {
                'event_id': event_id,
                'event_type': event_type,
                'request_id': request_id,
                'trace_id': trace_id,
                'span_id': span_id,
                'payload': json.dumps(payload, ensure_ascii=False, default=str),
            },
            maxlen=LogConfig.log_stream_maxlen,
            approximate=True,
        )

    @classmethod
    async def enqueue_login_log(cls, request: Request, login_log: LogininforModel, source: str) -> None:
        """
        登录日志入队

        :param request: Request对象
        :param login_log: 登录日志模型
        :param source: 日志来源
        :return: None
        """
        payload = login_log.model_dump(by_alias=True, exclude_none=True)
        await cls._xadd_event(request.app.state.redis, 'login', payload, source)

    @classmethod
    async def enqueue_operation_log(cls, request: Request, operation_log: OperLogModel, source: str) -> None:
        """
        操作日志入队

        :param request: Request对象
        :param operation_log: 操作日志模型
        :param source: 日志来源
        :return: None
        """
        payload = operation_log.model_dump(by_alias=True, exclude_none=True)
        await cls._xadd_event(request.app.state.redis, 'operation', payload, source)


class LogAggregatorService:
    """
    日志聚合消费服务
    """

    @classmethod
    async def _ensure_group(cls, redis: aioredis.Redis) -> None:
        """
        初始化消费组

        :param redis: Redis连接对象
        :return: None
        """
        try:
            await redis.xgroup_create(
                name=LogConfig.log_stream_key,
                groupname=LogConfig.log_stream_group,
                id='0-0',
                mkstream=True,
            )
        except Exception as exc:
            if 'BUSYGROUP' not in str(exc):
                raise

    @classmethod
    async def _acquire_dedup(cls, redis: aioredis.Redis, event_id: str) -> bool:
        """
        获取去重锁

        :param redis: Redis连接对象
        :param event_id: 事件唯一标识
        :return: 是否获取成功
        """
        if not event_id:
            return False
        key = f'{LogConfig.log_stream_dedup_prefix}:{event_id}'
        return await redis.set(key, '1', nx=True, ex=LogConfig.log_stream_dedup_ttl)

    @classmethod
    async def _release_dedup(cls, redis: aioredis.Redis, event_id: str) -> None:
        """
        释放去重锁

        :param redis: Redis连接对象
        :param event_id: 事件唯一标识
        :return: None
        """
        if not event_id:
            return
        await redis.delete(f'{LogConfig.log_stream_dedup_prefix}:{event_id}')

    @classmethod
    async def _claim_pending(cls, redis: aioredis.Redis, consumer_name: str) -> None:
        """
        认领并处理超时未确认的消息

        :param redis: Redis连接对象
        :param consumer_name: 消费者名称
        :return: None
        """
        if LogConfig.log_stream_claim_idle_ms <= 0:
            return
        start_id = '0-0'
        while True:
            result = await redis.xautoclaim(
                name=LogConfig.log_stream_key,
                groupname=LogConfig.log_stream_group,
                consumername=consumer_name,
                min_idle_time=LogConfig.log_stream_claim_idle_ms,
                start_id=start_id,
                count=LogConfig.log_stream_claim_batch_size,
            )
            if not result:
                return
            next_start_id, messages = result[0], result[1]
            if messages:
                await cls._process_messages(redis, LogConfig.log_stream_key, messages)
            if not messages or next_start_id == start_id:
                return
            start_id = next_start_id

    @classmethod
    async def consume_stream(cls, redis: aioredis.Redis) -> None:
        """
        消费日志队列

        :param redis: Redis连接对象
        :return: None
        """
        await cls._ensure_group(redis)
        consumer_name = f'{LogConfig.log_stream_consumer_prefix}-{os.getpid()}-{uuid.uuid4().hex[:6]}'
        last_claim_time = 0.0
        while True:
            try:
                now = asyncio.get_running_loop().time()
                if now - last_claim_time >= LogConfig.log_stream_claim_interval_ms / 1000:
                    await cls._claim_pending(redis, consumer_name)
                    last_claim_time = now
                result = await redis.xreadgroup(
                    groupname=LogConfig.log_stream_group,
                    consumername=consumer_name,
                    streams={LogConfig.log_stream_key: '>'},
                    count=LogConfig.log_stream_batch_size,
                    block=LogConfig.log_stream_block_ms,
                )
                if not result:
                    continue
                for stream_name, messages in result:
                    await cls._process_messages(redis, stream_name, messages)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f'日志聚合消费异常: {exc}')
                await asyncio.sleep(1)

    @classmethod
    async def _process_messages(cls, redis: aioredis.Redis, stream_name: str, messages: list[tuple[str, dict]]) -> None:
        """
        处理消息并落库

        :param redis: Redis连接对象
        :param stream_name: Stream名称
        :param messages: 消息列表
        :return: None
        """
        if not messages:
            return
        async with AsyncSessionLocal() as session:
            ack_ids: list[str] = []
            dedup_event_ids: list[str] = []
            try:
                for message_id, data in messages:
                    event_type = data.get('event_type')
                    event_id = data.get('event_id')
                    payload_raw = data.get('payload') or '{}'
                    if event_type not in {'login', 'operation'}:
                        ack_ids.append(message_id)
                        continue
                    acquired = await cls._acquire_dedup(redis, event_id)
                    if not acquired:
                        ack_ids.append(message_id)
                        continue
                    dedup_event_ids.append(event_id)
                    payload = json.loads(payload_raw)
                    if event_type == 'login':
                        await LoginLogDao.add_login_log_dao(session, LogininforModel(**payload))
                    elif event_type == 'operation':
                        await OperationLogDao.add_operation_log_dao(session, OperLogModel(**payload))
                    ack_ids.append(message_id)
                if ack_ids:
                    await session.commit()
                    await redis.xack(stream_name, LogConfig.log_stream_group, *ack_ids)
            except Exception:
                await session.rollback()
                for event_id in dedup_event_ids:
                    await cls._release_dedup(redis, event_id)
                raise
