# 15 Release package

Area code `REL`. Artifacts: the portable Windows bundle `ViWo-<version>-windows-x64.zip`
(`dist\viwo\viwo.exe`, no Python needed) and the wheel / sdist in `release\`. Build locally:

```powershell
pip install pyinstaller==6.22.3 build==1.3.0
python packaging\build_portable.py --out dist     # builds dist\viwo\ and smoke-tests viwo.exe
python -m build --outdir release                  # wheel + sdist
Compress-Archive dist\viwo release\ViWo-<version>-windows-x64.zip
```

## SQC-REL-01 (P0) Portable bundle starts, serves, extracts

Preconditions: a Windows machine or VM WITHOUT Python on PATH (or a user account where `python`
is not found). Copy the zip and the fixture folder `C:\sqc` there.

Steps:
1. Unzip to `C:\ViWo\`; `C:\ViWo\viwo.exe` (guide), `viwo.exe slots`, `viwo.exe info`.
2. `viwo.exe serve` ; wait for the browser; let the landing install the tools.
3. `Get-ChildItem C:\ViWo` ; `Get-ChildItem C:\ViWo\third_party`
4. EXTRACT `C:\sqc\renpy\game`; SORT; CLEANUP scan; PATCHED COPY plan.
5. `viwo.exe extract C:\sqc\zip-basic\game --workspace C:\ViWo\viwo-data\ws1`

Expected: 1: the guide; `slots` shows `unitypy found`, `py7zr found`, `unrpa found` (bundled) and
`lz4 found`; no `ModuleNotFoundError`, no console window error about tkinter. 2: the landing runs
the preflight and installs into `C:\ViWo\third_party\` (created next to `viwo.exe`); the summary
shows the installed count. 3: `startup.ini`, `README.md`, `LICENSE`, `viwo.exe`, `_internal\`
(with `viwo\data\tools.json` and `viwo\web\` inside), `viwo-data\`, `third_party\`. 4: all four
views work; the folder picker (`BROWSE`) opens a native dialog (tkinter bundled). 5: works, exit 0.

## SQC-REL-02 (P0) Smoke test of `build_portable.py` passes locally

Steps: `python packaging\build_portable.py --out dist`

Expected: PyInstaller completes; the script prints `$ viwo info -> 0`, `$ viwo slots -> 0`,
`$ viwo --json detect ... -> 0` and the extraction smoke with exit 0; `dist\viwo\viwo.exe` exists;
UnityPy's native libs are collected (no warning about missing `archspec`/`texture2ddecoder`).

## SQC-REL-03 (P0) Wheel install in a clean venv

Steps:
```powershell
py -3.13 -m venv C:\sqc\_venv; C:\sqc\_venv\Scripts\Activate.ps1
pip install release\viwo-<version>-py3-none-any.whl
viwo; viwo slots; viwo install repak; viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\whl
```

Expected: the wheel installs with no dependencies; `viwo` runs; `third_party\` and `viwo-data\`
are created next to the working directory's `startup.ini` (or the current folder when none);
`pip install "viwo[unity,sevenzip,renpy,lz4]"` from the same wheel adds the Python tools.

## SQC-REL-04 (P1) Version consistency

Steps: `viwo.exe --json info | Select-String version`; compare with the zip name, `python
tools\version.py show` in the repo at the tagged commit, `docs\release-notes.md` first line.

Expected: all the same `a.b.c`; the release notes' first heading names the same major version.

## SQC-REL-05 (P1) Clean uninstall

Steps: delete `C:\ViWo\`.

Expected: nothing of ViWo remains anywhere else on the machine (no registry keys, no files in
`%APPDATA%`, `%LOCALAPPDATA%`, `%TEMP%\viwo` may hold staging leftovers from killed runs only).

## SQC-REL-06 (P2) GitHub release page

Steps: open the release `v<a>.0.0` on GitHub.

Expected: assets: the zip, the wheel, the sdist, `SHA256SUMS.txt`; the notes are
`docs/release-notes.md`; `sha256sum` of the downloaded zip matches the sums file.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-REL-01 | | version: | | |
| SQC-REL-02 | | | | |
| SQC-REL-03 | | | | |
| SQC-REL-04 | | | | |
| SQC-REL-05 | | | | |
| SQC-REL-06 | | | | |
