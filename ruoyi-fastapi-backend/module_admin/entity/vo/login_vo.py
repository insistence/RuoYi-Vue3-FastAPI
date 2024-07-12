import re
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from typing import List, Optional, Union
from exceptions.exception import ModelValidatorException
from module_admin.entity.vo.menu_vo import MenuModel


class UserLogin(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    user_name: str = Field(description='用户名称')
    password: str = Field(description='用户密码')
    code: Optional[str] = Field(default=None, description='验证码')
    uuid: Optional[str] = Field(default=None, description='会话编号')
    login_info: Optional[dict] = Field(default=None, description='登录信息，前端无需传递')
    captcha_enabled: Optional[bool] = Field(default=None, description='是否启用验证码，前端无需传递')


class UserRegister(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    username: str = Field(description='用户名称')
    password: str = Field(description='用户密码')
    confirm_password: str = Field(description='用户二次确认密码')
    code: Optional[str] = Field(default=None, description='验证码')
    uuid: Optional[str] = Field(default=None, description='会话编号')

    @model_validator(mode='after')
    def check_password(self) -> 'UserRegister':
        pattern = r"""^[^<>"'|\\]+$"""
        if self.password is None or re.match(pattern, self.password):
            return self
        else:
            raise ModelValidatorException(message='密码不能包含非法字符：< > " \' \\ |')


class Token(BaseModel):
    access_token: str = Field(description='token信息')
    token_type: str = Field(description='token类型')


class CaptchaCode(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    captcha_enabled: bool = Field(description='是否启用验证码')
    register_enabled: bool = Field(description='是否启用注册')
    img: str = Field(description='验证码图片')
    uuid: str = Field(description='会话编号')


class SmsCode(BaseModel):
    is_success: Optional[bool] = Field(default=None, description='操作是否成功')
    sms_code: str = Field(description='短信验证码')
    session_id: str = Field(description='会话编号')
    message: Optional[str] = Field(default=None, description='响应信息')


class MenuTreeModel(MenuModel):
    children: Optional[Union[List['MenuTreeModel'], None]] = Field(default=None, description='子菜单')


class MetaModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    title: Optional[str] = Field(default=None, description='设置路由在侧边栏和面包屑中展示的名字')
    icon: Optional[str] = Field(default=None, description='设置路由的图标')
    no_cache: Optional[bool] = Field(default=None, description='设置为true，则不会被 <keep-alive>缓存')
    link: Optional[str] = Field(default=None, description='内链地址（http(s)://开头）')


class RouterModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    name: Optional[str] = Field(default=None, description='路由名称')
    path: Optional[str] = Field(default=None, description='路由地址')
    hidden: Optional[bool] = Field(default=None, description='是否隐藏路由，当设置 true 的时候该路由不会再侧边栏出现')
    redirect: Optional[str] = Field(
        default=None, description='重定向地址，当设置 noRedirect 的时候该路由在面包屑导航中不可被点击'
    )
    component: Optional[str] = Field(default=None, description='组件地址')
    query: Optional[str] = Field(default=None, description='路由参数：如 {"id": 1, "name": "ry"}')
    always_show: Optional[bool] = Field(
        default=None, description='当你一个路由下面的children声明的路由大于1个时，自动会变成嵌套的模式--如组件页面'
    )
    meta: Optional[MetaModel] = Field(default=None, description='其他元素')
    children: Optional[Union[List['RouterModel'], None]] = Field(default=None, description='子路由')
