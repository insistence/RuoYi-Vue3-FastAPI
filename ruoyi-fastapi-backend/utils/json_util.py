import json
from datetime import datetime
from typing import Any


# 1. 自定义 JSONEncoder
class ComplexEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        # 处理 datetime 对象
        if isinstance(obj, datetime):
            return obj.isoformat()

        # 处理自定义类对象
        if hasattr(obj, '__dict__'):
            # 获取对象的字典表示，递归处理嵌套对象
            result = {}
            for key, value in obj.__dict__.items():
                # 过滤掉以 _ 开头的私有属性
                if not key.startswith('_'):
                    # 递归调用 default 处理嵌套对象
                    if isinstance(value, (datetime,)):
                        result[key] = self.default(value)
                    else:
                        result[key] = value
            return result

        # 处理 dataclass
        if hasattr(obj, '__dataclass_fields__'):
            return {field: self.default(getattr(obj, field)) for field in obj.__dataclass_fields__}

        # 让基类处理其他类型
        return super().default(obj)
