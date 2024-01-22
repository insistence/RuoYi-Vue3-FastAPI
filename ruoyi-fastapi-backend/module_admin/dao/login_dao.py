from sqlalchemy.orm import Session
from sqlalchemy import and_
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.do.dept_do import SysDept


def login_by_account(db: Session, user_name: str):
    """
    根据用户名查询用户信息
    :param db: orm对象
    :param user_name: 用户名
    :return: 用户对象
    """
    user = db.query(SysUser, SysDept)\
        .filter(SysUser.user_name == user_name, SysUser.del_flag == '0') \
        .outerjoin(SysDept, and_(SysUser.dept_id == SysDept.dept_id, SysDept.status == 0, SysDept.del_flag == 0)) \
        .distinct() \
        .first()

    return user
