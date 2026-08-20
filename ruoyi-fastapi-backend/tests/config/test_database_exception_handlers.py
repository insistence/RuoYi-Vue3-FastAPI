import json

import pytest
from fastapi import FastAPI, status

from common.constant import HttpStatusConstant
from exceptions.exception import (
    DataSourceInitializationException,
    DataSourceNotFoundException,
    DataSourceUnavailableException,
    ServiceException,
)
from exceptions.handle import handle_exception


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'exception',
    [
        DataSourceUnavailableException('reporting'),
        DataSourceInitializationException('reporting'),
        DataSourceNotFoundException('reporting'),
    ],
)
async def test_data_source_exceptions_use_service_exception_handler(exception: Exception) -> None:
    app = FastAPI()
    handle_exception(app)

    handler = app.exception_handlers[ServiceException]
    response = await handler(None, exception)
    payload = json.loads(response.body)

    assert response.status_code == status.HTTP_200_OK
    assert payload['code'] == HttpStatusConstant.ERROR
    assert payload['success'] is False
    assert 'reporting' in payload['msg']
    assert '://' not in payload['msg']
