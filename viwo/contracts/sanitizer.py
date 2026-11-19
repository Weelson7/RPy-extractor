"""Sanitizer rule providers (doc 5.2): the object model core rules and plugin rules share.

A `SanitizerRule` looks at one file (`applies_to` is cheap, `inspect` may read); a `BatchRule`
looks at the whole set (duplicates). Rules declare a `cost` and run in cost order; `inspect`
never writes. A plugin's rules come from `EnginePlugin.sanitizer_rules()`, ids
`<plugin id>.<name>`. Findings are plain dicts: {rule, path, message, action, severity, ...}.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass
class RuleContext:
    """What a rule may use: the workspace root, the cancel token, nothing else."""

    workspace: Path
    cancel: object = None
    sink: object = None  # batch rules report their own step through it

    def finding(self, rule: str, path: Path, message: str, action: str, **extra) -> dict:
        rel = path.relative_to(self.workspace).as_posix()
        base = {"rule": rule, "path": rel, "message": message, "action": action}
        return {**base, "severity": extra.pop("severity", "warn"), **extra}


class SanitizerRule:
    """Per-file rule. Subclasses set the class attributes and implement `inspect`."""

    rule_id = ""
    owner = "core"
    category = "health"
    default_enabled = True
    lossy = False
    cost = 1  # 1 = header peek .. 10 = transcode

    def dependencies(self) -> Sequence:
        return ()

    def applies_to(self, path: Path) -> bool:
        return True

    def inspect(self, path: Path, ctx: RuleContext) -> list[dict]:
        return []

    def fix(self, finding: dict, ctx: RuleContext) -> None:
        """Phase 1: report-only; core commits trash/rename itself."""


class BatchRule(SanitizerRule):
    """Rule over the whole file set (dedupe, numbering)."""

    def inspect_all(self, files: list[Path], ctx: RuleContext, earlier: list[dict]) -> list[dict]:
        return []
