from dataclasses import dataclass, field
from typing import List, Literal, Optional, Any, Union

KeyboardType = Literal["inline", "reply"]
RowOrName = Union[str, List[str]]

@dataclass
class KeyboardParams:
    max_in_row: int = 3
    resize_keyboard: bool = True
    one_time_keyboard: bool = False
    is_persistent: bool = False
    selective: bool = False
    input_field_placeholder: Optional[str] = None

@dataclass
class KeyboardSpec:
    type: KeyboardType
    name: str
    options: List[RowOrName]                  # <-- поддержка вложенных рядов
    params: KeyboardParams = field(default_factory=KeyboardParams)
    context: dict[str, Any] = field(default_factory=dict)
