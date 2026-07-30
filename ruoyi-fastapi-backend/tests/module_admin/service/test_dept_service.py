from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from config.database import Base
from exceptions.exception import ServiceException
from module_admin.dao.dept_dao import DeptDao
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.vo.dept_vo import DeptSortModel
from module_admin.service.dept_service import DeptService


async def _create_dept_table() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysDept.__table__])
    return engine, session_maker


def test_parse_dept_sort_items_preserves_corresponding_order_values() -> None:
    result = DeptService.parse_dept_sort_items(DeptSortModel(deptIds='101, 102', orderNums='3, 1'))

    assert result == [
        {'dept_id': 101, 'order_num': 3},
        {'dept_id': 102, 'order_num': 1},
    ]


@pytest.mark.parametrize(
    ('dept_ids', 'order_nums'),
    [
        ('101,102', '1'),
        ('101,101', '1,2'),
        ('101,invalid', '1,2'),
        ('101,102', '1,-1'),
        ('', ''),
    ],
)
def test_parse_dept_sort_items_rejects_invalid_parameters(dept_ids: str, order_nums: str) -> None:
    with pytest.raises(ServiceException) as exc_info:
        DeptService.parse_dept_sort_items(DeptSortModel(deptIds=dept_ids, orderNums=order_nums))

    assert exc_info.value.message == '部门排序参数不正确'


@pytest.mark.asyncio
async def test_update_dept_sort_updates_all_rows_in_one_transaction() -> None:
    engine, session_maker = await _create_dept_table()
    try:
        async with session_maker() as session:
            session.add_all(
                [
                    SysDept(dept_id=101, dept_name='研发部门', order_num=1),
                    SysDept(dept_id=102, dept_name='测试部门', order_num=2),
                ]
            )
            await session.commit()

            result = await DeptService.update_dept_sort_services(
                session,
                DeptSortModel(deptIds='101,102', orderNums='5,4'),
            )
            rows = (await session.execute(select(SysDept.dept_id, SysDept.order_num).order_by(SysDept.dept_id))).all()

        assert result.is_success is True
        assert rows == [(101, 5), (102, 4)]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_dept_sort_rolls_back_and_wraps_database_error() -> None:
    query_db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    with (
        patch.object(DeptDao, 'update_dept_sort_dao', AsyncMock(side_effect=RuntimeError('database error'))),
        pytest.raises(ServiceException) as exc_info,
    ):
        await DeptService.update_dept_sort_services(
            query_db,
            DeptSortModel(deptIds='101', orderNums='2'),
        )

    assert exc_info.value.message == '保存排序异常，请联系管理员'
    query_db.commit.assert_not_awaited()
    query_db.rollback.assert_awaited_once()
