from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from config.constant import CommonConstant, MenuConstant
from exceptions.exception import ServiceException, ServiceWarning
from module_admin.dao.menu_dao import MenuDao
from module_admin.dao.role_dao import RoleDao
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.entity.vo.menu_vo import DeleteMenuModel, MenuQueryModel, MenuModel
from module_admin.entity.vo.role_vo import RoleMenuQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from utils.common_util import CamelCaseUtil
from utils.string_util import StringUtil


class MenuService:
    """
    菜单管理模块服务层
    """

    @classmethod
    async def get_menu_tree_services(cls, query_db: AsyncSession, current_user: Optional[CurrentUserModel] = None):
        """
        获取菜单树信息service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :return: 菜单树信息对象
        """
        menu_list_result = await MenuDao.get_menu_list_for_tree(
            query_db, current_user.user.user_id, current_user.user.role
        )
        menu_tree_result = cls.list_to_tree(menu_list_result)

        return menu_tree_result

    @classmethod
    async def get_role_menu_tree_services(
        cls, query_db: AsyncSession, role_id: int, current_user: Optional[CurrentUserModel] = None
    ):
        """
        根据角色id获取菜单树信息service

        :param query_db: orm对象
        :param role_id: 角色id
        :param current_user: 当前用户对象
        :return: 当前角色id的菜单树信息对象
        """
        menu_list_result = await MenuDao.get_menu_list_for_tree(
            query_db, current_user.user.user_id, current_user.user.role
        )
        menu_tree_result = cls.list_to_tree(menu_list_result)
        role = await RoleDao.get_role_detail_by_id(query_db, role_id)
        role_menu_list = await RoleDao.get_role_menu_dao(query_db, role)
        checked_keys = [row.menu_id for row in role_menu_list]
        result = RoleMenuQueryModel(menus=menu_tree_result, checkedKeys=checked_keys)

        return result

    @classmethod
    async def get_menu_list_services(
        cls, query_db: AsyncSession, page_object: MenuQueryModel, current_user: Optional[CurrentUserModel] = None
    ):
        """
        获取菜单列表信息service

        :param query_db: orm对象
        :param page_object: 分页查询参数对象
        :param current_user: 当前用户对象
        :return: 菜单列表信息对象
        """
        menu_list_result = await MenuDao.get_menu_list(
            query_db, page_object, current_user.user.user_id, current_user.user.role
        )

        return CamelCaseUtil.transform_result(menu_list_result)

    @classmethod
    async def check_menu_name_unique_services(cls, query_db: AsyncSession, page_object: MenuModel):
        """
        校验菜单名称是否唯一service

        :param query_db: orm对象
        :param page_object: 菜单对象
        :return: 校验结果
        """
        menu_id = -1 if page_object.menu_id is None else page_object.menu_id
        menu = await MenuDao.get_menu_detail_by_info(query_db, MenuModel(menuName=page_object.menu_name))
        if menu and menu.menu_id != menu_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def add_menu_services(cls, query_db: AsyncSession, page_object: MenuModel):
        """
        新增菜单信息service

        :param query_db: orm对象
        :param page_object: 新增菜单对象
        :return: 新增菜单校验结果
        """
        if not await cls.check_menu_name_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增菜单{page_object.menu_name}失败，菜单名称已存在')
        elif page_object.is_frame == MenuConstant.YES_FRAME and not StringUtil.is_http(page_object.path):
            raise ServiceException(message=f'新增菜单{page_object.menu_name}失败，地址必须以http(s)://开头')
        else:
            try:
                await MenuDao.add_menu_dao(query_db, page_object)
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='新增成功')
            except Exception as e:
                await query_db.rollback()
                raise e

    @classmethod
    async def edit_menu_services(cls, query_db: AsyncSession, page_object: MenuModel):
        """
        编辑菜单信息service

        :param query_db: orm对象
        :param page_object: 编辑部门对象
        :return: 编辑菜单校验结果
        """
        edit_menu = page_object.model_dump(exclude_unset=True)
        menu_info = await cls.menu_detail_services(query_db, page_object.menu_id)
        if menu_info.menu_id:
            if not await cls.check_menu_name_unique_services(query_db, page_object):
                raise ServiceException(message=f'修改菜单{page_object.menu_name}失败，菜单名称已存在')
            elif page_object.is_frame == MenuConstant.YES_FRAME and not StringUtil.is_http(page_object.path):
                raise ServiceException(message=f'修改菜单{page_object.menu_name}失败，地址必须以http(s)://开头')
            elif page_object.menu_id == page_object.parent_id:
                raise ServiceException(message=f'修改菜单{page_object.menu_name}失败，上级菜单不能选择自己')
            else:
                try:
                    await MenuDao.edit_menu_dao(query_db, edit_menu)
                    await query_db.commit()
                    return CrudResponseModel(is_success=True, message='更新成功')
                except Exception as e:
                    await query_db.rollback()
                    raise e
        else:
            raise ServiceException(message='菜单不存在')

    @classmethod
    async def delete_menu_services(cls, query_db: AsyncSession, page_object: DeleteMenuModel):
        """
        删除菜单信息service

        :param query_db: orm对象
        :param page_object: 删除菜单对象
        :return: 删除菜单校验结果
        """
        if page_object.menu_ids:
            menu_id_list = page_object.menu_ids.split(',')
            try:
                for menu_id in menu_id_list:
                    if (await MenuDao.has_child_by_menu_id_dao(query_db, int(menu_id))) > 0:
                        raise ServiceWarning(message='存在子菜单,不允许删除')
                    elif (await MenuDao.check_menu_exist_role_dao(query_db, int(menu_id))) > 0:
                        raise ServiceWarning(message='菜单已分配,不允许删除')
                    await MenuDao.delete_menu_dao(query_db, MenuModel(menuId=menu_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入菜单id为空')

    @classmethod
    async def menu_detail_services(cls, query_db: AsyncSession, menu_id: int):
        """
        获取菜单详细信息service

        :param query_db: orm对象
        :param menu_id: 菜单id
        :return: 菜单id对应的信息
        """
        menu = await MenuDao.get_menu_detail_by_id(query_db, menu_id=menu_id)
        if menu:
            result = MenuModel(**CamelCaseUtil.transform_result(menu))
        else:
            result = MenuModel(**dict())

        return result

    @classmethod
    def list_to_tree(cls, permission_list: list) -> list:
        """
        工具方法：根据菜单列表信息生成树形嵌套数据

        :param permission_list: 菜单列表信息
        :return: 菜单树形嵌套数据
        """
        permission_list = [
            dict(id=item.menu_id, label=item.menu_name, parentId=item.parent_id) for item in permission_list
        ]
        # 转成id为key的字典
        mapping: dict = dict(zip([i['id'] for i in permission_list], permission_list))

        # 树容器
        container: list = []

        for d in permission_list:
            # 如果找不到父级项，则是根节点
            parent: dict = mapping.get(d['parentId'])
            if parent is None:
                container.append(d)
            else:
                children: list = parent.get('children')
                if not children:
                    children = []
                children.append(d)
                parent.update({'children': children})

        return container
