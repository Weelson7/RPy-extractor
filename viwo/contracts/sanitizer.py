"""Sanitizer rule providers (doc 5.2): the object model core rules and plugin rules share.

A `SanitizerRule` looks at one file (`applies_to` is cheap, `inspect` may read); a `BatchRule`
looks at the whole set (duplicates, renumbering). Rules declare a `cost` and run in cost order;
`inspect` never writes. A plugin's rules come from `EnginePlugin.sanitizer_rules()`, ids
`<plugin id>.<name>`. Findings are plain dicts: {rule, path, message, action, severity, ...}.
A rule whose findings write new files (phase 2 `convert`/`replace`, phase 3 `transcode`) writes
them in `fix` into `ctx.cache`; core commits them into the workspace and journals them.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

WRITES = ("convert", "replace", "transcode")  # actions whose `fix` writes new files


@dataclass
class RuleContext:
    """What a rule may use: the workspace root, the cancel token, nothing else; `cache` is the
    empty folder `fix` writes into (apply only)."""

    workspace: Path
    cancel: object = None
    sink: object = None  # batch rules report their own step through it
    cache: Path | None = None

    def finding(self, rule: str, path: Path, message: str, action: str, **extra) -> dict:
        rel = path.relative_to(self.workspace).as_posix()
        base = {"rule": rule, "path": rel, "message": message, "action": action}
        return {**base, "severity": extra.pop("severity", "warn"), **extra}


class SanitizerRule:
    """Per-file rule. Subclasses set the class attributes and implement `inspect`.
    `default_enabled` rules make the safe recipe; the others run only in a recipe the user
    picks. `lossy` rules rewrite content with loss and are marked so in every recipe."""

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

    def unready(self) -> str:
        """Why this rule cannot act now (its tool or slot is missing), "" when it can: the
        plan says it (never silent)."""
        return ""

    def fix(self, finding: dict, ctx: RuleContext) -> str:
        """For a finding whose action writes (WRITES): write its files into `ctx.cache` and
        return their provenance origin (`decode:<backend>:<path>` for a decoder's copy);
        raise OSError with the reason when it cannot. Trash and rename are core's."""
        raise OSError(f"{self.rule_id} writes nothing")


class BatchRule(SanitizerRule):
    """Rule over the whole file set (dedupe, numbering)."""

    def inspect_all(self, files: list[Path], ctx: RuleContext, earlier: list[dict]) -> list[dict]:
        return []
