# 15 Release package

Area code `REL`. Contract doc 12.6. Artifacts: the portable Windows bundle
`ViWo-<version>-windows-x64.zip` (`dist\viwo\viwo.exe`, no Python needed), the wheel and the sdist.
`release.yml` builds and publishes them on a `vN.0.0` tag (owner's approval only). Build locally:

```powershell
pip install pyinstaller==6.22.3 build==1.3.0
python packaging\build_portable.py --out dist     # builds dist\viwo\ and smoke-tests viwo.exe
python -m build --outdir release                  # wheel + sdist
Compress-Archive dist\viwo release\ViWo-<version>-windows-x64.zip
```

Without network for `build`: `pip wheel . --no-deps --no-build-isolation -w release` (setuptools
and wheel in the venv) builds the same wheel.

## SQC-REL-01 (P0) Portable bundle starts, serves, extracts

Preconditions: a Windows machine or VM WITHOUT Python on PATH. Copy the zip and `C:\sqc` there.

Steps:
1. Unzip to `C:\ViWo\`; `C:\ViWo\viwo.exe` (guide), `viwo.exe slots`, `viwo.exe info`.
2. `viwo.exe serve`; let the landing install the tools.
3. `Get-ChildItem C:\ViWo`; `Get-ChildItem C:\ViWo\third_party`
4. EXTRACT `C:\sqc\renpy\game`; SORT; CLEANUP scan; PATCHED COPY plan; SEARCH the workspace for `label`.
5. `viwo.exe extract C:\sqc\zip-basic\game --workspace C:\ViWo\viwo-data\ws1`

Expected: 1: the guide; `slots` shows `unitypy`, `py7zr`, `unrpa`, `lz4`, `pillow` found (bundled);
no `ModuleNotFoundError`, no tkinter error. 2: the landing runs the preflight and installs into
`C:\ViWo\third_party\` (next to `viwo.exe`); the summary shows the installed count. 3:
`startup.ini`, `README.md`, `LICENSE`, `viwo.exe`, `_internal\` (with `viwo\data\tools.json`,
`viwo\data\workbooks\`, `viwo\data\runbooks\` and `viwo\web\` inside), `viwo-data\`,
`third_party\`. 4: every view works; `BROWSE` opens a native dialog. 5: exit 0.

## SQC-REL-02 (P0) Smoke test of `build_portable.py` passes locally

Steps: `python packaging\build_portable.py --out dist`

Expected: PyInstaller completes; the script prints `$ viwo info -> 0`, `$ viwo slots -> 0`,
`$ viwo --json detect ... -> 0` and the extraction smoke with exit 0; `dist\viwo\viwo.exe` exists;
UnityPy's native libs are collected (no warning about missing `archspec` / `texture2ddecoder`).

## SQC-REL-03 (P0) Wheel install in a clean venv

Steps:
```powershell
py -3.10 -m venv C:\sqc\_venv
C:\sqc\_venv\Scripts\python -m pip install release\viwo-<version>-py3-none-any.whl
mkdir C:\sqc\whl; cd C:\sqc\whl
C:\sqc\_venv\Scripts\viwo.exe; C:\sqc\_venv\Scripts\viwo.exe info; C:\sqc\_venv\Scripts\viwo.exe extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\whl
C:\sqc\_venv\Scripts\viwo.exe install repak
```

Expected: the wheel's metadata: `Requires-Python: >=3.10`, one dependency `Pillow==11.3.0`, extras
`unity`, `sevenzip`, `renpy`, `lz4`, `patch`, `runtime`, `dev`; it holds `viwo\web\` (52 files), the
six workbooks, the three runbooks, `viwo\data\locks\`, `tools.json`, the Ghidra script, the
workers and the RenderDoc scripts. `viwo` runs on Python 3.10; `info` says `Startup : defaults`;
`viwo-data\` (and `third_party\` after an install) appear in the current folder when it holds no
`startup.ini`; the zip extraction works; `pip install "viwo[unity,sevenzip,renpy,lz4]"` from the same
wheel adds the Python tools.

## SQC-REL-04 (P1) Version consistency

Steps: `python tools\version.py show` at the tagged commit; `pyproject.toml` `version`;
`python -c "import viwo; print(viwo.__version__)"` in the clean venv; `viwo diag --out d.zip` and
`about.json` `viwo`; the zip name; the first heading of `docs\release-notes.md`.

Expected: all the same `a.b.c`; the release notes' heading names the release being shipped.

## SQC-REL-05 (P1) Clean uninstall

Steps: delete `C:\ViWo\`.

Expected: nothing of ViWo remains elsewhere (no registry keys, nothing in `%APPDATA%` or
`%LOCALAPPDATA%`; `%TEMP%\viwo` may hold staging leftovers from killed runs only).

## SQC-REL-06 (P2) GitHub release page

Steps: open the release `v<a>.0.0` on GitHub.

Expected: assets: the zip, the wheel, the sdist, `SHA256SUMS.txt`; the notes are
`docs/release-notes.md`; `sha256sum` of the downloaded zip matches the sums file.

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-REL-01 | NOT RUN | 1.36.0+search+apk (unreleased) | needs the portable build (PyInstaller, a download) and a machine without Python | agent | 2026-11-23 |
| SQC-REL-02 | NOT RUN | 1.36.0+search+apk (unreleased) | PyInstaller is not installed; installing it is a download | agent | 2026-11-23 |
| SQC-REL-03 | PASS (but the install steps) | 1.36.0+search+apk (unreleased) | wheel built with `pip wheel --no-build-isolation` from a copy of the worktree (434 members); installed `--no-index --no-deps` into a fresh 3.10 venv; `viwo`, `info`, the extraction as written. `pip` resolving Pillow, `viwo install repak` and the extras NOT RUN (downloads) | agent | 2026-11-23 |
| SQC-REL-04 | FAIL | 1.36.0+search+apk (unreleased) | `1.36.0` in `version.py show`, `pyproject.toml`, `viwo.__version__`, `pip show`, diag `about.json`; but `docs/release-notes.md` line 1 reads `## ViWo (Vidya Wormhole) 1.6.0`. `viwo info` prints no version | agent | 2026-11-23 |
| SQC-REL-05 | NOT RUN | 1.36.0+search+apk (unreleased) | needs the portable bundle | agent | 2026-11-23 |
| SQC-REL-06 | NOT RUN | 1.36.0+search+apk (unreleased) | no `v2.0.0` release exists (owner's call) | agent | 2026-11-23 |
