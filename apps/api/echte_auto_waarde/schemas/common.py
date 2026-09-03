"""Shared schema configuration.

API field names are camelCase so the TypeScript frontend consumes them without a
translation layer, while Python keeps snake_case internally. Money always
travels as integer cents in EUR; formatting is a frontend concern.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
