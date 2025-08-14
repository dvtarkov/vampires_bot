from dataclasses import dataclass, field
from typing import List, Literal, Optional, Any, Union, Dict
from pydantic import BaseModel, Field

KeyboardType = Literal["inline", "reply"]
RowOrName = Union[str, List[str]]


class KeyboardParams(BaseModel):
    max_in_row: int = 2
    resize_keyboard: bool = True
    one_time_keyboard: bool = False
    is_persistent: bool = False
    selective: bool = False
    input_field_placeholder: str | None = None


class KeyboardSpec(BaseModel):
    type: str
    name: str
    options: List[RowOrName]
    params: KeyboardParams = Field(default_factory=KeyboardParams)
    context: Dict[str, Any] = Field(default_factory=dict)
    button_params: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
