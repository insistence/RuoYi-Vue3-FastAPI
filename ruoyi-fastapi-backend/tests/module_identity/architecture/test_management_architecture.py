"""统一认证管理 Service 的分层架构守卫。"""

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).parents[3]
MANAGEMENT_SERVICES = ('oauth_management_service.py',)


def test_all_management_services_are_framework_and_app_state_free() -> None:
    """所有管理 Service 不得反向依赖 FastAPI 请求或应用状态。"""
    service_dir = BACKEND_ROOT / 'module_identity' / 'service'
    forbidden_request = re.compile(r'\bRequest\b')
    forbidden_fastapi_import = re.compile(r'^\s*(?:from|import)\s+fastapi(?:\.|\s|$)', re.MULTILINE)
    for path in sorted(service_dir.glob('*management_service.py')):
        source = path.read_text(encoding='utf-8')
        assert forbidden_fastapi_import.search(source) is None, path.name
        assert forbidden_request.search(source) is None, path.name
        assert 'app.state' not in source, path.name
