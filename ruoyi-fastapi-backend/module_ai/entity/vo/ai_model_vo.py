from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size


class AiModelModel(BaseModel):
    """
    AI模型表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    model_id: int | None = Field(default=None, description='模型主键')
    model_code: str | None = Field(default=None, description='模型编码')
    model_name: str | None = Field(default=None, description='模型名称')
    provider: str | None = Field(default=None, description='提供商')
    model_sort: int | None = Field(default=None, description='显示顺序')
    api_key: str | None = Field(default=None, description='API Key')
    base_url: str | None = Field(default=None, description='Base URL')
    max_tokens: int | None = Field(default=None, description='最大输出token')
    temperature: float | None = Field(default=None, description='默认温度')
    support_reasoning: Literal['Y', 'N'] | None = Field(default=None, description='是否支持推理(深度思考)')
    support_images: Literal['Y', 'N'] | None = Field(default=None, description='是否支持图片')
    model_type: str | None = Field(default=None, description='模型类型')
    status: Literal['0', '1'] | None = Field(default=None, description='模型状态')
    user_id: int | None = Field(default=None, description='用户ID')
    dept_id: int | None = Field(default=None, description='部门ID')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')
    remark: str | None = Field(default=None, description='备注')

    @NotBlank(field_name='model_code', message='模型编码不能为空')
    @Size(field_name='model_code', min_length=0, max_length=100, message='模型编码长度不能超过100个字符')
    def get_model_code(self) -> str | None:
        return self.model_code

    @NotBlank(field_name='base_url', message='Base URL不能为空')
    @Size(field_name='base_url', min_length=0, max_length=255, message='Base URL长度不能超过255个字符')
    def get_base_url(self) -> str | None:
        return self.base_url


class AiModelPageQueryModel(AiModelModel):
    """
    AI模型管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteAiModelModel(BaseModel):
    """
    删除AI模型模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    model_ids: str = Field(description='需要删除的模型主键')
