from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class AiChatRequestModel(BaseModel):
    """
    AI对话请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    session_id: str | None = Field(default=None, description='会话ID')
    model_id: int = Field(description='模型ID')
    message: str = Field(description='用户消息')
    is_reasoning: bool | None = Field(default=None, description='本次是否开启深度思考')
    images: list[str] | None = Field(default=None, description='图片URL列表')


class AiChatConfigModel(BaseModel):
    """
    AI对话配置模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    chat_config_id: int | None = Field(default=None, description='配置主键')
    user_id: int | None = Field(default=None, description='用户ID')
    temperature: float | None = Field(default=None, description='默认温度')
    add_history_to_context: Literal['0', '1'] | None = Field(default=None, description='是否添加历史记录')
    num_history_runs: int | None = Field(default=3, description='历史记录条数')
    system_prompt: str | None = Field(default=None, description='系统提示词')
    metrics_default_visible: Literal['0', '1'] | None = Field(default=None, description='默认显示指标')
    vision_enabled: Literal['0', '1'] | None = Field(default=None, description='是否开启视觉')
    image_max_size_mb: int | None = Field(default=None, description='图片最大大小(MB)')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_time: datetime | None = Field(default=None, description='更新时间')


class AiChatSessionBaseModel(BaseModel):
    """
    AI对话会话基础模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    session_id: str = Field(description='会话ID')
    session_title: str | None = Field(default=None, description='会话标题')
    session_type: str | None = Field(default=None, description='会话类型')
    user_id: str | None = Field(default=None, description='用户ID')
    created_at: datetime | None = Field(default=None, description='创建时间')
    updated_at: datetime | None = Field(default=None, description='更新时间')


class ModelInfoModel(BaseModel):
    """
    对话会话数据模型-模型信息模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    id: str | None = Field(default=None, description='模型ID')
    name: str | None = Field(default=None, description='模型名称')
    provider: str | None = Field(default=None, description='模型提供者')
    temperature: float | None = Field(default=None, description='模型温度')


class AgentDataModel(BaseModel):
    """
    对话会话数据模型-智能体数据模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    model: ModelInfoModel | None = Field(default=None, description='模型信息')
    agent_id: str | None = Field(default=None, description='智能体ID')


class SessionMetricsModel(BaseModel):
    """
    对话会话数据模型-会话指标模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    cost: float | None = Field(default=None, description='成本（元）')
    timer: float | None = Field(default=None, description='运行时长（秒）')
    duration: float | None = Field(default=None, description='运行时长（秒）')
    input_tokens: int | None = Field(default=None, description='输入Token数量')
    total_tokens: int | None = Field(default=None, description='总Token数量')
    output_tokens: int | None = Field(default=None, description='输出Token数量')
    provider_metrics: dict | None = Field(default=None, description='提供者指标')
    reasoning_tokens: int | None = Field(default=None, description='推理Token数量')
    cache_read_tokens: int | None = Field(default=None, description='缓存读取Token数量')
    additional_metrics: dict | None = Field(default=None, description='其他指标')
    audio_input_tokens: int | None = Field(default=None, description='音频输入Token数量')
    audio_total_tokens: int | None = Field(default=None, description='音频总Token数量')
    cache_write_tokens: int | None = Field(default=None, description='缓存写入Token数量')
    audio_output_tokens: int | None = Field(default=None, description='音频输出Token数量')
    time_to_first_token: float | None = Field(default=None, description='到第一个Token的时间（秒）')


class SessionDataModel(BaseModel):
    """
    对话会话数据模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    session_state: dict | None = Field(default=None, description='会话状态')
    session_metrics: SessionMetricsModel | None = Field(default=None, description='会话指标')


class MessageMetrics(BaseModel):
    """
    对话消息模型-消息指标模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    input_tokens: int | None = Field(default=None, description='输入Token数量')
    total_tokens: int | None = Field(default=None, description='总Token数量')
    output_tokens: int | None = Field(default=None, description='输出Token数量')
    reasoning_tokens: int | None = Field(default=None, description='推理Token数量')
    duration: float | None = Field(default=None, description='运行时长（秒）')
    time_to_first_token: float | None = Field(default=None, description='到第一个Token的时间（秒）')


class ChatMessageModel(BaseModel):
    """
    对话消息模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    id: str | None = Field(default=None, description='消息ID')
    role: str | None = Field(default=None, description='角色')
    content: str | None = Field(default=None, description='内容')
    images: list[str] | None = Field(default=None, description='图片列表')
    metrics: MessageMetrics | None = Field(default=None, description='Token使用统计')
    created_at: datetime | None = Field(default=None, description='创建时间')
    from_history: bool | None = Field(default=None, description='是否来自历史记录')
    reasoning_content: str | None = Field(default=None, description='推理/思考内容')
    stop_after_tool_call: bool | None = Field(default=None, description='是否在工具调用后停止')


class AiChatSessionModel(AiChatSessionBaseModel):
    """
    AI对话会话模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    agent_id: str | None = Field(default=None, description='智能体ID')
    session_data: SessionDataModel | None = Field(default=None, description='会话数据')
    agent_data: AgentDataModel | None = Field(default=None, description='智能体数据')
    messages: list[ChatMessageModel] | None = Field(default=None, description='消息列表')
