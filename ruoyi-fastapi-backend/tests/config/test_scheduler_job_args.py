import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from config.get_scheduler import SchedulerUtil  # noqa: E402


def test_scheduler_job_args_parse_json_array_without_splitting_commas() -> None:
    """
    校验 JSON 格式位置参数可保留参数内部逗号。

    :return: None
    """
    assert SchedulerUtil._parse_job_args('["tenant,a", "dry-run"]') == ['tenant,a', 'dry-run']


def test_scheduler_job_args_parse_legacy_comma_separated_value() -> None:
    """
    校验旧逗号分隔格式仍保持兼容。

    :return: None
    """
    assert SchedulerUtil._parse_job_args('tenant,dry-run') == ['tenant', 'dry-run']


def test_scheduler_job_args_dump_json_array() -> None:
    """
    校验调度器日志位置参数使用 JSON 数组格式。

    :return: None
    """
    assert SchedulerUtil._dump_job_args(('tenant,a', 'dry-run')) == '["tenant,a", "dry-run"]'
