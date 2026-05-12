from pathlib import Path
from types import SimpleNamespace

import pytest

from cli.exit_codes import ARGUMENT_ERROR
from cli.runtime.gen import GenRuntimeService
from cli.runtime.gen.gateway import GenInfrastructureGateway
from cli.runtime.gen.support import GenDomainSupport

REDIS_UNUSED = 'unused'


def test_gen_domain_support_resolves_sql_text_from_argument() -> None:
    """
    校验代码生成领域支持对象会优先使用直接传入的 SQL 文本。

    :return: None
    """
    support = GenDomainSupport(GenInfrastructureGateway())

    payload = support.resolve_sql_text(' CREATE TABLE demo(id bigint); ', '')

    assert payload == 'CREATE TABLE demo(id bigint);'


def test_gen_domain_support_resolve_sql_text_rejects_invalid_inputs(tmp_path: Path) -> None:
    """
    校验代码生成领域支持对象会拒绝无效 SQL 输入组合。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    support = GenDomainSupport(GenInfrastructureGateway())
    sql_file = tmp_path / 'demo.sql'
    sql_file.write_text('select 1', encoding='utf-8')

    try:
        support.resolve_sql_text('select 1', str(sql_file))
    except ValueError as exc:
        assert '必须且只能传入 --sql 或 --sql-file 其中一种方式' in str(exc)
    else:
        raise AssertionError('expected ValueError for conflicting SQL inputs')


def test_gen_domain_support_writes_export_zip(tmp_path: Path) -> None:
    """
    校验代码生成领域支持对象会写出导出压缩包。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    support = GenDomainSupport(GenInfrastructureGateway())
    target_file = tmp_path / 'exports' / 'gen.zip'

    output_path = support.write_export_zip(str(target_file), b'zip-content')

    assert output_path == str(target_file.resolve())
    assert target_file.read_bytes() == b'zip-content'


@pytest.mark.asyncio
async def test_gen_runtime_service_export_code_dry_run_returns_preview_payload() -> None:
    """
    校验代码生成运行时在 dry-run 导出时会返回结构化预览结果。

    :return: None
    """
    gateway = GenInfrastructureGateway()
    service = GenRuntimeService(infrastructure_gateway=gateway)

    def _fake_get_gen_config() -> SimpleNamespace:
        return SimpleNamespace(allow_overwrite=True, GEN_PATH='/tmp/gen')

    object.__setattr__(gateway, 'get_gen_config', _fake_get_gen_config)

    payload = await service.export_code(['sys_user', 'sys_role'], mode='zip', dry_run=True)

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['tableNames'] == ['sys_user', 'sys_role']
    assert payload['outputFile'].endswith('gen_code_sys_user_sys_role.zip')


@pytest.mark.asyncio
async def test_gen_runtime_service_import_tables_requires_at_least_one_table() -> None:
    """
    校验代码生成运行时在未传入表名时会返回参数错误。

    :return: None
    """
    service = GenRuntimeService()

    payload = await service.import_tables([])

    assert payload['ok'] is False
    assert payload['exit_code'] == ARGUMENT_ERROR
    assert payload['message'] == '至少需要传入一个表名'
