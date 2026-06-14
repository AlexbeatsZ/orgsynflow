from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AdapterCapability:
    name: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
        }


@dataclass(frozen=True)
class AdapterStatus:
    name: str
    display_name: str
    available: bool
    status: str
    reason: str | None
    capabilities: list[AdapterCapability]
    source: str
    confidence: str = "detected"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "available": self.available,
            "status": self.status,
            "reason": self.reason,
            "capabilities": [capability.as_dict() for capability in self.capabilities],
            "source": self.source,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


class Adapter(Protocol):
    name: str
    display_name: str
    capabilities: list[AdapterCapability]
    source: str

    def check_status(self) -> AdapterStatus:
        ...
