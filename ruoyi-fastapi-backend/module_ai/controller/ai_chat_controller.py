from typing import Annotated

from fastapi import Body, Path, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, ResponseBaseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_ai.entity.vo.ai_chat_vo import (
    AiChatConfigModel,
    AiChatRequestModel,
    AiChatSessionBaseModel,
    AiChatSessionModel,
)
from module_ai.service.ai_chat_service import AiChatService
from utils.log_util import logger
from utils.response_util import ResponseUtil

ai_chat_controller = APIRouterPro(
    prefix='/ai/chat', order_num=19, tags=['AI管理-AI对话'], dependencies=[PreAuthDependency()]
)


@ai_chat_controller.post(
    '/send',
    summary='发送对话消息',
    description='流式返回对话结果',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回对话结果',
            'content': {
                'text/event-stream': {},
            },
        }
    },
)
async def send_chat_message(
    request: Request,
    chat_req: AiChatRequestModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> StreamingResponse:
    user_id = current_user.user.user_id if current_user and current_user.user else 1
    chat_stream = AiChatService.chat_services(query_db, chat_req, user_id)
    logger.info(f'用户{user_id}发送对话消息成功')

    return StreamingResponse(content=chat_stream, media_type='text/event-stream')


@ai_chat_controller.get(
    '/config',
    summary='获取用户对话配置',
    description='获取当前用户的AI对话配置',
    response_model=DataResponseModel[AiChatConfigModel],
)
async def get_user_chat_config(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    user_id = current_user.user.user_id
    ai_chat_config_detail_result = await AiChatService.ai_chat_config_detail_services(query_db, user_id)
    logger.info(f'获取user_id为{user_id}的对话配置成功')

    return ResponseUtil.success(data=ai_chat_config_detail_result)


@ai_chat_controller.put(
    '/config',
    summary='保存用户对话配置',
    description='保存当前用户的AI对话配置',
    response_model=DataResponseModel[AiChatConfigModel],
)
@Log(title='AI对话配置管理', business_type=BusinessType.INSERT)
async def save_user_chat_config(
    request: Request,
    ai_chat_config: AiChatConfigModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    user_id = current_user.user.user_id if current_user and current_user.user else 1
    save_ai_chat_config_result = await AiChatService.save_ai_chat_config_services(query_db, user_id, ai_chat_config)
    logger.info(save_ai_chat_config_result.message)

    return ResponseUtil.success(msg=save_ai_chat_config_result.message)


@ai_chat_controller.get(
    '/session/list',
    summary='获取会话列表',
    description='获取用户的会话列表',
    response_model=DataResponseModel[list[AiChatSessionBaseModel]],
)
async def get_chat_session_list(
    request: Request,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await AiChatService.get_chat_session_list_services(current_user.user.user_id)
    logger.info('获取成功')

    return ResponseUtil.success(data=result)


@ai_chat_controller.delete(
    '/session/{session_id}',
    summary='删除会话',
    description='删除指定会话',
    response_model=ResponseBaseModel,
)
@Log(title='AI对话会话管理', business_type=BusinessType.DELETE)
async def delete_chat_session(
    request: Request,
    session_id: Annotated[str, Path(description='会话ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_chat_session_result = await AiChatService.delete_chat_session_services(session_id)
    logger.info(delete_chat_session_result.message)

    return ResponseUtil.success(msg=delete_chat_session_result.message)


@ai_chat_controller.get(
    '/session/{session_id}',
    summary='获取会话消息详情',
    description='获取指定会话的消息详情',
    response_model=DataResponseModel[AiChatSessionModel],
)
async def get_chat_session_detail(
    request: Request,
    session_id: Annotated[str, Path(description='会话ID')],
) -> Response:
    chat_session_detail_result = await AiChatService.get_chat_session_detail_services(session_id)
    logger.info(f'获取session_id为{session_id}的信息成功')

    return ResponseUtil.success(data=chat_session_detail_result)


@ai_chat_controller.post(
    '/cancel',
    summary='取消对话',
    description='取消正在进行的对话',
    response_model=ResponseBaseModel,
)
async def cancel_chat_run(
    request: Request,
    run_id: Annotated[str, Body(embed=True, description='运行ID', alias='runId')],
) -> Response:
    cancel_result = await AiChatService.cancel_run_services(run_id)
    logger.info(cancel_result.message)

    return ResponseUtil.success(msg=cancel_result.message)
