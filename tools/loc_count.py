"""Count non-blank, non-comment lines and enforce loc_caps.ini (contract doc 15).

Usage: python tools/loc_count.py [--report]   (exit 1 when a cap is exceeded)
Docstrings are excluded; code must be ruff-formatted (line length 100) first.
The caps file is read and validated by tools/caps_ini.py (exceptions, expiry, schema).
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import caps_ini  # noqa: E402

_SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
_SKIP |= {tokenize.ENCODING, tokenize.ENDMARKER}
TEST_FLOOR = 0.6  # doc 15.4: test LoC >= 0.6 x (contracts + core)


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


def check_python(path: Path, caps: caps_ini.Caps, test: bool) -> tuple[int, list[str]]:
    source = path.read_text(encoding="utf-8-sig")
    lines, tree = counted_lines(source)
    rel = path.relative_to(ROOT).as_posix()
    problems: list[str] = []
    c = caps.caps
    file_cap = c["test_file"] if test else c["file"]
    if "/contracts/" in f"/{rel}" and not test:
        file_cap = c["contracts_file"]
    file_cap = caps.file_cap(rel, file_cap)
    if len(lines) > file_cap:
        problems.append(f"{rel}: {len(lines)} LoC > file cap {file_cap}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            size, cap = _span(lines, node), c["test_function" if test else "function"]
            if size > cap:
                problems.append(f"{rel}:{node.lineno} {node.name}() {size} LoC > {cap}")
            args = node.args
            params = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
            params = [a for a in params if a not in {"self", "cls"}]
            if not test and len(params) > c["params"]:
                problems.append(f"{rel}:{node.lineno} {node.name}() has {len(params)} params")
        elif isinstance(node, ast.ClassDef) and _span(lines, node) > c["class"]:
            problems.append(f"{rel}:{node.lineno} class {node.name} > {c['class']} LoC")
    for number, text in enumerate(source.splitlines(), 1):
        if len(text) > c["line_length"]:
            problems.append(f"{rel}:{number} line longer than {c['line_length']}")
    return len(lines), problems


def _web_lines(path: Path) -> int:
    lines = [s.strip() for s in path.read_text(encoding="utf-8").splitlines()]
    return len([s for s in lines if s and not s.startswith(("//", "/*", "*", "<!--"))])


def check_web(web: dict[str, int], report: bool) -> list[str]:
    """Web UI: per-file cap for JS and a total budget for js/css/html."""
    problems, total = [], 0
    for rel, budget in web.items():
        if rel == "js_file":
            continue
        for path in sorted((ROOT / rel).rglob("*")):
            if path.suffix in {".js", ".css", ".html"}:
                count = _web_lines(path)
                total += count
                if path.suffix == ".js" and count > web["js_file"]:
                    problems.append(f"{path.relative_to(ROOT).as_posix()}: {count} LoC > JS cap")
        if report:
            print(f"{total:6d} / {budget:6d}  {rel} (web)")
        if total > budget:
            problems.append(f"web budget {rel}: {total} LoC > {budget}")
    return problems


def run(report: bool) -> int:
    from viwo import __version__

    caps = caps_ini.load(ROOT / "loc_caps.ini", __version__)
    problems = list(caps.problems)
    if problems:
        print("\n".join(f"CAP: {p}" for p in problems))
        return 1
    totals: dict[str, int] = {k: 0 for k in caps.budgets}
    tests = 0
    for top in ("viwo", "tests", "tools"):
        for path in sorted((ROOT / top).rglob("*.py")):
            count, found = check_python(path, caps, test=top == "tests")
            problems += found
            tests += count if top == "tests" else 0
            rel = path.relative_to(ROOT).as_posix()
            for prefix in caps.budgets:
                if rel == prefix or rel.startswith(prefix.rstrip("/") + "/"):
                    totals[prefix] += count
    for prefix, total in totals.items():
        if total > caps.budgets[prefix]:
            problems.append(f"budget {prefix}: {total} LoC > {caps.budgets[prefix]}")
    floor = TEST_FLOOR * (totals.get("viwo/contracts", 0) + totals.get("viwo/core", 0))
    if tests < floor:
        problems.append(f"tests: {tests} LoC < floor {floor:.0f} (0.6 x contracts+core)")
    if report:
        for prefix, total in sorted(totals.items()):
            print(f"{total:6d} / {caps.budgets[prefix]:6d}  {prefix}")
        print(f"{tests:6d} / {floor:6.0f}  tests (floor)")
    problems += check_web(caps.web, report)
    for problem in problems:
        print(f"CAP: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(run("--report" in sys.argv))
