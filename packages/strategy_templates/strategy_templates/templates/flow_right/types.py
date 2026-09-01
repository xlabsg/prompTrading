from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Signal:
    direction: Direction
    timestamp: datetime
    price: float
    strength: float = 1.0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
