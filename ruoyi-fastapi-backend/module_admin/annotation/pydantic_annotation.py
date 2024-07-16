import inspect
from fastapi import Form, Query
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from typing import Type


def as_query(cls: Type[BaseModel]):
    """
    pydantic模型查询参数装饰器，将pydantic模型用于接收查询参数
    """
    new_parameters = []

    for field_name, model_field in cls.model_fields.items():
        model_field: FieldInfo  # type: ignore

        if not model_field.is_required():
            new_parameters.append(
                inspect.Parameter(
                    model_field.alias,
                    inspect.Parameter.POSITIONAL_ONLY,
                    default=Query(default=model_field.default, description=model_field.description),
                    annotation=model_field.annotation,
                )
            )
        else:
            new_parameters.append(
                inspect.Parameter(
                    model_field.alias,
                    inspect.Parameter.POSITIONAL_ONLY,
                    default=Query(..., description=model_field.description),
                    annotation=model_field.annotation,
                )
            )

    async def as_query_func(**data):
        return cls(**data)

    sig = inspect.signature(as_query_func)
    sig = sig.replace(parameters=new_parameters)
    as_query_func.__signature__ = sig  # type: ignore
    setattr(cls, 'as_query', as_query_func)
    return cls


def as_form(cls: Type[BaseModel]):
    """
    pydantic模型表单参数装饰器，将pydantic模型用于接收表单参数
    """
    new_parameters = []

    for field_name, model_field in cls.model_fields.items():
        model_field: FieldInfo  # type: ignore

        if not model_field.is_required():
            new_parameters.append(
                inspect.Parameter(
                    model_field.alias,
                    inspect.Parameter.POSITIONAL_ONLY,
                    default=Form(default=model_field.default, description=model_field.description),
                    annotation=model_field.annotation,
                )
            )
        else:
            new_parameters.append(
                inspect.Parameter(
                    model_field.alias,
                    inspect.Parameter.POSITIONAL_ONLY,
                    default=Form(..., description=model_field.description),
                    annotation=model_field.annotation,
                )
            )

    async def as_form_func(**data):
        return cls(**data)

    sig = inspect.signature(as_form_func)
    sig = sig.replace(parameters=new_parameters)
    as_form_func.__signature__ = sig  # type: ignore
    setattr(cls, 'as_form', as_form_func)
    return cls
