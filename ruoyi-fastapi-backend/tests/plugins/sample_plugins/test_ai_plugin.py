from pathlib import Path

import pytest

from cli.runtime.plugin.scaffold import PluginFrontendVersionResolver
from exceptions.exception import ServiceException
from plugins.ai.dao.ai_chat_dao import AiChatConfigDao
from plugins.ai.dao.ai_model_dao import AiModelDao
from plugins.ai.entity.vo.ai_chat_vo import AiChatConfigModel, AiChatRequestModel
from plugins.ai.service.ai_chat_service import AiChatService
from plugins.ai.utils.ai_util import AiUtil
from plugins.core.discovery.registry import PluginRegistry
from plugins.core.discovery.scanner import PluginScanner
from plugins.core.management.entity.vo.schemas import PluginModel
from plugins.core.validation.structure import PluginStructureChecker

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = PROJECT_ROOT / 'ruoyi-fastapi-frontend'
FRONTEND_VERSION = PluginFrontendVersionResolver.resolve(FRONTEND_ROOT)

EXPECTED_AI_PERMISSIONS = {
    'ai:model:list',
    'ai:model:add',
    'ai:model:edit',
    'ai:model:remove',
    'ai:model:query',
    'ai:chat:list',
}
EXPECTED_AI_PYTHON_DEPENDENCIES = [
    'agno==2.8.6',
    'anthropic==0.120.2',
    'cerebras-cloud-sdk==1.91.0',
    'cohere==7.0.8',
    'google-genai==2.16.0',
    'groq==1.6.0',
    'litellm==1.94.0',
    'llama-api-client==0.6.0',
    'mistralai==2.8.0',
    'ollama==0.6.2',
    'openai==2.52.0',
    'portkey-ai==2.3.4',
]
EXPECTED_AI_VUE2_NPM_DEPENDENCIES = [
    '@antv/infographic^0.2.13',
    '@terrastruct/d2>=0.1.33',
    'katex>=0.16.27',
    'markstream-vue2^0.0.50',
    'mermaid>=11.15.0',
    'shiki^3.21.0',
    'stream-markdown>=0.0.16',
    'stream-monaco>=0.0.48',
]
EXPECTED_AI_VUE3_NPM_DEPENDENCIES = [
    '@antv/infographic^0.2.13',
    '@terrastruct/d2>=0.1.33',
    'katex>=0.16.27',
    'markstream-vue>=1.0.9-beta.2',
    'mermaid>=11.15.0',
    'shiki^3.21.0',
    'stream-diffs>=0.0.2',
    'stream-markdown>=0.0.16',
    'stream-monaco>=0.0.48',
]
EXPECTED_AI_VUE3_NPM_DEV_DEPENDENCIES = ['vite-plugin-monaco-editor-esm==2.0.2']
EXPECTED_DEFAULT_NUM_HISTORY_RUNS = 3


def test_ai_plugin_template_can_be_discovered() -> None:
    """校验仓库内 AI 插件可以被插件扫描器读取。"""
    plugin = PluginScanner(BACKEND_ROOT / 'plugins').load_manifest(BACKEND_ROOT / 'plugins' / 'ai' / 'plugin.yaml')

    assert plugin.manifest.id == 'ai'
    assert plugin.manifest.backend.module == 'plugins.ai'
    assert plugin.manifest.backend.migrations == [
        'migrations/mysql/001_init.sql',
        'migrations/postgresql/001_init.sql',
    ]
    assert plugin.manifest.backend.seeds == [
        'seeds/mysql/ai_provider_type.sql',
        'seeds/postgresql/ai_provider_type.sql',
    ]
    assert plugin.manifest.frontend.menus[0].children[0].component == 'plugin/ai/model/index'
    assert plugin.manifest.frontend.menus[0].children[1].component == 'plugin/ai/chat/index'
    assert set(plugin.manifest.permission_codes) == EXPECTED_AI_PERMISSIONS
    assert plugin.manifest.permission_name_map['ai:model:add'] == '新增模型'
    assert plugin.manifest.dependencies.python == EXPECTED_AI_PYTHON_DEPENDENCIES
    assert plugin.manifest.config.items == []


@pytest.mark.skipif(FRONTEND_VERSION != 'vue2', reason='当前项目不是 Vue 2 前端')
def test_ai_plugin_vue2_frontend_dependencies() -> None:
    """校验 Vue 2 项目的 AI 插件声明 Vue 2 专属前端依赖。"""
    plugin = PluginScanner(BACKEND_ROOT / 'plugins').load_manifest(BACKEND_ROOT / 'plugins' / 'ai' / 'plugin.yaml')

    assert plugin.manifest.dependencies.npm == EXPECTED_AI_VUE2_NPM_DEPENDENCIES
    assert plugin.manifest.dependencies.npm_dev == []


@pytest.mark.skipif(FRONTEND_VERSION != 'vue3', reason='当前项目不是 Vue 3 前端')
def test_ai_plugin_vue3_frontend_dependencies() -> None:
    """校验 Vue 3 项目的 AI 插件声明 Vue 3 专属前端依赖。"""
    plugin = PluginScanner(BACKEND_ROOT / 'plugins').load_manifest(BACKEND_ROOT / 'plugins' / 'ai' / 'plugin.yaml')

    assert plugin.manifest.dependencies.npm == EXPECTED_AI_VUE3_NPM_DEPENDENCIES
    assert plugin.manifest.dependencies.npm_dev == EXPECTED_AI_VUE3_NPM_DEV_DEPENDENCIES


def test_ai_plugin_runtime_paths_exist() -> None:
    """校验 AI 插件后端和前端运行路径存在。"""
    plugin = PluginScanner(BACKEND_ROOT / 'plugins').load_manifest(BACKEND_ROOT / 'plugins' / 'ai' / 'plugin.yaml')
    registry = PluginRegistry.build(
        [plugin],
        [
            PluginModel(
                pluginId='ai',
                pluginName='AI 管理',
                version='0.1.0',
                installedVersion='0.1.0',
                enabled='0',
                status='installed',
            )
        ],
    )

    assert registry.get_enabled_controller_dirs() == [BACKEND_ROOT / 'plugins' / 'ai' / 'controller']
    assert registry.get_enabled_entity_do_dirs() == [BACKEND_ROOT / 'plugins' / 'ai' / 'entity' / 'do']
    assert (BACKEND_ROOT / 'plugins' / 'ai' / 'controller').is_dir()
    assert (BACKEND_ROOT / 'plugins' / 'ai' / 'entity' / 'do').is_dir()
    assert (FRONTEND_ROOT / 'plugins' / 'ai' / 'views' / 'model' / 'index.vue').is_file()
    assert (FRONTEND_ROOT / 'plugins' / 'ai' / 'views' / 'chat' / 'index.vue').is_file()
    assert not (FRONTEND_ROOT / 'src' / 'api' / 'ai').exists()
    assert not (FRONTEND_ROOT / 'src' / 'views' / 'ai').exists()


def test_ai_plugin_structure_check_passes() -> None:
    """校验 AI 插件目录满足插件结构检查。"""
    plugin = PluginScanner(BACKEND_ROOT / 'plugins').load_manifest(BACKEND_ROOT / 'plugins' / 'ai' / 'plugin.yaml')
    result = PluginStructureChecker(BACKEND_ROOT).check(plugin)

    assert result.ok is True
    assert result.failed_items == []


@pytest.mark.asyncio
async def test_ai_chat_config_detail_returns_vo_when_config_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验 AI 对话配置不存在时服务返回 VO 默认模型，而不是 DO 对象。"""

    async def fake_get_chat_config_detail_by_user_id(*_args: object, **_kwargs: object) -> None:
        """返回测试用 AI 聊天配置。"""

    monkeypatch.setattr(
        AiChatConfigDao,
        'get_chat_config_detail_by_user_id',
        fake_get_chat_config_detail_by_user_id,
    )

    result = await AiChatService.ai_chat_config_detail_services(query_db=object(), user_id=1)

    assert isinstance(result, AiChatConfigModel)
    assert result.num_history_runs == EXPECTED_DEFAULT_NUM_HISTORY_RUNS


@pytest.mark.asyncio
async def test_ai_chat_services_rejects_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验 AI 对话在模型不存在时直接返回明确业务异常。"""

    async def fake_get_ai_model_detail_by_id(*_args: object, **_kwargs: object) -> None:
        """返回测试用 AI 模型配置。"""

    monkeypatch.setattr(AiModelDao, 'get_ai_model_detail_by_id', fake_get_ai_model_detail_by_id)

    stream = AiChatService.chat_services(
        query_db=object(),
        chat_req=AiChatRequestModel(modelId=404, message='hi'),
        user_id=1,
    )

    with pytest.raises(ServiceException) as exc_info:
        await anext(stream)
    assert exc_info.value.message == '模型不存在'


@pytest.mark.asyncio
async def test_ai_chat_services_rejects_disabled_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验 AI 对话不能使用已停用模型。"""

    async def fake_get_ai_model_detail_by_id(*_args: object, **_kwargs: object) -> dict[str, object]:
        """返回测试用 AI 模型配置。"""
        return {
            'model_id': 1,
            'model_code': 'gpt-4o-mini',
            'model_name': 'GPT',
            'provider': 'OpenAI',
            'api_key': 'encrypted',
            'status': '1',
            'support_reasoning': 'N',
            'support_images': 'N',
        }

    monkeypatch.setattr(AiModelDao, 'get_ai_model_detail_by_id', fake_get_ai_model_detail_by_id)

    stream = AiChatService.chat_services(
        query_db=object(),
        chat_req=AiChatRequestModel(modelId=1, message='hi'),
        user_id=1,
    )

    with pytest.raises(ServiceException) as exc_info:
        await anext(stream)
    assert exc_info.value.message == '模型已停用'


def test_ai_model_factory_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验未知 AI provider 不会静默回退到 OpenAI。"""

    class FakeModel:
        """
        测试用模型类。
        """

        def __init__(self, **kwargs: object) -> None:
            """初始化测试用 AI 模型提供者。"""
            self.kwargs = kwargs

    def fake_resolve_provider_class(cls: type[AiUtil], provider: str) -> type[FakeModel] | None:
        """返回测试用 AI 模型提供者类。"""
        return FakeModel if provider == 'OpenAI' else None

    monkeypatch.setattr(AiUtil, '_resolve_provider_class', classmethod(fake_resolve_provider_class))

    with pytest.raises(ValueError, match='未知AI模型提供商'):
        AiUtil.get_model_from_factory(
            provider='UnknownAI',
            model_code='demo',
            model_name='Demo',
            api_key='secret',
        )


def test_ai_model_factory_validates_base_url_boundary() -> None:
    """校验 AI 模型工厂限制基础 URL 的信任边界。"""
    assert AiUtil._validate_base_url('https://api.example.com/v1') == 'https://api.example.com/v1'

    blocked_urls = (
        'http://127.0.0.1:8000',
        'http://10.0.0.1',
        'http://localhost:8000',
        'ftp://api.example.com',
    )
    for base_url in blocked_urls:
        with pytest.raises(ValueError):
            AiUtil._validate_base_url(base_url)


def test_ai_plugin_sql_assets_own_ai_schema_and_seed_data() -> None:
    """校验 AI 插件通过 SQL migration 和 seed 管理自身数据。"""
    plugin_root = BACKEND_ROOT / 'plugins' / 'ai'
    mysql_migration = (plugin_root / 'migrations' / 'mysql' / '001_init.sql').read_text(encoding='utf-8')
    postgres_migration = (plugin_root / 'migrations' / 'postgresql' / '001_init.sql').read_text(encoding='utf-8')
    mysql_seed = (plugin_root / 'seeds' / 'mysql' / 'ai_provider_type.sql').read_text(encoding='utf-8')
    postgres_seed = (plugin_root / 'seeds' / 'postgresql' / 'ai_provider_type.sql').read_text(encoding='utf-8')

    for sql_content in (mysql_migration, postgres_migration):
        assert '-- AI模型表' in sql_content
        assert '-- AI对话配置表' in sql_content
        assert 'create table ai_models' in sql_content
        assert 'create table ai_chat_config' in sql_content
    for sql_content in (mysql_seed, postgres_seed):
        assert '-- 初始化-字典类型表数据' in sql_content
        assert '-- 初始化-字典数据表数据' in sql_content
        assert 'ai_provider_type' in sql_content
        assert 'OpenAI' in sql_content
    assert 'sysdate()' in mysql_seed
    assert 'current_timestamp' not in mysql_seed
    assert 'current_timestamp' in postgres_seed
    assert 'sysdate()' not in postgres_seed
    assert 'auto_increment' in mysql_migration
    assert 'engine=innodb' in mysql_migration
    assert 'bigserial' not in mysql_migration
    assert 'comment on column' not in mysql_migration
    assert 'bigserial' in postgres_migration
    assert 'comment on column' in postgres_migration
    assert 'auto_increment' not in postgres_migration
    assert 'engine=innodb' not in postgres_migration
