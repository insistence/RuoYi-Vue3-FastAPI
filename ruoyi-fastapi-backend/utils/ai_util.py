import importlib
from typing import TYPE_CHECKING, Any

from config.database import async_engine
from config.env import DataBaseConfig

if TYPE_CHECKING:
    from agno.db.base import AsyncBaseDb
    from agno.models.base import Model


provider_model_config: dict[str, dict[str, str]] = {
    'AIMLAPI': {'module': 'agno.models.aimlapi', 'class': 'AIMLAPI'},
    'Anthropic': {'module': 'agno.models.anthropic', 'class': 'Claude'},
    'Cerebras': {'module': 'agno.models.cerebras', 'class': 'Cerebras'},
    'CerebrasOpenAI': {'module': 'agno.models.cerebras', 'class': 'CerebrasOpenAI'},
    'Cohere': {'module': 'agno.models.cohere', 'class': 'Cohere'},
    'CometAPI': {'module': 'agno.models.cometapi', 'class': 'CometAPI'},
    'DashScope': {'module': 'agno.models.dashscope', 'class': 'DashScope'},
    'DeepInfra': {'module': 'agno.models.deepinfra', 'class': 'DeepInfra'},
    'DeepSeek': {'module': 'agno.models.deepseek', 'class': 'DeepSeek'},
    'Fireworks': {'module': 'agno.models.fireworks', 'class': 'Fireworks'},
    'Google': {'module': 'agno.models.google', 'class': 'Gemini'},
    'Groq': {'module': 'agno.models.groq', 'class': 'Groq'},
    'HuggingFace': {'module': 'agno.models.huggingface', 'class': 'HuggingFace'},
    'LangDB': {'module': 'agno.models.langdb', 'class': 'LangDB'},
    'LiteLLM': {'module': 'agno.models.litellm', 'class': 'LiteLLM'},
    'LiteLLMOpenAI': {'module': 'agno.models.litellm', 'class': 'LiteLLMOpenAI'},
    'LlamaCpp': {'module': 'agno.models.llama_cpp', 'class': 'LlamaCpp'},
    'LMStudio': {'module': 'agno.models.lmstudio', 'class': 'LMStudio'},
    'Meta': {'module': 'agno.models.meta', 'class': 'Llama'},
    'Mistral': {'module': 'agno.models.mistral', 'class': 'MistralChat'},
    'N1N': {'module': 'agno.models.n1n', 'class': 'N1N'},
    'Nebius': {'module': 'agno.models.nebius', 'class': 'Nebius'},
    'Nexus': {'module': 'agno.models.nexus', 'class': 'Nexus'},
    'Nvidia': {'module': 'agno.models.nvidia', 'class': 'Nvidia'},
    'Ollama': {'module': 'agno.models.ollama', 'class': 'Ollama'},
    'OpenAI': {'module': 'agno.models.openai', 'class': 'OpenAIChat'},
    'OpenAIResponses': {'module': 'agno.models.openai.responses', 'class': 'OpenAIResponses'},
    'OpenRouter': {'module': 'agno.models.openrouter', 'class': 'OpenRouter'},
    'Perplexity': {'module': 'agno.models.perplexity', 'class': 'Perplexity'},
    'Portkey': {'module': 'agno.models.portkey', 'class': 'Portkey'},
    'Requesty': {'module': 'agno.models.requesty', 'class': 'Requesty'},
    'Sambanova': {'module': 'agno.models.sambanova', 'class': 'Sambanova'},
    'SiliconFlow': {'module': 'agno.models.siliconflow', 'class': 'Siliconflow'},
    'Together': {'module': 'agno.models.together', 'class': 'Together'},
    'Vercel': {'module': 'agno.models.vercel', 'class': 'V0'},
    'VLLM': {'module': 'agno.models.vllm', 'class': 'VLLM'},
    'xAI': {'module': 'agno.models.xai', 'class': 'xAI'},
}


storage_engine_config: dict[str, dict[str, str]] = {
    'mysql': {'module': 'agno.db.mysql', 'class': 'AsyncMySQLDb'},
    'postgresql': {'module': 'agno.db.postgres', 'class': 'AsyncPostgresDb'},
}


class AiUtil:
    """
    AI工具类
    """

    @classmethod
    def get_storage_engine(cls) -> 'AsyncBaseDb':
        """
        获取存储引擎实例

        :return: 存储引擎实例
        """
        config = storage_engine_config.get(DataBaseConfig.db_type)
        if not config:
            # 默认为MySQL
            config = storage_engine_config['mysql']

        module = importlib.import_module(config['module'])
        storage_engine_class = getattr(module, config['class'])

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
    def get_model_from_factory(
        cls,
        provider: str,
        model_code: str,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
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
        params = {
            'id': model_code,
            'name': model_name,
            'base_url': base_url,
            'api_key': api_key,
            'temperature': temperature,
            'max_tokens': max_tokens,
            **kwargs,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if provider == 'Ollama':
            params['host'] = base_url
        if provider == 'DashScope' and not base_url:
            params['base_url'] = 'https://dashscope.aliyuncs.com/compatible-mode/v1'

        config = provider_model_config.get(provider)
        if not config:
            # 默认为OpenAI
            config = provider_model_config['OpenAI']

        module = importlib.import_module(config['module'])
        model_class = getattr(module, config['class'])

        return model_class(**params)
