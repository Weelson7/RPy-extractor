# 14 Security

Area code `SEC`. Contract doc 4 (security model), doc 10 (pinned downloads). The local server: a
per-start token in a meta tag, a `Host` check, JSON-only POST bodies, static files only from
`viwo\web\`, previews only from inside the workspace and inert, the page under a strict policy. The
installer: HTTPS-only pinned downloads, sha256 verified before anything is unpacked, safe unpacking
(no traversal, no links), nothing outside `third_party\`.

Use `curl.exe`. `$U` = `http://127.0.0.1:8081` (or the port you serve on), `$T` = the token from the
page source (`<meta name="viwo-token" content="...">`):
`$T = [regex]::Match((Invoke-WebRequest -UseBasicParsing $U/).Content, 'name="viwo-token" content="([^"]+)"').Groups[1].Value`.

## SQC-SEC-01 (P0) Token required on every `/api/` route

Steps:
1. `curl.exe -s -w " %{http_code}" $U/api/status`
2. `curl.exe -s -w " %{http_code}" -H "X-VIWO-Token: wrong" $U/api/status`
3. `curl.exe -s -o NUL -w "%{http_code}" -H "X-VIWO-Token: $T" $U/api/status`
4. Restart the server; repeat 3 with the old `$T`; with a page open from before the restart, wait.
5. `curl.exe -s -H "X-VIWO-Token: $T" $U/api/logs` (new token).

Expected: 1 and 2: `{"success": false, "error": "Missing or invalid API token", "code": "token"}
403`; 3: `200`; 4: `403` with `code: "token"`; the open page reloads itself and works (12-ui-ux
SQC-UI-14); 5: the log holds `[SECURITY] GET /api/status rejected: Missing or invalid API token`.

## SQC-SEC-02 (P0) Host header check

Steps: with the token: `-H "Host: evil.example"`, `-H "Host: localhost:<port>"`, `-H "Host: [::1]:<port>"`.

Expected: `{"success": false, "error": "Host not allowed"} 403` for the first; `200` for the others.

## SQC-SEC-03 (P0) JSON-only POST, invalid JSON, body size

Steps:
1. `curl.exe -s -w " %{http_code}" -X POST -H "X-VIWO-Token: $T" -H "Content-Type: text/plain" -d "x" $U/api/logs/clear`
2. The same with `-H "Content-Type: application/json" -d "{bad"`
3. The same with `-d "{}"`
4. The same with `-H "Content-Length: 99999999999" --data "{}"`

Expected: 1: `{"success": false, "error": "Content-Type must be application/json"} 415`; 2:
`{"success": false, "error": "Invalid JSON"} 400`; 3: `{"success": true} 200`; 4:
`{"success": false, "error": "Request body too large or malformed"} 413`.

## SQC-SEC-04 (P0) Pinned downloads: HTTPS only, checksum refusal, no traversal

A copy of `tools.json` with the `repak` entry pointing at a local zip (`repak_cli/repak.exe` and a
`../evil.txt` member) is installed into a scratch home through the real installer; save as
`C:\sqc\sec_install.py` and run it from `<repo>` (`python C:\sqc\sec_install.py good|badsum|http C:\sqc\_sec\<case>`):

```python
import hashlib, io, json, sys, zipfile
from pathlib import Path
from viwo.core import thirdparty

case, home = sys.argv[1], Path(sys.argv[2])
home.mkdir(parents=True, exist_ok=True)
(home / "startup.ini").write_text("[startup]\nauto_install = off\n")
blob = io.BytesIO()
with zipfile.ZipFile(blob, "w") as z:
    z.writestr("repak_cli/repak.exe", b"MZ fake")
    z.writestr("../evil.txt", b"never")
zp = home / "repak.zip"
zp.write_bytes(blob.getvalue())
data = json.loads(thirdparty.MANIFEST.read_text(encoding="utf-8"))
spec = data["tools"]["repak"][thirdparty.PLATFORM]
spec.pop("needs", None)
spec.update(
    url=zp.as_uri(),
    sha256=hashlib.sha256(zp.read_bytes()).hexdigest(),
    size=zp.stat().st_size,
    kind="zip",
    find="repak.exe",
)
if case == "badsum":
    spec["sha256"] = "0" * 64
if case == "http":
    spec["url"] = "http://example.invalid/repak.zip"
(home / "tools.json").write_text(json.dumps(data))
thirdparty.MANIFEST = home / "tools.json"
from viwo.cli import main

sys.exit(main(["--ini", str(home / "startup.ini"), "install", "repak"]))
```

Expected: `good`: `Installed: repak`, `third_party\repak\repak_cli\repak.exe` exists, `evil.txt`
nowhere on disk. `badsum`: `viwo: warning: repak.zip: checksum mismatch, not installed`,
`FAILED repak: ...`, no `third_party\repak`. `http`: `repak.zip: downloads must use https`, no
network request, no `third_party\repak`.

## SQC-SEC-05 (P0) Static and preview containment

Steps (a workspace with `png\title.png` active, e.g. an extraction of `C:\sqc\zip-basic\game`):
1. `curl.exe -s -o NUL -w "%{http_code}" --path-as-is "$U/../startup.ini"` and `"$U/..%2f..%2fstartup.ini"`
2. `"$U/preview/..%2f..%2fstartup.ini"`, `"$U/preview/..%5c..%5ctoken.txt"`, `"$U/preview/C:/Windows/win.ini"`, `"$U/preview/.viwo-workspace"`
3. `curl.exe -s -D - -o NUL "$U/preview/png/title.png"`; the same with `-r 0-3`
4. `curl.exe -s -o NUL -w "%{http_code}" --path-as-is "$U/js/../css/base.css"`

Expected: 1, 2: `404` each (never a file outside the web root or the workspace, never a drive or
UNC name resolved). 3: `200` with `Accept-Ranges: bytes`, `Content-Security-Policy: sandbox`,
`X-Content-Type-Options: nosniff`; the range answers `206`. 4: `200` or `404`, never a file outside
`viwo\web\`.

## SQC-SEC-06 (P0) Installer unpacking: traversal, a killed download

Steps:
1. SQC-SEC-04 case `good` (a pinned zip with a `../evil.txt` member); search the disk for `evil.txt`.
2. `viwo install renderdoccmd`, Ctrl+C after 2 s; then `viwo install renderdoccmd` to the end.

Expected: 1: `evil.txt` nowhere; the tool found (`viwo slots` of that home lists `repak`). 2: no
partly unpacked `third_party\renderdoccmd` without `renderdoccmd.exe` (a FAIL); a leftover
`.renderdoccmd-xxxx` temp folder after the second install is a P2 note.

## SQC-SEC-07 (P1) Secrets never logged or written

Steps: record or run an extraction of `C:\sqc\godot\encrypted` with its key (`--ini
C:\sqc\ini\godot-fake.ini`, key `ab` x 32, 20-guides SQC-GUIDE-06); search `viwo-data\`, the
workspace, `GET /api/logs`, `GET /api/jobs` and a `viwo diag` bundle for the key.

Expected: the key appears nowhere (run records and recordings store `<secret>` / `{secret_1}`);
`viwo diag` says `(secrets stripped)`.

## SQC-SEC-08 (P1) The server binds where it is told, and only it

Steps:
1. `netstat -ano | findstr :<port>` while `viwo serve` runs.
2. With that server running, `viwo serve --port <same port> --no-browser` in a second terminal.
3. From another machine on the LAN: `http://<your ip>:<port>/`; then `viwo serve --host 0.0.0.0`
   and the same; then `--host <one LAN address>` with the printed `?key=` link.

Expected: 1: `127.0.0.1:<port> LISTENING`, one process. 2: `viwo: cannot listen on
127.0.0.1:<port>: ...`, exit 2: a second process (ViWo or anything else) must not share the port.
3: refused at the TCP level; with `0.0.0.0` the request reaches the server but gets `403 Host not
allowed`; with one LAN address, requests carrying that Host and the key are served.

## SQC-SEC-09 (P2) Dependency-free runtime

Steps: in a venv of its own: `pip uninstall -y UnityPy py7zr unrpa lz4`; `viwo slots`; `viwo extract
C:\sqc\zip-basic\game --workspace C:\sqc\_ws\nodeps`; `viwo install unitypy py7zr unrpa lz4`.

Expected: the four `missing`; the zip extraction works (stdlib only); after the install (into
`third_party\python`) `viwo slots` shows them found.

## SQC-SEC-10 (P0) The page's own policy

Steps: `curl.exe -s -D - -o NUL $U/`

Expected: `Content-Security-Policy: default-src 'self' data: blob:; script-src 'self' blob:
'wasm-unsafe-eval'; ...; connect-src 'self' data: blob: https://www.gstatic.com; frame-ancestors
'none'; object-src 'none'; base-uri 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options:
nosniff`.

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-SEC-01 | PASS | 1.36.0+search+apk (unreleased) | live server, port 8192; step 4 seen through the open page: its old token got `code: token` and it reloaded by itself; no SECURITY lines in the restarted server's terminal | agent | 2026-11-23 |
| SQC-SEC-02 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-SEC-03 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-SEC-04 | PASS | 1.36.0+search+apk (unreleased) | all three cases; `viwo install` exits 0 after a refused checksum or http URL (`Installed: nothing`, `FAILED repak: ...`) | agent | 2026-11-23 |
| SQC-SEC-05 | PASS | 1.36.0+search+apk (unreleased) | `js/../css/base.css` answers 404 | agent | 2026-11-23 |
| SQC-SEC-06 | PASS (step 1) / NOT RUN (step 2) | 1.36.0+search+apk (unreleased) | `evil.txt` found nowhere under the scratch homes, `third_party\repak\repak_cli\repak.exe` installed; step 2 is a real download: not allowed in this run | agent | 2026-11-23 |
| SQC-SEC-07 | PASS | 1.36.0+search+apk (unreleased) | through the API with the fake Godot tools; the diag bundle not searched for the key (its `about.json` names the version) | agent | 2026-11-23 |
| SQC-SEC-08 | FAIL (step 2) | 1.36.0+search+apk (unreleased) | step 1 PASS (`127.0.0.1:8192`, one pid). Step 2: the second `viwo serve --port 8192` printed `-> http://127.0.0.1:8192/` and both listened (`netstat`: two LISTENING pids on 8192): `viwo/api/server.py` 235-248, `QuietServer` keeps `allow_reuse_address`, which on Windows lets another process bind a port in use. Step 3 NOT RUN (no second machine) | agent | 2026-11-23 |
| SQC-SEC-09 | NOT RUN | 1.36.0+search+apk (unreleased) | the only venv here is shared with the main checkout | agent | 2026-11-23 |
| SQC-SEC-10 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
