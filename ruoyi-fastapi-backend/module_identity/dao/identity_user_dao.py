from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.role_do import SysRole
from module_admin.entity.do.user_do import SysUser, SysUserRole


class IdentityUserDao:
    """
    Identity User 数据库操作层
    """

    @classmethod
    async def get_active_user(cls, db: AsyncSession, user_id: int) -> SysUser | None:
        """
        按用户编号查询活跃用户

        :param db: orm对象
        :param user_id: 用户编号
        :return: SysUser，不存在时返回 None
        """

        result = await db.execute(
            select(SysUser).where(SysUser.status == '0', SysUser.del_flag == '0', SysUser.user_id == user_id)
        )

        return result.scalars().first()

    @classmethod
    async def get_user(cls, db: AsyncSession, user_id: int) -> SysUser | None:
        """
        按用户编号查询用户

        :param db: orm对象
        :param user_id: 用户编号
        :return: SysUser，不存在时返回 None
        """

        return await db.scalar(select(SysUser).where(SysUser.user_id == user_id))

    @classmethod
    async def list_user_ids_by_role_id(cls, db: AsyncSession, role_id: int) -> list[int]:
        """
        按角色编号查询用户编号

        :param db: orm对象
        :param role_id: 角色编号
        :return: 用户编号列表
        """

        result = await db.execute(
            select(SysUserRole.user_id).where(SysUserRole.role_id == role_id).order_by(SysUserRole.user_id)
        )

        return list(result.scalars().all())

    @classmethod
    async def get_claim_attributes(cls, db: AsyncSession, user_id: int) -> tuple[list[str], SysDept | None]:
        """
        查询用户声明属性和部门

        :param db: orm对象
        :param user_id: 用户编号
        :return: 声明名称列表和 SysDept，部门不存在时为 None
        """

        role_result = await db.execute(
            select(SysRole.role_key)
            .join(SysUserRole, SysUserRole.role_id == SysRole.role_id)
            .where(SysUserRole.user_id == user_id, SysRole.status == '0', SysRole.del_flag == '0')
            .order_by(SysRole.role_id)
        )
        dept_result = await db.execute(
            select(SysDept)
            .join(SysUser, SysUser.dept_id == SysDept.dept_id)
            .where(SysUser.user_id == user_id, SysDept.status == '0', SysDept.del_flag == '0')
        )

        return list(role_result.scalars().all()), dept_result.scalars().first()
