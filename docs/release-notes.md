## ViWo (Vidya Wormhole) 1.6.0

A community-owned, local-first orchestrator for game reverse engineering over three arms:
static (survey, extraction, curation, code analysis), dynamic (GPU capture, runtime agents,
memory dumps, API traces, debugger and memory handoffs) and patching (round trip into a patched
copy, binary patch sets, mod packages). What changed in each version: `CHANGELOG.md`.

**Downloads**
- `ViWo-<version>-windows-x64.zip`: portable Windows build. Unzip, run `viwo.exe serve` (opens
  your browser). No Python needed. Every tool installs itself into `third_party/` next to
  `viwo.exe` from its pinned release (HTTPS, size and sha256 checked); `viwo.exe slots` shows
  what is bound.
- `viwo-<version>-py3-none-any.whl` and the sdist: `pip install` (Python 3.11+), then
  `viwo install --all` once for the tools.

**Philosophy** (README): a community tool, MIT, forkable, for everyone who wants to look inside
a game. No boundaries and no safeguards in the code: nothing is refused because of what a game
is; anti-cheat and online detection are warnings plus one opt-in. A disclaimer replaces
safeguards and the responsibility is the user's. Borderline code is never first-party. The game
folder is never written to.

Open work and known limits: `docs/HANDOFF.md` and `docs/contract/CONFORMANCE.md`.
