from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.role_do import SysRoleDept
from module_admin.entity.vo.dept_vo import *
from utils.time_format_util import list_format_datetime


class DeptDao:
    """
    部门管理模块数据库操作层
    """

    @classmethod
    async def get_dept_by_id(cls, db: AsyncSession, dept_id: int):
        """
        根据部门id获取在用部门信息
        :param db: orm对象
        :param dept_id: 部门id
        :return: 在用部门信息对象
        """
        dept_info = (await db.execute(
            select(SysDept)
                .where(SysDept.dept_id == dept_id,
                       SysDept.status == '0',
                       SysDept.del_flag == '0')
        )).scalars().first()

        return dept_info

    @classmethod
    async def get_dept_by_id_for_list(cls, db: AsyncSession, dept_id: int):
        """
        用于获取部门列表的工具方法
        :param db: orm对象
        :param dept_id: 部门id
        :return: 部门id对应的信息对象
        """
        dept_info = (await db.execute(
            select(SysDept)
                .where(SysDept.dept_id == dept_id,
                       SysDept.del_flag == '0')
        )).scalars().first()

        return dept_info

    @classmethod
    async def get_dept_detail_by_id(cls, db: AsyncSession, dept_id: int):
        """
        根据部门id获取部门详细信息
        :param db: orm对象
        :param dept_id: 部门id
        :return: 部门信息对象
        """
        dept_info = (await db.execute(
            select(SysDept)
                .where(SysDept.dept_id == dept_id,
                       SysDept.del_flag == '0')
        )).scalars().first()

        return dept_info

    @classmethod
    async def get_dept_detail_by_info(cls, db: AsyncSession, dept: DeptModel):
        """
        根据部门参数获取部门信息
        :param db: orm对象
        :param dept: 部门参数对象
        :return: 部门信息对象
        """
        dept_info = (await db.execute(
            select(SysDept)
                .where(SysDept.parent_id == dept.parent_id if dept.parent_id else True,
                       SysDept.dept_name == dept.dept_name if dept.dept_name else True)
        )).scalars().first()

        return dept_info

    @classmethod
    async def get_dept_info_for_edit_option(cls, db: AsyncSession, dept_info: DeptModel, data_scope_sql: str):
        """
        获取部门编辑对应的在用部门列表信息
        :param db: orm对象
        :param dept_info: 部门对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门列表信息
        """
        dept_result = (await db.execute(
            select(SysDept)
                .where(SysDept.dept_id != dept_info.dept_id,
                       SysDept.parent_id != dept_info.dept_id,
                       SysDept.del_flag == '0', SysDept.status == '0',
                       eval(data_scope_sql))
                .order_by(SysDept.order_num)
                .distinct()
        )).scalars().all()

        return list_format_datetime(dept_result)

    @classmethod
    async def get_children_dept(cls, db: AsyncSession, dept_id: int):
        """
        根据部门id查询当前部门的子部门列表信息
        :param db: orm对象
        :param dept_id: 部门id
        :return: 子部门信息列表
        """
        dept_result = (await db.execute(
            select(SysDept)
                .where(SysDept.parent_id == dept_id,
                       SysDept.del_flag == '0')
        )).scalars().all()

        return list_format_datetime(dept_result)

    @classmethod
    async def get_dept_all_ancestors(cls, db: AsyncSession):
        """
        获取所有部门的ancestors信息
        :param db: orm对象
        :return: ancestors信息列表
        """
        ancestors = (await db.execute(
            select(SysDept.ancestors)
                .where(SysDept.del_flag == '0')
        )).scalars().all()

        return ancestors

    @classmethod
    async def get_dept_list_for_tree(cls, db: AsyncSession, dept_info: DeptModel, data_scope_sql: str):
        """
        获取所有在用部门列表信息
        :param db: orm对象
        :param dept_info: 部门对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 在用部门列表信息
        """
        dept_result = (await db.execute(
            select(SysDept)
                .where(SysDept.status == '0',
                       SysDept.del_flag == '0',
                       SysDept.dept_name.like(f'%{dept_info.dept_name}%') if dept_info.dept_name else True,
                       eval(data_scope_sql))
                .order_by(SysDept.order_num)
                .distinct()
        )).scalars().all()

        return dept_result

    @classmethod
    async def get_dept_list(cls, db: AsyncSession, page_object: DeptModel, data_scope_sql: str):
        """
        根据查询参数获取部门列表信息
        :param db: orm对象
        :param page_object: 不分页查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门列表信息对象
        """
        dept_result = (await db.execute(
            select(SysDept)
                .where(SysDept.del_flag == '0',
                       SysDept.status == page_object.status if page_object.status else True,
                       SysDept.dept_name.like(f'%{page_object.dept_name}%') if page_object.dept_name else True,
                       eval(data_scope_sql))
                .order_by(SysDept.order_num)
                .distinct()
        )).scalars().all()

        return dept_result

    @classmethod
    async def add_dept_dao(cls, db: AsyncSession, dept: DeptModel):
        """
        新增部门数据库操作
        :param db: orm对象
        :param dept: 部门对象
        :return: 新增校验结果
        """
        db_dept = SysDept(**dept.model_dump())
        db.add(db_dept)
        await db.flush()

        return db_dept

    @classmethod
    async def edit_dept_dao(cls, db: AsyncSession, dept: dict):
        """
        编辑部门数据库操作
        :param db: orm对象
        :param dept: 需要更新的部门字典
        :return: 编辑校验结果
        """
        await db.execute(
            update(SysDept),
            [dept]
        )

    @classmethod
    async def delete_dept_dao(cls, db: AsyncSession, dept: DeptModel):
        """
        删除部门数据库操作
        :param db: orm对象
        :param dept: 部门对象
        :return:
        """
        await db.execute(
            update(SysDept)
                .where(SysDept.dept_id == dept.dept_id)
                .values(del_flag='2', update_by=dept.update_by, update_time=dept.update_time)
        )
