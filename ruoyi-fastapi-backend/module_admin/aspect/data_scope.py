from fastapi import Depends
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService
from typing import Optional


class GetDataScope:
    """
    获取当前用户数据权限对应的查询sql语句
    """
    def __init__(self, query_alias: Optional[str] = '', db_alias: Optional[str] = 'db', user_alias: Optional[str] = 'user_id', dept_alias: Optional[str] = 'dept_id'):
        self.query_alias = query_alias
        self.db_alias = db_alias
        self.user_alias = user_alias
        self.dept_alias = dept_alias

    def __call__(self, current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
        user_id = current_user.user.user_id
        dept_id = current_user.user.dept_id
        role_datascope_list = [dict(role_id=item.role_id, data_scope=int(item.data_scope)) for item in current_user.user.role]
        max_data_scope_dict = min(role_datascope_list, key=lambda x: x['data_scope'])
        max_role_id = max_data_scope_dict['role_id']
        max_data_scope = max_data_scope_dict['data_scope']
        if self.query_alias == '' or max_data_scope == 1 or user_id == 1:
            param_sql = '1 == 1'
        elif max_data_scope == 2:
            param_sql = f"{self.query_alias}.{self.dept_alias}.in_({self.db_alias}.query(SysRoleDept.dept_id).filter(SysRoleDept.role_id == {max_role_id})) if hasattr({self.query_alias}, '{self.dept_alias}') else 1 == 1"
        elif max_data_scope == 3:
            param_sql = f"{self.query_alias}.{self.dept_alias} == {dept_id} if hasattr({self.query_alias}, '{self.dept_alias}') else 1 == 1"
        elif max_data_scope == 4:
            param_sql = f"{self.query_alias}.{self.dept_alias}.in_({self.db_alias}.query(SysDept.dept_id).filter(or_(SysDept.dept_id == {dept_id}, func.find_in_set({dept_id}, SysDept.ancestors)))) if hasattr({self.query_alias}, '{self.dept_alias}') else 1 == 1"
        elif max_data_scope == 5:
            param_sql = f"{self.query_alias}.{self.user_alias} == {user_id} if hasattr({self.query_alias}, '{self.user_alias}') else 1 == 1"
        else:
            param_sql = '1 == 0'

        return param_sql
