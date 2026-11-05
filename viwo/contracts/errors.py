"""Error taxonomy and the result envelope (doc 12.3b)."""

from dataclasses import dataclass, field
from typing import Any

CODES = tuple(
    "invalid_request not_found busy unavailable needs_key needs_decision failed cancelled "
    "refused offline internal".split()
)


class ViwoError(Exception):
    """Expected failure with a stable code; `owner` is "core", a plugin or a backend id."""

    def __init__(self, code: str, message: str, owner: str = "core", hint: str = "") -> None:
        if code not in CODES:
            raise ValueError(f"unknown error code: {code}")
        super().__init__(message)
        self.code, self.message, self.owner, self.hint = code, message, owner, hint

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "owner": self.owner, "hint": self.hint}


@dataclass
class Envelope:
    ok: bool
    data: Any = None
    error: dict[str, str] | None = None
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def success(cls, data: Any, warnings: list[str] | None = None) -> "Envelope":
        return cls(True, data, None, list(warnings or []))

    @classmethod
    def failure(cls, err: ViwoError) -> "Envelope":
        return cls(False, None, err.to_dict(), [])

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error, "warnings": self.warnings}
