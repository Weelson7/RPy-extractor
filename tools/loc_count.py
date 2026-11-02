"""Count non-blank, non-comment lines and enforce loc_caps.ini (contract doc 15).

Usage: python tools/loc_count.py [--report]   (exit 1 when a cap is exceeded)
Docstrings are excluded; code must be ruff-formatted (line length 100) first.
"""

from __future__ import annotations

import ast
import configparser
import io
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
_SKIP |= {tokenize.ENCODING, tokenize.ENDMARKER}


def _docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        kinds = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        if isinstance(node, kinds) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def counted_lines(source: str) -> tuple[set[int], ast.AST]:
    lines: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type not in _SKIP:
            lines.update(range(tok.start[0], tok.end[0] + 1))
    tree = ast.parse(source)
    return lines - _docstring_lines(tree), tree


def _span(lines: set[int], node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None) or node.lineno
    return len([n for n in lines if node.lineno <= n <= end])


def check_python(path: Path, caps: dict[str, int], test: bool) -> tuple[int, list[str]]:
    source = path.read_text(encoding="utf-8-sig")
    lines, tree = counted_lines(source)
    rel = path.relative_to(ROOT).as_posix()
    problems: list[str] = []
    file_cap = caps["test_file"] if test else caps["file"]
    if "/contracts/" in f"/{rel}" and not test:
        file_cap = caps["contracts_file"]
    if len(lines) > file_cap:
        problems.append(f"{rel}: {len(lines)} LoC > file cap {file_cap}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            size, cap = _span(lines, node), caps["test_function" if test else "function"]
            if size > cap:
                problems.append(f"{rel}:{node.lineno} {node.name}() {size} LoC > {cap}")
            args = node.args
            params = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
            params = [a for a in params if a not in {"self", "cls"}]
            if not test and len(params) > caps["params"]:
                problems.append(f"{rel}:{node.lineno} {node.name}() has {len(params)} params")
        elif isinstance(node, ast.ClassDef) and _span(lines, node) > caps["class"]:
            problems.append(f"{rel}:{node.lineno} class {node.name} > {caps['class']} LoC")
    for number, text in enumerate(source.splitlines(), 1):
        if len(text) > caps["line_length"]:
            problems.append(f"{rel}:{number} line longer than {caps['line_length']}")
    return len(lines), problems


def _web_lines(path: Path) -> int:
    lines = [s.strip() for s in path.read_text(encoding="utf-8").splitlines()]
    return len([s for s in lines if s and not s.startswith(("//", "/*", "*", "<!--"))])


def check_web(cfg: configparser.ConfigParser, report: bool) -> list[str]:
    """Web UI: per-file cap for JS and a total budget for js/css/html."""
    problems, total = [], 0
    for rel, budget in cfg["web"].items():
        if rel == "js_file":
            continue
        for path in sorted((ROOT / rel).rglob("*")):
            if path.suffix in {".js", ".css", ".html"}:
                count = _web_lines(path)
                total += count
                if path.suffix == ".js" and count > int(cfg["web"]["js_file"]):
                    problems.append(f"{path.relative_to(ROOT).as_posix()}: {count} LoC > JS cap")
        if report:
            print(f"{total:6d} / {int(budget):6d}  {rel} (web)")
        if total > int(budget):
            problems.append(f"web budget {rel}: {total} LoC > {budget}")
    return problems


def run(report: bool) -> int:
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.optionxform = str  # type: ignore[assignment,method-assign]  # keep path case
    cfg.read(ROOT / "loc_caps.ini", encoding="utf-8")
    caps = {k: int(v) for k, v in cfg["caps"].items()}
    budgets = {k: int(v) for k, v in cfg["budgets"].items()}
    totals: dict[str, int] = {k: 0 for k in budgets}
    problems: list[str] = []
    for top in ("viwo", "tests", "tools"):
        for path in sorted((ROOT / top).rglob("*.py")):
            count, found = check_python(path, caps, test=top == "tests")
            problems += found
            rel = path.relative_to(ROOT).as_posix()
            for prefix in budgets:
                if rel == prefix or rel.startswith(prefix.rstrip("/") + "/"):
                    totals[prefix] += count
    for prefix, total in totals.items():
        if total > budgets[prefix]:
            problems.append(f"budget {prefix}: {total} LoC > {budgets[prefix]}")
    if report:
        for prefix, total in sorted(totals.items()):
            print(f"{total:6d} / {budgets[prefix]:6d}  {prefix}")
    problems += check_web(cfg, report)
    for problem in problems:
        print(f"CAP: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(run("--report" in sys.argv))
