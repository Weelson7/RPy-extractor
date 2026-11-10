"""The CTF results at the end of the technical PDF: the flags of the real-game passes (each
game's `sqc/ctf.json` flags, judged by `tools/integration_games.py` into
`viwo-data/games-pass/<game>/report.json`) and the challenges run by hand, recorded as they come
in `viwo-data/ctf/results.json` ({id, game, date, asked, how, result, limits})."""

import json
from pathlib import Path

from reference import esc


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def passes(data: Path) -> str:
    """One row per game of the games pass: engine, files out, flags passed, the game unchanged."""
    rows = []
    for report in sorted((data / "games-pass").glob("*/report.json")):
        for game in _load(report) or []:
            flags = game.get("flags", [])
            ok = sum(1 for f in flags if f.get("ok"))
            failed = [f["name"] for f in flags if not f.get("ok")]
            extract = game.get("extract") or {}
            rows.append(
                f"<tr><td>{esc(game.get('game', report.parent.name))}</td>"
                f"<td>{esc(', '.join(extract.get('plugins', [])) or '-')}</td>"
                f"<td>{extract.get('copied', 0):,}</td><td>{ok} / {len(flags)}</td>"
                f"<td>{esc('; '.join(failed)) or '-'}</td>"
                f"<td>{'yes' if game.get('gameUnchanged') else 'NO'}</td></tr>"
            )
    if not rows:
        return "<p class='sub'>No games pass yet: run <code>tools/games_pass.ps1</code>.</p>"
    head = "<tr><th>Game</th><th>Engine</th><th>Files out</th><th>Flags</th>"
    head += "<th>Flags missed</th><th>Game folder unchanged</th></tr>"
    return f"<table>{head}{''.join(rows)}</table>"


def challenges(data: Path) -> str:
    """Each challenge run by hand: what was asked, how ViWo did it, the result and its limits."""
    items = _load(data / "ctf" / "results.json") or []
    if not items:
        where = "<code>viwo-data/ctf/results.json</code>"
        return f"<p class='sub'>No challenge recorded yet ({where}).</p>"
    parts = []
    for c in items:
        parts.append(
            f"<h3>{esc(c.get('asked', c.get('id', '')))}: {esc(c.get('game', ''))}"
            f" <span class='sub'>({esc(c.get('date', ''))})</span></h3>"
            f"<p><b>How.</b> {esc(c.get('how', ''))}</p>"
            f"<p><b>Result.</b> {esc(c.get('result', ''))}</p>"
            f"<p><b>Limits.</b> {esc(c.get('limits', '-'))}</p>"
        )
    return "\n".join(parts)


def section(data: Path) -> str:
    return (
        "<h3>Flags of the real-game passes</h3>" + passes(data)
        + "<h3>Challenges</h3>" + challenges(data)
    )  # fmt: skip
