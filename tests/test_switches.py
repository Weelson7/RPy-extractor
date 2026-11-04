"""L3: the [startup] features switches gate exactly what they name. With one switch off, every
entry point behind it refuses (code refused, a hint naming the switch); with all on, none of
them refuses for that reason. A switch the UI shows always does something."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_game, runtime
from viwo.api import app as app_module
from viwo.api.handlers import POST
from viwo.contracts import CancelToken, ExtractionRequest, ViwoError

ALL = ("extraction", "sorting", "merger", "analysis", "capture")


def entry_points(root: Path, rt) -> dict[str, list]:
    """switch -> callables that raise ViwoError or return an API answer."""
    from viwo.core.analysis import AnalysisRequest, analyze
    from viwo.core.capture.runtime import RuntimeRequest, run
    from viwo.core.pipeline.runner import extract

    game, app = make_game(root), app_module.App(rt)
    app.workspace = root / "ws"
    api = lambda route: lambda: POST[route](app, {"path": "png/x.png"})  # noqa: E731
    return {
        "extraction": [
            lambda: extract(
                rt,
                ExtractionRequest(str(game), str(root / "w")),
                "j",
                lambda e: None,
                CancelToken(),
            )
        ],
        "sorting": [api(r) for r in ("/api/sort-keep", "/api/sort-trash", "/api/keep-selected")],
        "merger": [api("/api/media-merger/list"), api("/api/media-merger/build")],
        "analysis": [lambda: analyze(rt, AnalysisRequest(game, root / "ws", "x"))],
        "capture": [lambda: run(rt, "dump", RuntimeRequest(root / "ws", pid=1))],
    }


def refusal(call) -> str:
    """The refused error's hint, or "" when the call was not refused."""
    try:
        answer = call()
    except ViwoError as exc:
        return exc.hint if exc.code == "refused" else ""
    except Exception:  # noqa: BLE001 (any other failure is past the switch)
        return ""
    if isinstance(answer, dict) and answer.get("code") == "refused":
        return str(answer.get("hint", ""))
    return ""


class SwitchTests(unittest.TestCase):
    def test_each_switch_gates_its_entry_points_and_only_them(self) -> None:
        for off in ALL:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                features = ", ".join(f for f in ALL if f != off)
                rt = runtime(root, f"[startup]\nfeatures = {features}\n[plugins]\ngeneric = on\n")
                for switch, calls in entry_points(root, rt).items():
                    for call in calls:
                        hint = refusal(call)
                        if switch == off:
                            self.assertIn(off, hint, f"{off} off: {switch} not refused")
                        else:
                            self.assertNotIn(f"add {switch}", hint, f"{off} off refused {switch}")
        app_module.reset_app()


if __name__ == "__main__":
    unittest.main()
