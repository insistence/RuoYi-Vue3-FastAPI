from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from config.constant import CommonConstant
from exceptions.exception import ServiceException
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.entity.vo.role_vo import (
    AddRoleModel,
    DeleteRoleModel,
    RoleDeptModel,
    RoleDeptQueryModel,
    RoleMenuModel,
    RoleModel,
    RolePageQueryModel,
)
from module_admin.entity.vo.user_vo import UserInfoModel, UserRolePageQueryModel
from module_admin.dao.role_dao import RoleDao
from module_admin.dao.user_dao import UserDao
from utils.common_util import CamelCaseUtil
from utils.excel_util import ExcelUtil
from utils.page_util import PageResponseModel


class RoleService:
    """
    角色管理模块服务层
    """

    @classmethod
    async def get_role_select_option_services(cls, query_db: AsyncSession):
        """
        获取角色列表不分页信息service

        :param query_db: orm对象
        :return: 角色列表不分页信息对象
        """
        role_list_result = await RoleDao.get_role_select_option_dao(query_db)

        return CamelCaseUtil.transform_result(role_list_result)

    @classmethod
    async def get_role_dept_tree_services(cls, query_db: AsyncSession, role_id: int):
        """
        根据角色id获取部门树信息service

        :param query_db: orm对象
        :param role_id: 角色id
        :return: 当前角色id的部门树信息对象
        """
        role = await cls.role_detail_services(query_db, role_id)
        role_dept_list = await RoleDao.get_role_dept_dao(query_db, role)
        checked_keys = [row.dept_id for row in role_dept_list]
        result = RoleDeptQueryModel(checkedKeys=checked_keys)

        return result

    @classmethod
    async def get_role_list_services(
        cls, query_db: AsyncSession, query_object: RolePageQueryModel, data_scope_sql: str, is_page: bool = False
    ):
        """
        获取角色列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 角色列表信息对象
        """
        role_list_result = await RoleDao.get_role_list(query_db, query_object, data_scope_sql, is_page)

        return role_list_result

    @classmethod
    async def check_role_allowed_services(cls, check_role: RoleModel):
        """
        校验角色是否允许操作service

        :param check_role: 角色信息
        :return: 校验结果
        """
        if check_role.admin:
            raise ServiceException(message='不允许操作超级管理员角色')
        else:
            return CrudResponseModel(is_success=True, message='校验通过')

    @classmethod
    async def check_role_data_scope_services(cls, query_db: AsyncSession, role_ids: str, data_scope_sql: str):
        """
        校验角色是否有数据权限service

        :param query_db: orm对象
        :param role_ids: 角色id
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 校验结果
        """
        role_id_list = role_ids.split(',') if role_ids else []
        if role_id_list:
            for role_id in role_id_list:
                roles = await RoleDao.get_role_list(
                    query_db, RolePageQueryModel(roleId=int(role_id)), data_scope_sql, is_page=False
                )
                if roles:
                    continue
                else:
                    raise ServiceException(message='没有权限访问角色数据')

    @classmethod
    async def check_role_name_unique_services(cls, query_db: AsyncSession, page_object: RoleModel):
        """
        校验角色名称是否唯一service

        :param query_db: orm对象
        :param page_object: 角色对象
        :return: 校验结果
        """
        role_id = -1 if page_object.role_id is None else page_object.role_id
        role = await RoleDao.get_role_by_info(query_db, RoleModel(roleName=page_object.role_name))
        if role and role.role_id != role_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def check_role_key_unique_services(cls, query_db: AsyncSession, page_object: RoleModel):
        """
        校验角色权限字符是否唯一service

        :param query_db: orm对象
        :param page_object: 角色对象
        :return: 校验结果
        """
        role_id = -1 if page_object.role_id is None else page_object.role_id
        role = await RoleDao.get_role_by_info(query_db, RoleModel(roleKey=page_object.role_key))
        if role and role.role_id != role_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def add_role_services(cls, query_db: AsyncSession, page_object: AddRoleModel):
        """
        新增角色信息service

        :param query_db: orm对象
        :param page_object: 新增角色对象
        :return: 新增角色校验结果
        """
        add_role = RoleModel(**page_object.model_dump(by_alias=True))
        if not await cls.check_role_name_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增角色{page_object.role_name}失败，角色名称已存在')
        elif not await cls.check_role_key_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增角色{page_object.role_name}失败，角色权限已存在')
        else:
            try:
                add_result = await RoleDao.add_role_dao(query_db, add_role)
                role_id = add_result.role_id
                if page_object.menu_ids:
                    for menu in page_object.menu_ids:
                        await RoleDao.add_role_menu_dao(query_db, RoleMenuModel(roleId=role_id, menuId=menu))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='新增成功')
            except Exception as e:
                await query_db.rollback()
                raise e

    @classmethod
    async def edit_role_services(cls, query_db: AsyncSession, page_object: AddRoleModel):
        """
        编辑角色信息service

        :param query_db: orm对象
        :param page_object: 编辑角色对象
        :return: 编辑角色校验结果
        """
        edit_role = page_object.model_dump(exclude_unset=True, exclude={'admin'})
        if page_object.type != 'status':
            del edit_role['menu_ids']
        if page_object.type == 'status':
            del edit_role['type']
        role_info = await cls.role_detail_services(query_db, edit_role.get('role_id'))
        if role_info:
            if page_object.type != 'status':
                if not await cls.check_role_name_unique_services(query_db, page_object):
                    raise ServiceException(message=f'修改角色{page_object.role_name}失败，角色名称已存在')
                elif not await cls.check_role_key_unique_services(query_db, page_object):
                    raise ServiceException(message=f'修改角色{page_object.role_name}失败，角色权限已存在')
            try:
                await RoleDao.edit_role_dao(query_db, edit_role)
                if page_object.type != 'status':
                    await RoleDao.delete_role_menu_dao(query_db, RoleMenuModel(roleId=page_object.role_id))
                    if page_object.menu_ids:
                        for menu in page_object.menu_ids:
                            await RoleDao.add_role_menu_dao(
                                query_db, RoleMenuModel(roleId=page_object.role_id, menuId=menu)
                            )
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='更新成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='角色不存在')

    @classmethod
    async def role_datascope_services(cls, query_db: AsyncSession, page_object: AddRoleModel):
        """
        分配角色数据权限service

        :param query_db: orm对象
        :param page_object: 角色数据权限对象
        :return: 分配角色数据权限结果
        """
        edit_role = page_object.model_dump(exclude_unset=True, exclude={'admin', 'dept_ids'})
        role_info = await cls.role_detail_services(query_db, page_object.role_id)
        if role_info.role_id:
            try:
                await RoleDao.edit_role_dao(query_db, edit_role)
                await RoleDao.delete_role_dept_dao(query_db, RoleDeptModel(roleId=page_object.role_id))
                if page_object.dept_ids and page_object.data_scope == '2':
                    for dept in page_object.dept_ids:
                        await RoleDao.add_role_dept_dao(
                            query_db, RoleDeptModel(roleId=page_object.role_id, deptId=dept)
                        )
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='分配成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='角色不存在')

    @classmethod
    async def delete_role_services(cls, query_db: AsyncSession, page_object: DeleteRoleModel):
        """
        删除角色信息service

        :param query_db: orm对象
        :param page_object: 删除角色对象
        :return: 删除角色校验结果
        """
        if page_object.role_ids:
            role_id_list = page_object.role_ids.split(',')
            try:
                for role_id in role_id_list:
                    role = await cls.role_detail_services(query_db, int(role_id))
                    if (await RoleDao.count_user_role_dao(query_db, int(role_id))) > 0:
                        raise ServiceException(message=f'角色{role.role_name}已分配,不能删除')
                    role_id_dict = dict(
                        roleId=role_id, updateBy=page_object.update_by, updateTime=page_object.update_time
                    )
                    await RoleDao.delete_role_menu_dao(query_db, RoleMenuModel(**role_id_dict))
                    await RoleDao.delete_role_dept_dao(query_db, RoleDeptModel(**role_id_dict))
                    await RoleDao.delete_role_dao(query_db, RoleModel(**role_id_dict))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入角色id为空')

    @classmethod
    async def role_detail_services(cls, query_db: AsyncSession, role_id: int):
        """
        获取角色详细信息service

        :param query_db: orm对象
        :param role_id: 角色id
        :return: 角色id对应的信息
        """
        role = await RoleDao.get_role_detail_by_id(query_db, role_id=role_id)
        if role:
            result = RoleModel(**CamelCaseUtil.transform_result(role))
        else:
            result = RoleModel(**dict())

        return result

    @staticmethod
    async def export_role_list_services(role_list: List):
        """
        导出角色列表信息service

        :param role_list: 角色信息列表
        :return: 角色列表信息对象
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'roleId': '角色编号',
            'roleName': '角色名称',
            'roleKey': '权限字符',
            'roleSort': '显示顺序',
            'status': '状态',
            'createBy': '创建者',
            'createTime': '创建时间',
            'updateBy': '更新者',
            'updateTime': '更新时间',
            'remark': '备注',
        }

        for item in role_list:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '停用'
        binary_data = ExcelUtil.export_list2excel(role_list, mapping_dict)

        return binary_data

    @classmethod
    async def get_role_user_allocated_list_services(
        cls, query_db: AsyncSession, page_object: UserRolePageQueryModel, data_scope_sql: str, is_page: bool = False
    ):
        """
        根据角色id获取已分配用户列表

        :param query_db: orm对象
        :param page_object: 用户关联角色对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 已分配用户列表
        """
        query_user_list = await UserDao.get_user_role_allocated_list_by_role_id(
            query_db, page_object, data_scope_sql, is_page
        )
        allocated_list = PageResponseModel(
            **{
                **query_user_list.model_dump(by_alias=True),
                'rows': [UserInfoModel(**row) for row in query_user_list.rows],
            }
        )

        return allocated_list

    @classmethod
    async def get_role_user_unallocated_list_services(
        cls, query_db: AsyncSession, page_object: UserRolePageQueryModel, data_scope_sql: str, is_page: bool = False
    ):
        """
        根据角色id获取未分配用户列表

        :param query_db: orm对象
        :param page_object: 用户关联角色对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 未分配用户列表
        """
        query_user_list = await UserDao.get_user_role_unallocated_list_by_role_id(
            query_db, page_object, data_scope_sql, is_page
        )
        unallocated_list = PageResponseModel(
            **{
                **query_user_list.model_dump(by_alias=True),
                'rows': [UserInfoModel(**row) for row in query_user_list.rows],
            }
        )

        return unallocated_list
