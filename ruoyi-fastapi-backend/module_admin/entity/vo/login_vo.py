from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Optional


class UserLogin(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    user_name: str
    password: str
    code: Optional[str] = None
    uuid: Optional[str] = None
    login_info: Optional[dict] = None
    captcha_enabled: Optional[bool] = None


class UserRegister(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    username: str
    password: str
    confirm_password: str
    code: Optional[str] = None
    uuid: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class CaptchaCode(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    captcha_enabled: bool
    register_enabled: bool
    img: str
    uuid: str


class SmsCode(BaseModel):
    is_success: Optional[bool] = None
    sms_code: str
    session_id: str
    message: Optional[str] = None