"""Status presentation as a PDF: project state, the sqc suite, the CTF flags, real-game
evidence and the night's commits. The markup is `tools/status_template.html`; this fills it and
Edge headless prints it (`--print-to-pdf`). The HTML stays next to the PDF.

Usage: python tools/status_pdf.py [--out viwo-data/status/ViWo-status.pdf] [--tests LOG]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from viwo import CONTRACT_VERSION, __version__  # noqa: E402
from viwo.core.wiring.registry import BUILTIN_PLUGINS, load_plugin  # noqa: E402

TEMPLATE = Path(__file__).with_name("status_template.html")
EDGE = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


def esc(text) -> str:
    return html.escape(str(text))


def cell(*values) -> str:
    return "<tr>" + "".join(f"<td>{v}</td>" for v in values) + "</tr>"


def verdict(ok) -> str:
    if ok is None:
        return "<span class='sub'>n/a</span>"
    return "<span class='pass'>PASS</span>" if ok else "<span class='fail'>FAIL</span>"


def report(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["games"] if isinstance(data, dict) and "games" in data else data


def flag_rows(records: list[dict]) -> str:
    rows = []
    for r in records:
        for f in r.get("flags", []):
            check = f.get("glob") or f"warning: {f.get('warning')!r}"
            found = f.get("found", 0)
            rows.append(
                cell(
                    esc(r["game"]),
                    esc(f["name"]),
                    f"<code>{esc(check)}</code>",
                    found,
                    verdict(f["ok"]),
                )
            )
    return "\n".join(rows)


def game_rows(records: list[dict]) -> str:
    rows = []
    for r in records:
        ex = r.get("extract") or {}
        top = max(r.get("detection", {}).items(), key=lambda kv: kv[1], default=("none", 0))
        flags = r.get("flags", [])
        decided = [f for f in flags if f["ok"] is not None]
        counts = f"{sum(1 for f in decided if f['ok'])}/{len(flags)}" if flags else "-"
        archives = f"{ex.get('archivesExtracted', '-')}/{ex.get('archivesFound', '-')}"
        unchanged = "yes" if r.get("gameUnchanged") else "NO"
        rows.append(
            cell(
                esc(r["game"]),
                f"{esc(top[0])} {top[1]:.0%}",
                ex.get("copied", "-"),
                archives,
                unchanged,
                counts,
                verdict(r["ok"]),
            )
        )
    return "\n".join(rows)


def sqc_rows() -> str:
    rows = []
    for path in sorted((ROOT / "sqc").glob("[0-9]*.md")):
        text = path.read_text(encoding="utf-8")
        ids = re.findall(r"^## (SQC-[A-Z]+-\d+) \((P\d)\)", text, re.M)
        title = text.splitlines()[0].lstrip("# ").strip()
        rows.append(
            cell(
                f"<code>{esc(path.name)}</code>",
                esc(title),
                len(ids),
                sum(1 for _, p in ids if p == "P0"),
            )
        )
    return "\n".join(rows)


def plugin_rows() -> str:
    rows = []
    for pid, entry in sorted(BUILTIN_PLUGINS.items()):
        plugin = load_plugin(entry)
        slots = ", ".join(s.slot_id for s in plugin.slot_definitions()) or "-"
        rows.append(
            cell(f"<code>{pid}</code>", esc(plugin.manifest.name), f"<code>{esc(slots)}</code>")
        )
    return "\n".join(rows)


def values(test_log: str) -> dict[str, str]:
    shipped = report(ROOT / "viwo-data" / "integration" / "report.json")
    passes: list[dict] = []
    for folder in sorted((ROOT / "viwo-data" / "games-pass").glob("pass-*")):
        passes += report(folder / "report.json")
    log = subprocess.run(
        ["git", "log", "--oneline", "v1.2.1..HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    commits = [line for line in log.splitlines() if line]
    loc = subprocess.run(
        [sys.executable, "tools/loc_count.py", "--report"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    product = re.search(r"\s(\d+) /\s+(\d+)\s+viwo\n", loc)
    tests = re.search(r"Ran (\d+) tests", test_log)
    flags = [f for r in shipped + passes for f in r.get("flags", [])]
    return {
        "version": __version__,
        "contract": CONTRACT_VERSION,
        "date": date.today().isoformat(),
        "plugin_count": str(len(BUILTIN_PLUGINS)),
        "test_count": tests.group(1) if tests else "?",
        "loc": product.group(1) if product else "?",
        "loc_cap": product.group(2) if product else "?",
        "game_count": str(len(shipped) + len(passes)),
        "flags_pass": str(sum(1 for f in flags if f["ok"])),
        "flags_total": str(len(flags)),
        "commit_count": str(len(commits)),
        "plugins": plugin_rows(),
        "sqc": sqc_rows(),
        "games": game_rows(shipped) + game_rows(passes),
        "flags": flag_rows(shipped) + flag_rows(passes),
        "commits": "".join(f"<li><code>{esc(c[:7])}</code> {esc(c[8:240])}</li>" for c in commits),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    default = ROOT / "viwo-data" / "status" / f"ViWo-status-{__version__}.pdf"
    ap.add_argument("--out", type=Path, default=default)
    ap.add_argument("--tests", type=Path, help="a unittest log to read the test count from")
    args = ap.parse_args(argv)
    log = args.tests.read_text(encoding="utf-8", errors="replace") if args.tests else ""
    page = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values(log).items():
        page = page.replace("{{" + key + "}}", value)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    source = args.out.with_suffix(".html")
    source.write_text(page, encoding="utf-8")
    edge = next((p for p in EDGE if p.is_file()), None)
    if edge is None:
        print(f"HTML written: {source} (no Edge found for the PDF)")
        return 0
    argv = [str(edge), "--headless=new", "--disable-gpu", "--no-pdf-header-footer"]
    subprocess.run(
        [*argv, f"--print-to-pdf={args.out.resolve()}", source.resolve().as_uri()], timeout=120
    )
    print(f"PDF written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
