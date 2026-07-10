import ipaddress
from importlib import import_module
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from config.database import async_engine
from config.env import DataBaseConfig

if TYPE_CHECKING:
    from agno.db.base import AsyncBaseDb
    from agno.models.base import Model

# 提供商名称 -> (模块路径, 类名) 的映射，延迟导入避免启动时加载所有AI SDK
_PROVIDER_REGISTRY: dict[str, tuple[str, str]] = {
    'AIMLAPI': ('agno.models.aimlapi', 'AIMLAPI'),
    'Anthropic': ('agno.models.anthropic', 'Claude'),
    'Cerebras': ('agno.models.cerebras', 'Cerebras'),
    'CerebrasOpenAI': ('agno.models.cerebras', 'CerebrasOpenAI'),
    'Cohere': ('agno.models.cohere', 'Cohere'),
    'CometAPI': ('agno.models.cometapi', 'CometAPI'),
    'DashScope': ('agno.models.dashscope', 'DashScope'),
    'DeepInfra': ('agno.models.deepinfra', 'DeepInfra'),
    'DeepSeek': ('agno.models.deepseek', 'DeepSeek'),
    'Fireworks': ('agno.models.fireworks', 'Fireworks'),
    'Google': ('agno.models.google', 'Gemini'),
    'Groq': ('agno.models.groq', 'Groq'),
    'HuggingFace': ('agno.models.huggingface', 'HuggingFace'),
    'LangDB': ('agno.models.langdb', 'LangDB'),
    'LiteLLM': ('agno.models.litellm', 'LiteLLM'),
    'LiteLLMOpenAI': ('agno.models.litellm', 'LiteLLMOpenAI'),
    'LlamaCpp': ('agno.models.llama_cpp', 'LlamaCpp'),
    'LMStudio': ('agno.models.lmstudio', 'LMStudio'),
    'Meta': ('agno.models.meta', 'Llama'),
    'Mistral': ('agno.models.mistral', 'MistralChat'),
    'N1N': ('agno.models.n1n', 'N1N'),
    'Nebius': ('agno.models.nebius', 'Nebius'),
    'Nexus': ('agno.models.nexus', 'Nexus'),
    'Nvidia': ('agno.models.nvidia', 'Nvidia'),
    'Ollama': ('agno.models.ollama', 'Ollama'),
    'OpenAI': ('agno.models.openai', 'OpenAIChat'),
    'OpenAIResponses': ('agno.models.openai.responses', 'OpenAIResponses'),
    'OpenRouter': ('agno.models.openrouter', 'OpenRouter'),
    'Perplexity': ('agno.models.perplexity', 'Perplexity'),
    'Portkey': ('agno.models.portkey', 'Portkey'),
    'Requesty': ('agno.models.requesty', 'Requesty'),
    'Sambanova': ('agno.models.sambanova', 'Sambanova'),
    'SiliconFlow': ('agno.models.siliconflow', 'Siliconflow'),
    'Together': ('agno.models.together', 'Together'),
    'Vercel': ('agno.models.vercel', 'V0'),
    'VLLM': ('agno.models.vllm', 'VLLM'),
    'xAI': ('agno.models.xai', 'xAI'),
}

# 存储引擎名称 -> (模块路径, 类名) 的映射
_STORAGE_ENGINE_REGISTRY: dict[str, tuple[str, str]] = {
    'mysql': ('agno.db.mysql', 'AsyncMySQLDb'),
    'postgresql': ('agno.db.postgres', 'AsyncPostgresDb'),
}

# 已加载的提供商类缓存，避免重复import_module
_provider_class_cache: dict[str, 'type[Model]'] = {}
_storage_class_cache: dict[str, 'type[AsyncBaseDb]'] = {}


class AiUtil:
    """
    AI工具类
    """

    @classmethod
    def _resolve_provider_class(cls, provider: str) -> 'type[Model] | None':
        """
        按需加载并缓存提供商模型类

        :param provider: 提供商名称
        :return: 模型类，未找到返回None
        """
        if provider in _provider_class_cache:
            return _provider_class_cache[provider]
        entry = _PROVIDER_REGISTRY.get(provider)
        if entry is None:
            return None
        module_path, class_name = entry
        provider_cls = getattr(import_module(module_path), class_name)
        _provider_class_cache[provider] = provider_cls
        return provider_cls

    @classmethod
    def _resolve_storage_class(cls, db_type: str) -> 'type[AsyncBaseDb]':
        """
        按需加载并缓存存储引擎类

        :param db_type: 数据库类型
        :return: 存储引擎类
        """
        if db_type in _storage_class_cache:
            return _storage_class_cache[db_type]
        entry = _STORAGE_ENGINE_REGISTRY.get(db_type)
        if entry is None:
            # 默认使用MySQL
            entry = _STORAGE_ENGINE_REGISTRY['mysql']
        module_path, class_name = entry
        storage_cls = getattr(import_module(module_path), class_name)
        _storage_class_cache[db_type] = storage_cls
        return storage_cls

    @classmethod
    def get_storage_engine(cls) -> 'AsyncBaseDb':
        """
        获取存储引擎实例

        :return: 存储引擎实例
        """
        storage_engine_class = cls._resolve_storage_class(DataBaseConfig.db_type)

        return storage_engine_class(
            db_engine=async_engine,
            db_schema=DataBaseConfig.db_database if DataBaseConfig.db_type == 'mysql' else 'public',
            session_table='ai_sessions',
            memory_table='ai_memories',
            metrics_table='ai_metrics',
            eval_table='ai_eval_runs',
            knowledge_table='ai_knowledge',
            culture_table='ai_culture',
            traces_table='ai_traces',
            spans_table='ai_spans',
            versions_table='ai_schema_versions',
            create_schema=False,
        )

    @classmethod
    def _validate_base_url(cls, base_url: str | None) -> str | None:
        """
        校验模型服务基础地址，阻断内网和元数据地址。

        :param base_url: 基础URL
        :return: 校验后的基础URL
        """
        if not base_url:
            return None

        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {'http', 'https'} or not parsed_url.hostname:
            raise ValueError('Base URL 只支持 http/https 且必须包含主机名')

        hostname = parsed_url.hostname.strip().lower()
        if hostname in {'localhost'} or hostname.endswith(('.localhost', '.local')):
            raise ValueError('Base URL 不允许指向本机或内网地址')

        try:
            ip_address = ipaddress.ip_address(hostname)
        except ValueError:
            return base_url

        if (
            ip_address.is_private
            or ip_address.is_loopback
            or ip_address.is_link_local
            or ip_address.is_multicast
            or ip_address.is_reserved
            or ip_address.is_unspecified
        ):
            raise ValueError('Base URL 不允许指向本机或内网地址')

        return base_url

    @classmethod
    def get_model_from_factory(
        cls,
        provider: str,
        model_code: str,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> 'Model':
        """
        从工厂获取模型实例

        :param provider: 提供商
        :param model_code: 模型编码
        :param model_name: 模型名称
        :param api_key: API密钥
        :param base_url: 基础URL
        :param temperature: 温度
        :param max_tokens: 最大令牌数
        :return: 模型实例
        """
        safe_base_url = cls._validate_base_url(base_url)
        params = {
            'id': model_code,
            'name': model_name,
            'base_url': safe_base_url,
            'api_key': api_key,
            'temperature': temperature,
            'max_tokens': max_tokens,
            **kwargs,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if provider == 'Ollama':
            params['host'] = safe_base_url
        if provider == 'DashScope' and not safe_base_url:
            params['base_url'] = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        model_class = cls._resolve_provider_class(provider)
        if model_class is None:
            raise ValueError(f'未知AI模型提供商：{provider}')

        return model_class(**params)
