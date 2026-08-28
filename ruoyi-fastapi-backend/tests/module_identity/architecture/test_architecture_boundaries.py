"""统一认证模块分层边界测试。"""

import ast
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_IDENTITY_ROOT = _BACKEND_ROOT / 'module_identity'
_SQL_CALL_NAMES = {'delete', 'insert', 'select', 'update'}
_DB_EXECUTION_METHODS = {'add', 'delete', 'execute', 'flush', 'scalar', 'scalars'}
_HTTP_ROUTE_METHODS = {'api_route', 'delete', 'get', 'head', 'options', 'patch', 'post', 'put'}


def _python_files(directory: str) -> list[Path]:
    """返回指定认证模块目录下的生产 Python 文件。"""
    return sorted((_IDENTITY_ROOT / directory).glob('*.py'))


def _parse(path: Path) -> ast.Module:
    """将生产文件解析为抽象语法树。"""
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def _imported_modules(tree: ast.Module) -> set[str]:
    """收集语法树中的完整导入模块路径。"""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_controllers_do_not_depend_on_dao_or_database_models() -> None:
    """Controller 只能依赖 DTO 和 Service，不得越层访问 DAO 或 DO。"""
    violations: list[str] = []
    for path in _python_files('controller'):
        modules = _imported_modules(_parse(path))
        forbidden = sorted(
            module for module in modules if module.startswith(('module_identity.dao', 'module_identity.entity.do'))
        )
        if forbidden:
            violations.append(f'{path.name}: {", ".join(forbidden)}')
    assert not violations, '\n'.join(violations)


def test_services_do_not_construct_or_execute_database_statements() -> None:
    """Service 负责编排事务，SQL 构造和数据库执行必须位于 DAO。"""
    violations: list[str] = []
    for path in _python_files('service'):
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SQL_CALL_NAMES:
                violations.append(f'{path.name}:{node.lineno}: {node.func.id}()')
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _DB_EXECUTION_METHODS
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id == 'db' or node.func.value.id.endswith('_db'))
            ):
                continue
            violations.append(f'{path.name}:{node.lineno}: {node.func.value.id}.{node.func.attr}()')
    assert not violations, '\n'.join(violations)


def test_services_do_not_contain_controller_dependencies() -> None:
    """Service 不得包含路由注册器或数据库依赖注入声明。"""
    violations: list[str] = []
    for path in _python_files('service'):
        tree = _parse(path)
        imported_names = {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names
        }
        forbidden = sorted(imported_names & {'APIRouterPro', 'DBSessionDependency'})
        if forbidden:
            violations.append(f'{path.name}: {", ".join(forbidden)}')
    assert not violations, '\n'.join(violations)


def test_controller_dependencies_use_annotated_style() -> None:
    """Controller 依赖必须使用项目统一的 ``Annotated`` 声明。"""
    violations: list[str] = []
    for path in _python_files('controller'):
        for node in ast.walk(_parse(path)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            defaults = [*node.args.defaults, *node.args.kw_defaults]
            violations.extend(
                f'{path.name}:{default.lineno}: {default.func.id}()'
                for default in defaults
                if isinstance(default, ast.Call)
                and isinstance(default.func, ast.Name)
                and default.func.id.endswith('Dependency')
            )
    assert not violations, '\n'.join(violations)


def _route_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    """返回函数上的 HTTP 路由装饰器。"""
    return [
        decorator
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in _HTTP_ROUTE_METHODS
    ]


def _doc_param_names(docstring: str) -> set[str]:
    """提取 Sphinx 文档字符串中的参数名称。"""
    return {
        line.removeprefix(':param ').split(':', 1)[0].strip()
        for line in docstring.splitlines()
        if line.startswith(':param ')
    }


def _block_docstring(path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查函数文档字符串是否采用项目统一的独占行格式。"""
    if not node.body or not isinstance(node.body[0], ast.Expr):
        return False
    expression = node.body[0].value
    if not isinstance(expression, ast.Constant) or not isinstance(expression.value, str):
        return False
    lines = path.read_text(encoding='utf-8').splitlines()
    opening_index = expression.lineno - 1
    if lines[opening_index].strip() not in {'"""', "'''"}:
        opening_index -= 1
    opening = lines[opening_index].strip()
    closing = lines[expression.end_lineno - 1].strip()
    doc_lines = expression.value.splitlines()
    return opening in {'"""', "'''"} and closing == opening and len(doc_lines) > 1 and bool(doc_lines[1].strip())


def _internal_doc_violations(
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    first_route_lineno: int | None,
) -> list[str]:
    """返回内部函数的顺序和文档违规信息。"""
    violations: list[str] = []
    docstring = ast.get_docstring(node)
    if node.col_offset != 0:
        violations.append(f'{path.name}:{node.lineno}: 非路由函数必须位于模块级作用域')
    if first_route_lineno is not None and node.lineno >= first_route_lineno:
        violations.append(f'{path.name}:{node.lineno}: 非路由函数必须位于首个路由函数之前')
    if docstring is None or not _block_docstring(path, node):
        violations.append(f'{path.name}:{node.lineno}: 非路由函数必须使用独占行多行 docstring')
        return violations
    arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    if node.args.vararg is not None:
        arguments.append(node.args.vararg)
    if node.args.kwarg is not None:
        arguments.append(node.args.kwarg)
    documented_params = _doc_param_names(docstring)
    violations.extend(
        f'{path.name}:{node.lineno}: 缺少 :param {argument.arg}:'
        for argument in arguments
        if argument.arg not in {'self', 'cls'} and argument.arg not in documented_params
    )
    if node.returns is not None and ':return:' not in docstring:
        violations.append(f'{path.name}:{node.lineno}: 缺少 :return:')
    return violations


def _route_doc_violations(
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    route_decorators: list[ast.Call],
) -> list[str]:
    """返回路由函数文档和 OpenAPI 文案违规信息。"""
    violations: list[str] = []
    if ast.get_docstring(node) is not None:
        violations.append(f'{path.name}:{node.lineno}: 路由函数不得使用 docstring')
    for decorator in route_decorators:
        keywords = {keyword.arg: keyword.value for keyword in decorator.keywords if keyword.arg is not None}
        summary = keywords.get('summary')
        description = keywords.get('description')
        if (
            not isinstance(summary, ast.Constant)
            or not isinstance(summary.value, str)
            or not summary.value.endswith('接口')
        ):
            violations.append(f'{path.name}:{node.lineno}: 路由 summary 必须是以“接口”结尾的字符串')
        if (
            not isinstance(description, ast.Constant)
            or not isinstance(description.value, str)
            or not description.value.startswith('用于')
        ):
            violations.append(f'{path.name}:{node.lineno}: 路由 description 必须是以“用于”开头的字符串')
    return violations


def test_identity_packages_do_not_reexport_implementation_details() -> None:
    """包入口保持空白，调用方必须从职责明确的模块显式导入。"""
    violations = [
        str(path.relative_to(_BACKEND_ROOT))
        for path in sorted(_IDENTITY_ROOT.rglob('__init__.py'))
        if path.read_text(encoding='utf-8').strip()
    ]
    assert not violations, '\n'.join(violations)


def test_removed_facades_and_merged_modules_do_not_return() -> None:
    """禁止重新引入旧 Facade 或已经合并的薄模块。"""
    removed_paths = [
        _IDENTITY_ROOT / 'exceptions.py',
        _IDENTITY_ROOT / 'controller' / 'logout_controller.py',
        _IDENTITY_ROOT / 'controller' / 'userinfo_controller.py',
        _IDENTITY_ROOT / 'service' / 'oauth_management_application_service.py',
        _IDENTITY_ROOT / 'service' / 'authorization_flow_service.py',
        _IDENTITY_ROOT / 'service' / 'token_endpoint_service.py',
        _IDENTITY_ROOT / 'service' / 'oauth_audit_management_service.py',
        _IDENTITY_ROOT / 'service' / 'interaction_audit_service.py',
        _IDENTITY_ROOT / 'service' / 'authorization_code_service.py',
        _IDENTITY_ROOT / 'service' / 'claim_service.py',
        _IDENTITY_ROOT / 'service' / 'credential_authentication_service.py',
        _IDENTITY_ROOT / 'service' / 'identity_security_event_service.py',
        _IDENTITY_ROOT / 'service' / 'identity_subject_service.py',
        _IDENTITY_ROOT / 'service' / 'interaction_completion_service.py',
        _IDENTITY_ROOT / 'service' / 'interaction_consent_service.py',
        _IDENTITY_ROOT / 'service' / 'interaction_flow_service.py',
        _IDENTITY_ROOT / 'service' / 'interaction_login_service.py',
        _IDENTITY_ROOT / 'service' / 'introspection_service.py',
        _IDENTITY_ROOT / 'service' / 'logout_service.py',
        _IDENTITY_ROOT / 'service' / 'oauth_client_management_service.py',
        _IDENTITY_ROOT / 'service' / 'oauth_management_base.py',
        _IDENTITY_ROOT / 'service' / 'oauth_resource_management_service.py',
        _IDENTITY_ROOT / 'service' / 'oidc_key_management_service.py',
        _IDENTITY_ROOT / 'service' / 'rate_limit_service.py',
        _IDENTITY_ROOT / 'service' / 'revocation_service.py',
        _IDENTITY_ROOT / 'service' / 'sso_session_service.py',
        _IDENTITY_ROOT / 'service' / 'transaction_coordinator.py',
        _IDENTITY_ROOT / 'service' / 'userinfo_service.py',
    ]
    assert not [str(path.relative_to(_BACKEND_ROOT)) for path in removed_paths if path.exists()]

    authorization_tree = _parse(_IDENTITY_ROOT / 'service' / 'authorization_service.py')
    assert not [
        node.name
        for node in authorization_tree.body
        if isinstance(node, ast.ClassDef) and node.name == 'AuthorizationRequestService'
    ]


def test_protocol_and_interaction_services_do_not_import_fastapi_http_types() -> None:
    """协议与交互核心 Service 只接收领域数据，不得依赖 FastAPI HTTP 类型。"""
    names = {
        'authorization_service.py',
        'consent_service.py',
        'identity_service.py',
        'interaction_service.py',
        'session_service.py',
        'token_protocol_service.py',
        'token_service.py',
    }
    forbidden = {'Request', 'Response', 'JSONResponse', 'RedirectResponse', 'HTTPException'}
    violations: list[str] = []
    for path in _python_files('service'):
        if path.name not in names:
            continue
        tree = _parse(path)
        imported_modules = _imported_modules(tree)
        http_modules = sorted(module for module in imported_modules if module.startswith(('fastapi', 'starlette')))
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        if imported_names & forbidden or http_modules:
            violations.append(f'{path.name}: names={sorted(imported_names & forbidden)}, modules={http_modules}')
    assert not violations, '\n'.join(violations)


def test_dependencies_delegate_database_access_to_daos() -> None:
    """协议依赖不得自行拼 SQL 或依赖 ORM DO，只能调用明确的 DAO。"""
    path = _IDENTITY_ROOT / 'dependencies.py'
    tree = _parse(path)
    imported_modules = _imported_modules(tree)
    forbidden_modules = {
        module
        for module in imported_modules
        if module == 'sqlalchemy'
        or module.startswith(('sqlalchemy.sql', 'sqlalchemy.orm', 'module_identity.entity.do'))
    }
    assert not forbidden_modules, f'{path.name}: {sorted(forbidden_modules)}'

    forbidden_calls = [
        f'{path.name}:{node.lineno}: {node.func.id}()'
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SQL_CALL_NAMES
    ]
    forbidden_calls.extend(
        f'{path.name}:{node.lineno}: {node.func.value.id}.{node.func.attr}()'
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {'db', 'query_db'}
        and node.func.attr in _DB_EXECUTION_METHODS
    )
    assert not forbidden_calls, '\n'.join(forbidden_calls)

    dao_calls = {
        (node.func.value.id, node.func.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
    }
    assert ('OidcKeyDao', 'get_verifying') in dao_calls


def test_logout_service_has_no_direct_http_client_or_socket_dependency() -> None:
    """Logout Service 的协议编排不得携带 HTTP 客户端和 Socket 实现依赖。"""
    path = _IDENTITY_ROOT / 'service' / 'session_service.py'
    imported_modules = _imported_modules(_parse(path))
    forbidden = sorted(
        module
        for module in imported_modules
        if module in {'socket', 'httpx', 'httpcore'} or module.startswith(('httpx.', 'httpcore.'))
    )
    assert not forbidden, f'{path.name}: {forbidden}'


def test_admin_user_dao_and_identity_services_keep_identity_queries_in_identity_layer() -> None:
    """Admin UserDao 不得出现身份专用查询名，身份 Service 也不得反向依赖它。"""
    user_dao = _BACKEND_ROOT / 'module_admin' / 'dao' / 'user_dao.py'
    source = user_dao.read_text(encoding='utf-8').lower()
    forbidden_terms = ('identity', 'subject', 'auth_version', 'sso_session')
    assert not [term for term in forbidden_terms if term in source], user_dao.name

    violations: list[str] = []
    for path in _python_files('service'):
        tree = _parse(path)
        modules = _imported_modules(tree)
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        if 'module_admin.dao.user_dao' in modules or 'UserDao' in imported_names:
            violations.append(path.name)
    assert not violations, ', '.join(violations)


def test_protocol_controllers_do_not_manage_database_transactions() -> None:
    """协议与交互 Controller 只适配 HTTP，事务必须由核心 Service 完成。"""
    violations: list[str] = []
    for path in (
        _IDENTITY_ROOT / 'controller' / 'authorization_controller.py',
        _IDENTITY_ROOT / 'controller' / 'interaction_controller.py',
        _IDENTITY_ROOT / 'controller' / 'token_controller.py',
    ):
        tree = _parse(path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {'commit', 'rollback'}
            ):
                violations.append(f'{path.name}:{node.lineno}: {node.func.attr}()')
            elif isinstance(node, ast.Name) and node.id == 'AfterCommitCoordinator':
                violations.append(f'{path.name}:{node.lineno}: AfterCommitCoordinator')
    assert not violations, '\n'.join(violations)
