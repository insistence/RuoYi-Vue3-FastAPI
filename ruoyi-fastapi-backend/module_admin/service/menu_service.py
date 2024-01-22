from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.entity.vo.role_vo import RoleMenuQueryModel
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.dao.role_dao import RoleDao
from module_admin.dao.menu_dao import *
from utils.common_util import CamelCaseUtil


class MenuService:
    """
    菜单管理模块服务层
    """

    @classmethod
    def get_menu_tree_services(cls, query_db: Session, current_user: Optional[CurrentUserModel] = None):
        """
        获取菜单树信息service
        :param query_db: orm对象
        :param current_user: 当前用户对象
        :return: 菜单树信息对象
        """
        menu_list_result = MenuDao.get_menu_list_for_tree(query_db, current_user.user.user_id, current_user.user.role)
        menu_tree_result = cls.list_to_tree(menu_list_result)

        return menu_tree_result

    @classmethod
    def get_role_menu_tree_services(cls, query_db: Session, role_id: int, current_user: Optional[CurrentUserModel] = None):
        """
        根据角色id获取菜单树信息service
        :param query_db: orm对象
        :param role_id: 角色id
        :param current_user: 当前用户对象
        :return: 当前角色id的菜单树信息对象
        """
        menu_list_result = MenuDao.get_menu_list_for_tree(query_db, current_user.user.user_id, current_user.user.role)
        menu_tree_result = cls.list_to_tree(menu_list_result)
        role_menu_list = RoleDao.get_role_menu_dao(query_db, role_id)
        checked_keys = [row.menu_id for row in role_menu_list]
        result = RoleMenuQueryModel(
            menus=menu_tree_result,
            checkedKeys=checked_keys
        )

        return result

    @classmethod
    def get_menu_list_services(cls, query_db: Session, page_object: MenuQueryModel, current_user: Optional[CurrentUserModel] = None):
        """
        获取菜单列表信息service
        :param query_db: orm对象
        :param page_object: 分页查询参数对象
        :param current_user: 当前用户对象
        :return: 菜单列表信息对象
        """
        menu_list_result = MenuDao.get_menu_list(query_db, page_object, current_user.user.user_id, current_user.user.role)

        return CamelCaseUtil.transform_result(menu_list_result)

    @classmethod
    def add_menu_services(cls, query_db: Session, page_object: MenuModel):
        """
        新增菜单信息service
        :param query_db: orm对象
        :param page_object: 新增菜单对象
        :return: 新增菜单校验结果
        """
        menu = MenuDao.get_menu_detail_by_info(query_db, MenuModel(parentId=page_object.parent_id, menuName=page_object.menu_name, menuType=page_object.menu_type))
        if menu:
            result = dict(is_success=False, message='同一目录下不允许存在同名同类型的菜单')
        else:
            try:
                MenuDao.add_menu_dao(query_db, page_object)
                query_db.commit()
                result = dict(is_success=True, message='新增成功')
            except Exception as e:
                query_db.rollback()
                raise e

        return CrudResponseModel(**result)

    @classmethod
    def edit_menu_services(cls, query_db: Session, page_object: MenuModel):
        """
        编辑菜单信息service
        :param query_db: orm对象
        :param page_object: 编辑部门对象
        :return: 编辑菜单校验结果
        """
        edit_menu = page_object.model_dump(exclude_unset=True)
        menu_info = cls.menu_detail_services(query_db, edit_menu.get('menu_id'))
        if menu_info:
            if menu_info.parent_id != page_object.parent_id or menu_info.menu_name != page_object.menu_name or menu_info.menu_type != page_object.menu_type:
                menu = MenuDao.get_menu_detail_by_info(query_db, MenuModel(parentId=page_object.parent_id, menuName=page_object.menu_name, menuType=page_object.menu_type))
                if menu:
                    result = dict(is_success=False, message='同一目录下不允许存在同名同类型的菜单')
                    return CrudResponseModel(**result)
            try:
                MenuDao.edit_menu_dao(query_db, edit_menu)
                query_db.commit()
                result = dict(is_success=True, message='更新成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='菜单不存在')

        return CrudResponseModel(**result)

    @classmethod
    def delete_menu_services(cls, query_db: Session, page_object: DeleteMenuModel):
        """
        删除菜单信息service
        :param query_db: orm对象
        :param page_object: 删除菜单对象
        :return: 删除菜单校验结果
        """
        if page_object.menu_ids.split(','):
            menu_id_list = page_object.menu_ids.split(',')
            try:
                for menu_id in menu_id_list:
                    MenuDao.delete_menu_dao(query_db, MenuModel(menuId=menu_id))
                query_db.commit()
                result = dict(is_success=True, message='删除成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='传入菜单id为空')
        return CrudResponseModel(**result)

    @classmethod
    def menu_detail_services(cls, query_db: Session, menu_id: int):
        """
        获取菜单详细信息service
        :param query_db: orm对象
        :param menu_id: 菜单id
        :return: 菜单id对应的信息
        """
        menu = MenuDao.get_menu_detail_by_id(query_db, menu_id=menu_id)
        result = MenuModel(**CamelCaseUtil.transform_result(menu))

        return result

    @classmethod
    def list_to_tree(cls, permission_list: list) -> list:
        """
        工具方法：根据菜单列表信息生成树形嵌套数据
        :param permission_list: 菜单列表信息
        :return: 菜单树形嵌套数据
        """
        permission_list = [dict(id=item.menu_id, label=item.menu_name, parentId=item.parent_id) for item in permission_list]
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
