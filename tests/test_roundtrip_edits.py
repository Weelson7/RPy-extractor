"""L3: the round-trip edit set (doc 18.2-18.3) as a property: over random provenance maps and
random user actions (untouched, edited in the same format, edited into another format,
deleted, added under _added/), the edit set holds exactly the edits that can be written back,
and every one that cannot is named with its reason; nothing is silently dropped."""

from __future__ import annotations

import hashlib
import json
import random
import tempfile
import unittest
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.core.roundtrip_edits import ADDED_DIR, edit_set, format_ok, original_hashes

PNG, JPEG = b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff\xe0"


def _entry(rng: random.Random, i: int) -> tuple[dict, bytes]:
    kind = rng.choice(["loose", "member", "exported", "derived", "carved"])
    path = f"{rng.choice(['png', 'txt'])}/f{i}.{'png' if rng.random() < 0.6 else 'txt'}"
    body = (PNG if path.endswith(".png") else b"") + rng.randbytes(20)
    entry = {"path": path, "sha256": hashlib.sha256(body).hexdigest(), "kind": kind}
    if kind == "member":
        entry |= {"container": "data.zip", "member": f"assets/f{i}{Path(path).suffix}"}
    if kind == "exported":
        entry |= {"plugin": "unity"}
    return entry, body


class EditSetTests(unittest.TestCase):
    def test_every_edit_is_in_the_set_or_named(self) -> None:
        rng = random.Random(18)
        for _ in range(30):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                lines, want_edits, want_skips, missing = [], set(), set(), []
                for i in range(rng.randint(1, 14)):
                    entry, body = _entry(rng, i)
                    lines.append(json.dumps(entry))
                    file = root / entry["path"]
                    file.parent.mkdir(parents=True, exist_ok=True)
                    action = rng.choice(["keep", "same", "other", "delete"])
                    if action == "delete":
                        missing.append(entry["path"])
                        continue
                    if action == "keep":
                        file.write_bytes(body)
                        continue
                    png = file.suffix == ".png"
                    head = (PNG if png else b"") if action == "same" else (JPEG if png else PNG)
                    file.write_bytes(head + rng.randbytes(20))
                    target = entry.get("member") or entry["path"]
                    if entry["kind"] not in ("loose", "member", "exported"):
                        want_skips.add(f"{entry['path']}: {entry['kind']} file")
                    elif entry["kind"] != "exported" and not format_ok(file, target):
                        want_skips.add(f"{entry['path']}: format differs")
                    else:
                        want_edits.add(entry["path"])
                (root / ws.PROVENANCE_FILE).parent.mkdir(parents=True, exist_ok=True)
                (root / ws.PROVENANCE_FILE).write_text("\n".join(lines) + "\n{broken\n")
                added = rng.sample(["mods/new.txt", "data/extra.bin", "x.png"], rng.randint(0, 3))
                for rel in added:
                    (root / ADDED_DIR / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / ADDED_DIR / rel).write_bytes(b"added")
                edits, skipped = edit_set(root)
                got = {e.file.relative_to(root).as_posix() for e in edits if e.kind != "added"}
                self.assertEqual(got, want_edits)
                self.assertEqual(
                    sorted(e.member for e in edits if e.kind == "added"), sorted(added)
                )
                for skip in want_skips:
                    self.assertTrue(any(s.startswith(skip) for s in skipped), (skip, skipped))
                if missing:  # a moved or deleted file is counted and named, never dropped
                    line = next(s for s in skipped if "moved, renamed or trashed" in s)
                    self.assertTrue(line.startswith(f"{len(missing)} extracted file(s)"))
                    self.assertIn(missing[0], line)
                    self.assertEqual("more" in line, len(missing) > 5)
                self.assertEqual(len(skipped), len(want_skips) + bool(missing))

    def test_format_rule_and_original_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for head, member, ok in (
                (PNG, "a.png", True),
                (JPEG, "a.png", False),  # another known format: rejected
                (b"\0\1\2\3", "a.png", True),  # unknown bytes: accepted
                (JPEG, "a.unknownext", True),
            ):
                file = root / "f"
                file.write_bytes(head + b"rest")
                self.assertEqual(format_ok(file, member), ok, (head, member))
            lines = [
                {"path": "a", "sha256": "1", "kind": "member", "container": "c.zip", "member": "m"},
                {"path": "b", "sha256": "2", "kind": "loose"},
            ]
            (root / ws.PROVENANCE_FILE).parent.mkdir(parents=True)
            (root / ws.PROVENANCE_FILE).write_text("\n".join(json.dumps(x) for x in lines))
            self.assertEqual(original_hashes(root), {"c.zip": {"m": "1"}})


if __name__ == "__main__":
    unittest.main()
