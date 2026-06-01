import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = PROJECT_ROOT / 'ruoyi-fastapi-frontend'
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.discovery.registry import PluginRegistry  # noqa: E402
from plugins.core.discovery.scanner import PluginScanner  # noqa: E402
from plugins.core.validation.structure import PluginStructureChecker  # noqa: E402

EXPECTED_AI_PERMISSIONS = {
    'ai:model:list',
    'ai:model:add',
    'ai:model:edit',
    'ai:model:remove',
    'ai:model:query',
    'ai:chat:list',
}
EXPECTED_AI_PYTHON_DEPENDENCIES = [
    'agno==2.4.8',
    'anthropic==0.78.0',
    'cerebras-cloud-sdk==1.67.0',
    'cohere==5.20.4',
    'google-genai==1.62.0',
    'groq==1.0.0',
    'litellm==1.81.8',
    'llama-api-client==0.6.0',
    'mistralai==1.12.0',
    'ollama==0.6.1',
    'openai==2.17.0',
    'portkey-ai==2.1.0',
]
EXPECTED_AI_NPM_DEPENDENCIES = [
    '@antv/infographic^0.2.13',
    'katex>=0.16.27',
    'markstream-vue>=0.0.7-beta.6',
    'mermaid>=11.12.2',
    'shiki^3.21.0',
    'stream-markdown>=0.0.14',
    'stream-monaco>=0.0.17',
]
EXPECTED_AI_NPM_DEV_DEPENDENCIES = ['vite-plugin-monaco-editor-esm==2.0.2']


def test_ai_plugin_template_can_be_discovered() -> None:
    """
    校验仓库内 AI 插件可以被插件扫描器读取。

    :return: None
    """
    plugin = PluginScanner(BACKEND_ROOT / 'plugins').load_manifest(BACKEND_ROOT / 'plugins' / 'ai' / 'plugin.yaml')

    assert plugin.manifest.id == 'ai'
    assert plugin.manifest.enabled is False
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
    assert set(plugin.manifest.permissions) == EXPECTED_AI_PERMISSIONS
    assert plugin.manifest.dependencies.python == EXPECTED_AI_PYTHON_DEPENDENCIES
    assert plugin.manifest.dependencies.npm == EXPECTED_AI_NPM_DEPENDENCIES
    assert plugin.manifest.dependencies.npm_dev == EXPECTED_AI_NPM_DEV_DEPENDENCIES


def test_ai_plugin_runtime_paths_exist() -> None:
    """
    校验 AI 插件后端和前端运行路径存在。

    :return: None
    """
    plugin = PluginScanner(BACKEND_ROOT / 'plugins').load_manifest(BACKEND_ROOT / 'plugins' / 'ai' / 'plugin.yaml')
    registry = PluginRegistry.build([plugin])

    assert registry.get_enabled_controller_dirs() == []
    assert registry.get_enabled_entity_do_dirs() == []
    assert (BACKEND_ROOT / 'plugins' / 'ai' / 'controller').is_dir()
    assert (BACKEND_ROOT / 'plugins' / 'ai' / 'entity' / 'do').is_dir()
    assert (FRONTEND_ROOT / 'plugins' / 'ai' / 'views' / 'model' / 'index.vue').is_file()
    assert (FRONTEND_ROOT / 'plugins' / 'ai' / 'views' / 'chat' / 'index.vue').is_file()
    assert not (FRONTEND_ROOT / 'src' / 'api' / 'ai').exists()
    assert not (FRONTEND_ROOT / 'src' / 'views' / 'ai').exists()


def test_ai_plugin_does_not_use_package_aggregation_init() -> None:
    """
    校验 AI 插件不维护聚合入口文件。

    :return: None
    """
    assert not (BACKEND_ROOT / 'plugins' / 'ai' / '__init__.py').exists()


def test_ai_plugin_structure_check_passes() -> None:
    """
    校验 AI 插件目录满足插件结构检查。

    :return: None
    """
    plugin = PluginScanner(BACKEND_ROOT / 'plugins').load_manifest(BACKEND_ROOT / 'plugins' / 'ai' / 'plugin.yaml')
    result = PluginStructureChecker(BACKEND_ROOT).check(plugin)

    assert result.ok is True
    assert result.failed_items == []


def test_ai_plugin_keeps_original_backend_api_paths() -> None:
    """
    校验 AI 插件控制器保持原有接口路径。

    :return: None
    """
    model_controller = (BACKEND_ROOT / 'plugins' / 'ai' / 'controller' / 'ai_model_controller.py').read_text(
        encoding='utf-8'
    )
    chat_controller = (BACKEND_ROOT / 'plugins' / 'ai' / 'controller' / 'ai_chat_controller.py').read_text(
        encoding='utf-8'
    )

    assert "prefix='/ai/model'" in model_controller
    assert "prefix='/ai/chat'" in chat_controller
    assert "'/list'" in model_controller
    assert "'/all'" in model_controller
    assert "'/{model_id}'" in model_controller
    assert "'/send'" in chat_controller
    assert "'/config'" in chat_controller
    assert "'/session/list'" in chat_controller


def test_ai_plugin_frontend_api_keeps_original_backend_paths() -> None:
    """
    校验 AI 前端插件 API 仍调用原有后端路径。

    :return: None
    """
    model_api = (FRONTEND_ROOT / 'plugins' / 'ai' / 'api' / 'model.js').read_text(encoding='utf-8')
    chat_api = (FRONTEND_ROOT / 'plugins' / 'ai' / 'api' / 'chat.js').read_text(encoding='utf-8')
    model_view = (FRONTEND_ROOT / 'plugins' / 'ai' / 'views' / 'model' / 'index.vue').read_text(encoding='utf-8')
    chat_view = (FRONTEND_ROOT / 'plugins' / 'ai' / 'views' / 'chat' / 'index.vue').read_text(encoding='utf-8')

    assert '"/ai/model/list"' in model_api
    assert '"/ai/model/all"' in model_api
    assert '"/ai/model/" + modelId' in model_api
    assert '"/ai/chat/config"' in chat_api
    assert '"/ai/chat/session/list"' in chat_api
    assert '"/ai/chat/send"' in chat_view
    assert '@/api/ai' not in model_view
    assert '@/api/ai' not in chat_view
    assert '../../api/model' in model_view
    assert '../../api/model' in chat_view
    assert '../../api/chat' in chat_view


def test_ai_plugin_sql_assets_own_ai_schema_and_seed_data() -> None:
    """
    校验 AI 插件通过 SQL migration 和 seed 管理自身数据。

    :return: None
    """
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
