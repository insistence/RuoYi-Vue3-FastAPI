from collections.abc import Iterable, Sequence
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_identity.entity.do.identity_subject_do import SysIdentitySubject
from utils.time_util import TimezoneUtil


class IdentitySubjectDao:
    """
    Identity Subject 数据库操作层
    """

    @classmethod
    async def get_by_user_id(cls, db: AsyncSession, user_id: int) -> SysIdentitySubject | None:
        """
        按用户编号查询 Identity Subject

        :param db: orm对象
        :param user_id: 用户编号
        :return: Identity Subject，不存在时返回 None
        """

        result = await db.execute(select(SysIdentitySubject).where(SysIdentitySubject.user_id == user_id))

        return result.scalars().first()

    @classmethod
    async def get_by_subject_id(cls, db: AsyncSession, subject_id: str) -> SysIdentitySubject | None:
        """
        按主体标识查询 Identity Subject

        :param db: orm对象
        :param subject_id: 主体标识
        :return: Identity Subject，不存在时返回 None
        """

        result = await db.execute(select(SysIdentitySubject).where(SysIdentitySubject.subject_id == subject_id))

        return result.scalars().first()

    @classmethod
    async def list_for_users_for_update(cls, db: AsyncSession, user_ids: Sequence[int]) -> Sequence[SysIdentitySubject]:
        """
        按用户编号锁定查询 Identity Subject

        :param db: orm对象
        :param user_ids: 用户编号序列
        :return: 按用户编号排序的 Identity Subject 序列
        """

        result = await db.execute(
            select(SysIdentitySubject)
            .where(SysIdentitySubject.user_id.in_(user_ids))
            .order_by(SysIdentitySubject.user_id)
            .with_for_update()
        )

        return result.scalars().all()

    @classmethod
    async def create_for_user(
        cls, db: AsyncSession, user_id: int, create_by: str | None = None, subject_id: str | None = None
    ) -> SysIdentitySubject:
        """
        新增用户 Identity Subject

        :param db: orm对象
        :param user_id: 用户编号
        :param create_by: 创建人标识
        :param subject_id: 主体标识
        :return: 新建或已存在的 Identity Subject
        """

        existing = await cls.get_by_user_id(db, user_id)
        if existing is not None:
            return existing
        subject = SysIdentitySubject(
            user_id=user_id,
            subject_id=subject_id or str(uuid4()),
            auth_version=1,
            create_by=create_by,
            create_time=TimezoneUtil.utc_now(),
        )
        try:
            async with db.begin_nested():
                db.add(subject)
                await db.flush()
        except IntegrityError:
            existing = await cls.get_by_user_id(db, user_id)
            if existing is not None:
                return existing
            raise
        return subject

    @classmethod
    async def backfill_for_users(
        cls, db: AsyncSession, user_ids: Iterable[int], create_by: str = 'migration'
    ) -> Sequence[SysIdentitySubject]:
        """
        批量补齐用户 Identity Subject

        :param db: orm对象
        :param user_ids: 用户编号序列
        :param create_by: 创建人标识
        :return: 补齐后的 Identity Subject 序列
        """

        ids = list(dict.fromkeys(user_ids))
        if not ids:
            return []
        result = await db.execute(select(SysIdentitySubject.user_id).where(SysIdentitySubject.user_id.in_(ids)))
        existing = set(result.scalars().all())
        rows: list[SysIdentitySubject] = []
        for user_id in ids:
            if user_id in existing:
                continue
            rows.append(await cls.create_for_user(db, user_id, create_by=create_by))
        return rows

    @classmethod
    async def increment_auth_version(cls, db: AsyncSession, user_id: int, expected_version: int | None = None) -> bool:
        """
        递增单个用户认证版本

        :param db: orm对象
        :param user_id: 用户编号
        :param expected_version: 期望认证版本
        :return: 是否更新成功
        """

        conditions = [SysIdentitySubject.user_id == user_id]
        if expected_version is not None:
            conditions.append(SysIdentitySubject.auth_version == expected_version)
        result = await db.execute(
            update(SysIdentitySubject)
            .where(*conditions)
            .values(auth_version=SysIdentitySubject.auth_version + 1, update_time=TimezoneUtil.utc_now())
        )

        return bool(result.rowcount)

    @classmethod
    async def increment_auth_versions(
        cls, db: AsyncSession, user_ids: Sequence[int], update_by: str, now: datetime | None = None
    ) -> int:
        """
        批量递增用户认证版本

        :param db: orm对象
        :param user_ids: 用户编号序列
        :param update_by: 更新人标识
        :param now: 当前时间
        :return: 成功更新的 Identity Subject 数量
        """

        result = await db.execute(
            update(SysIdentitySubject)
            .where(SysIdentitySubject.user_id.in_(user_ids))
            .values(
                auth_version=SysIdentitySubject.auth_version + 1,
                update_by=update_by,
                update_time=now or TimezoneUtil.utc_now(),
            )
        )
        await db.flush()

        return result.rowcount or 0

    @classmethod
    async def list_missing_user_ids(cls, db: AsyncSession, user_ids: Iterable[int] | None = None) -> list[int]:
        """
        查询缺少 Identity Subject 的用户编号

        :param db: orm对象
        :param user_ids: 用户编号序列
        :return: 缺少 Identity Subject 的用户编号列表
        """

        if user_ids is None:
            result = await db.execute(select(SysUser.user_id).where(SysUser.del_flag == '0'))
            ids = list(result.scalars().all())
        else:
            ids = list(dict.fromkeys(user_ids))
        if not ids:
            return []
        result = await db.execute(select(SysIdentitySubject.user_id).where(SysIdentitySubject.user_id.in_(ids)))
        existing = set(result.scalars().all())

        return [user_id for user_id in ids if user_id not in existing]
