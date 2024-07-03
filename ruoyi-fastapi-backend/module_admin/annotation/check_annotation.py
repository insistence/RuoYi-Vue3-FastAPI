from typing import Optional
from pydantic import BaseModel
from exceptions.exception import FieldValidatorException


class NotBlank:
    """
    字段非空校验装饰器
    """
    def __init__(self, field_name: str, message: Optional[str] = None):
        """
        字段非空校验装饰器
        :param field_name: 需要校验的字段名称
        :param message: 校验失败的提示信息
        :return:
        """
        self.field_name = field_name
        self.message = message

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            check_model = args[0]
            if isinstance(check_model, BaseModel):
                field_value = getattr(check_model, self.field_name)
                if field_value is None or field_value == '' or field_value == [] or field_value == () or field_value == {}:
                    raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}不能为空')
            return func(*args, **kwargs)
        return wrapper


class Size:
    """
    字段大小校验装饰器
    """
    def __init__(self, field_name: str, gt: Optional[float] = None, ge: Optional[float] = None,
                 lt: Optional[float] = None, le: Optional[float] = None, min_length: Optional[int] = 0,
                 max_length: Optional[int] = None, message: Optional[str] = None):
        """
        字段大小校验装饰器
        :param field_name: 需要校验的字段名称
        :param gt: 数字型字段值必须要大于gt
        :param ge: 数字型字段值必须要大于等于ge
        :param lt: 数字型字段值必须要小于ge
        :param le: 数字型字段值必须要小于等于ge
        :param min_length: 字符串型字段长度不能小于min_length
        :param max_length: 字符串型字段长度不能大于max_length
        :param message: 校验失败的提示信息
        :return:
        """
        self.field_name = field_name
        self.gt = gt
        self.ge = ge
        self.lt = lt
        self.le = le
        self.min_length = min_length if min_length >= 0 else 0
        self.max_length = max_length
        self.message = message

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            check_model = args[0]
            if isinstance(check_model, BaseModel):
                field_value = getattr(check_model, self.field_name)
                if isinstance(field_value, float):
                    if self.gt is not None and field_value <= self.gt:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}必须大于{self.gt}')
                    elif self.ge is not None and field_value < self.ge:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}必须大于等于{self.ge}')
                    elif self.lt is not None and field_value >= self.lt:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}必须小于{self.lt}')
                    elif self.le is not None and field_value > self.le:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}必须小于等于{self.le}')
                elif isinstance(field_value, str):
                    if len(field_value) < self.min_length:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}长度不能小于{self.min_length}')
                    elif self.max_length is not None and len(field_value) > self.max_length:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}长度不能大于{self.max_length}')
            return func(*args, **kwargs)
        return wrapper
