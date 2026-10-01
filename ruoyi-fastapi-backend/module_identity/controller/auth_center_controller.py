from fastapi.responses import Response

from common.router import APIRouterPro
from common.vo import DataResponseModel
from config.env import OidcConfig
from utils.response_util import ResponseUtil

auth_center_controller = APIRouterPro(tags=['认证中心状态'], order_num=1)


@auth_center_controller.get(
    '/auth/status',
    summary='获取认证中心启用状态',
    description='供公共认证页面判断是否允许进入，仅返回功能开关',
    response_model=DataResponseModel[dict[str, bool]],
)
async def get_auth_center_status() -> Response:
    """匿名读取功能开关，不依赖交互凭据、数据库或签名密钥。"""
    return ResponseUtil.success(
        data={'enabled': OidcConfig.oidc_enabled},
        headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'},
    )
