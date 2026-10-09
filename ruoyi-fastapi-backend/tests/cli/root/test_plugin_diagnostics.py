from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cli.groups.plugin.payload import PluginCommandPayloadAdapter
from cli.groups.plugin.presenter import PluginCommandPresenter
from cli.runtime.plugin.service import CliPluginRuntimeService


@pytest.mark.asyncio
async def test_cli_diagnose_appends_runtime_without_changing_static_result(monkeypatch: pytest.MonkeyPatch) -> None:
    read = AsyncMock(return_value={'state': 'unavailable', 'observedTotals': None})
    monkeypatch.setattr('plugins.core.runtime.diagnostics_query.read_cli_runtime_diagnostics', read)
    runtime = CliPluginRuntimeService(runtime_environment=SimpleNamespace(get_backend_dir=lambda: '/backend'))
    runtime._core_runtime = SimpleNamespace(diagnose_plugin=AsyncMock(return_value={'ok': True, 'info': {'x': 1}}))
    payload = await runtime.diagnose_plugin_with_runtime('demo')
    assert payload['ok'] is True and payload['info'] == {'x': 1}
    assert payload['runtime']['state'] == 'unavailable'
    read.assert_awaited_once_with('demo', backend_root=Path('/backend'))


def test_runtime_shared_contract_and_unknown_text_are_preserved() -> None:
    payload = {
        'ok': True,
        'runtime': {
            'state': 'partial',
            'scope': 'reporting_workers',
            'observedWorkers': 0,
            'expectedWorkers': 1,
            'missingWorkers': 1,
            'staleSnapshots': 1,
            'invalidSnapshots': 0,
            'sampleTtlSeconds': 60,
            'release': {'summary': {'pluginId': 'demo', 'status': 'pending_restart', 'enabled': True}},
            'workers': [{'workerId': 'a' * 32, 'freshness': 'stale', 'observation': 'stale', 'actual': None}],
        },
    }
    adapted = PluginCommandPayloadAdapter.adapt(payload)
    assert adapted['runtime'] == payload['runtime']
    text = PluginCommandPresenter().build_diagnose_text(adapted)
    assert 'runtime_state: partial' in text and 'freshness=stale' in text
    assert 'jobs=unknown' in text and 'sse=unknown' in text and 'websocket=unknown' in text
    assert 'ready=unknown' in text and 'worker_pending_cleanup=unknown' in text
    assert 'jobs=0' not in text
