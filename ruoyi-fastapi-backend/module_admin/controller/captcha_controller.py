import uuid
from datetime import timedelta

from fastapi import Request, Response

from common.enums import RedisInitKeyConfig
from common.router import APIRouterPro
from common.vo import DynamicResponseModel
from module_admin.entity.vo.login_vo import CaptchaCode
from module_admin.service.captcha_service import CaptchaService
from utils.log_util import logger
from utils.response_util import ResponseUtil

captcha_controller = APIRouterPro(order_num=2, tags=['验证码模块'])


@captcha_controller.get(
    '/captchaImage',
    summary='获取图片验证码接口',
    description='用于获取图片验证码',
    response_model=DynamicResponseModel[CaptchaCode],
)
async def get_captcha_image(request: Request) -> Response:
    captcha_enabled = (
        await request.app.state.redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.account.captchaEnabled') == 'true'
    )
    register_enabled = (
        await request.app.state.redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.account.registerUser') == 'true'
    )
    session_id = str(uuid.uuid4())
    captcha_result = await CaptchaService.create_captcha_image_service()
    image = captcha_result[0]
    computed_result = captcha_result[1]
    await request.app.state.redis.set(
        f'{RedisInitKeyConfig.CAPTCHA_CODES.key}:{session_id}', computed_result, ex=timedelta(minutes=2)
    )
    logger.info(f'编号为{session_id}的会话获取图片验证码成功')

    return ResponseUtil.success(
        model_content=CaptchaCode(
            captchaEnabled=captcha_enabled, registerEnabled=register_enabled, img=image, uuid=session_id
        )
    )
