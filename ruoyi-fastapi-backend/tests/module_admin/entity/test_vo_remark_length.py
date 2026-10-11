"""备注字段长度校验测试。

备注列在各表中的真实长度来自 sql/ruoyi-fastapi-pg.sql：
sys_notice.remark 为 varchar(255)，其余业务表的 remark 为 varchar(500)。
超长备注在写库前必须被拦截，否则会在数据库层报错或（MySQL 非严格模式下）被静默截断。
"""

import pytest
from pydantic_validation_decorator import FieldValidationError

from module_admin.entity.vo.config_vo import ConfigModel
from module_admin.entity.vo.dict_vo import DictDataModel, DictTypeModel
from module_admin.entity.vo.job_vo import JobModel
from module_admin.entity.vo.menu_vo import MenuModel
from module_admin.entity.vo.notice_vo import NoticeModel
from module_admin.entity.vo.post_vo import PostModel
from module_admin.entity.vo.role_vo import RoleModel
from module_admin.entity.vo.user_vo import UserModel

# (模型, remark 列长度)
REMARK_LENGTH_CASES = [
    (UserModel, 500),
    (RoleModel, 500),
    (PostModel, 500),
    (MenuModel, 500),
    (ConfigModel, 500),
    (DictTypeModel, 500),
    (DictDataModel, 500),
    (JobModel, 500),
    (NoticeModel, 255),
]


class TestRemarkLengthValidation:
    """备注字段长度校验。"""

    @pytest.mark.parametrize(('model', 'max_length'), REMARK_LENGTH_CASES)
    def test_remark_at_the_column_limit_is_accepted(self, model: type, max_length: int) -> None:
        instance = model(remark='备' * max_length)

        instance.get_remark()

        assert len(instance.remark) == max_length

    @pytest.mark.parametrize(('model', 'max_length'), REMARK_LENGTH_CASES)
    def test_remark_one_past_the_column_limit_is_rejected(self, model: type, max_length: int) -> None:
        instance = model(remark='备' * (max_length + 1))

        with pytest.raises(FieldValidationError):
            instance.get_remark()

    @pytest.mark.parametrize(('model', 'max_length'), REMARK_LENGTH_CASES)
    def test_remark_is_optional(self, model: type, max_length: int) -> None:
        instance = model(remark=None)

        instance.get_remark()

        assert instance.remark is None

    @pytest.mark.parametrize(('model', 'max_length'), REMARK_LENGTH_CASES)
    def test_validate_fields_covers_remark(self, model: type, max_length: int) -> None:
        """validate_fields 是服务层实际调用的入口，它必须覆盖备注字段。"""
        instance = model(remark='备' * (max_length + 1))

        with pytest.raises(FieldValidationError):
            instance.validate_fields()
