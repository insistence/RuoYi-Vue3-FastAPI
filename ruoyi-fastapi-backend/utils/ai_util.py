from agno.db.base import AsyncBaseDb
from agno.db.mysql import AsyncMySQLDb
from agno.db.postgres import AsyncPostgresDb
from agno.models.aimlapi import AIMLAPI
from agno.models.anthropic import Claude
from agno.models.base import Model
from agno.models.cerebras import Cerebras, CerebrasOpenAI
from agno.models.cohere import Cohere
from agno.models.cometapi import CometAPI
from agno.models.dashscope import DashScope
from agno.models.deepinfra import DeepInfra
from agno.models.deepseek import DeepSeek
from agno.models.fireworks import Fireworks
from agno.models.google import Gemini
from agno.models.groq import Groq
from agno.models.huggingface import HuggingFace
from agno.models.langdb import LangDB
from agno.models.litellm import LiteLLM, LiteLLMOpenAI
from agno.models.llama_cpp import LlamaCpp
from agno.models.lmstudio import LMStudio
from agno.models.meta import Llama
from agno.models.mistral import MistralChat
from agno.models.n1n import N1N
from agno.models.nebius import Nebius
from agno.models.nexus import Nexus
from agno.models.nvidia import Nvidia
from agno.models.ollama import Ollama
from agno.models.openai import OpenAIChat
from agno.models.openai.responses import OpenAIResponses
from agno.models.openrouter import OpenRouter
from agno.models.perplexity import Perplexity
from agno.models.portkey import Portkey
from agno.models.requesty import Requesty
from agno.models.sambanova import Sambanova
from agno.models.siliconflow import Siliconflow
from agno.models.together import Together
from agno.models.vercel import V0
from agno.models.vllm import VLLM
from agno.models.xai import xAI

from config.database import async_engine
from config.env import DataBaseConfig

provider_model_map: dict[str, type[Model]] = {
    'AIMLAPI': AIMLAPI,
    'Anthropic': Claude,
    'Cerebras': Cerebras,
    'CerebrasOpenAI': CerebrasOpenAI,
    'Cohere': Cohere,
    'CometAPI': CometAPI,
    'DashScope': DashScope,
    'DeepInfra': DeepInfra,
    'DeepSeek': DeepSeek,
    'Fireworks': Fireworks,
    'Google': Gemini,
    'Groq': Groq,
    'HuggingFace': HuggingFace,
    'LangDB': LangDB,
    'LiteLLM': LiteLLM,
    'LiteLLMOpenAI': LiteLLMOpenAI,
    'LlamaCpp': LlamaCpp,
    'LMStudio': LMStudio,
    'Meta': Llama,
    'Mistral': MistralChat,
    'N1N': N1N,
    'Nebius': Nebius,
    'Nexus': Nexus,
    'Nvidia': Nvidia,
    'Ollama': Ollama,
    'OpenAI': OpenAIChat,
    'OpenAIResponses': OpenAIResponses,
    'OpenRouter': OpenRouter,
    'Perplexity': Perplexity,
    'Portkey': Portkey,
    'Requesty': Requesty,
    'Sambanova': Sambanova,
    'SiliconFlow': Siliconflow,
    'Together': Together,
    'Vercel': V0,
    'VLLM': VLLM,
    'xAI': xAI,
}


storage_engine_map: dict[str, type[AsyncBaseDb]] = {
    'mysql': AsyncMySQLDb,
    'postgresql': AsyncPostgresDb,
}


class AiUtil:
    """
    AI工具类
    """

    @classmethod
    def get_storage_engine(cls) -> AsyncBaseDb:
        """
        获取存储引擎实例

        :return: 存储引擎实例
        """
        storage_engine_class = storage_engine_map.get(DataBaseConfig.db_type, AsyncMySQLDb)

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
        **kwargs,
    ) -> Model:
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
        if provider == 'ollama':
            params['host'] = base_url
        if provider == 'DashScope' and not base_url:
            params['base_url'] = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        model_class = provider_model_map.get(provider, OpenAIChat)

        return model_class(**params)
