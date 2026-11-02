# 14 Security

Area code `SEC`. The local server model (doc 4.1): a per-start token in a meta tag, `Host`
check, JSON-only POST bodies, static files only from `viwo\web\`, previews only from inside the
workspace. The installer: HTTPS-only pinned downloads, sha256 verified before anything is
unpacked, safe unpacking (no traversal, no links), nothing outside `third_party\`.

Use `curl.exe` (Windows 10+ ships it). `$T` = the token from the page source
(`<meta name="viwo-token" content="...">`), `$U` = `http://127.0.0.1:8081`.

## SQC-SEC-01 (P0) Token required on every `/api/` route

Steps:
1. `curl.exe -s -o - -w " %{http_code}" $U/api/status`
2. `curl.exe -s -w " %{http_code}" -H "X-VIWO-Token: wrong" $U/api/status`
3. `curl.exe -s -w " %{http_code}" -H "X-VIWO-Token: $T" $U/api/status`
4. Restart the server, reuse the old `$T` in step 3.

Expected: 1 and 2: `{"success": false, "error": "Missing or invalid API token"} 403`; 3: JSON
`200`; 4: `403` (a new token per start). The activity log records `[SECURITY] ... rejected`.

## SQC-SEC-02 (P0) Host header check

Steps: `curl.exe -s -w " %{http_code}" -H "Host: evil.example" -H "X-VIWO-Token: $T" $U/api/status`;
same with `-H "Host: localhost:8081"`.

Expected: `403 Host not allowed` for the first; `200` for the second (`127.0.0.1`, `localhost`,
`[::1]` and the configured host are accepted).

## SQC-SEC-03 (P0) JSON-only POST, invalid JSON

Steps:
1. `curl.exe -s -w " %{http_code}" -X POST -H "X-VIWO-Token: $T" -H "Content-Type: text/plain" -d "x" $U/api/logs/clear`
2. `curl.exe -s -w " %{http_code}" -X POST -H "X-VIWO-Token: $T" -H "Content-Type: application/json" -d "{bad" $U/api/logs/clear`
3. `curl.exe -s -w " %{http_code}" -X POST -H "X-VIWO-Token: $T" -H "Content-Type: application/json" -d "{}" $U/api/logs/clear`

Expected: 1: `415 Content-Type must be application/json`; 2: `400 Invalid JSON`; 3: `200`.

## SQC-SEC-04 (P0) Pinned downloads: HTTPS only and checksum refusal

Steps:
1. SQC-DEP-04 (checksum mismatch).
2. Edit `tools.json`: change `tools.repak.windows.url` to start with `http://`; `viwo install repak`;
   restore.

Expected: 1: `refused ... checksum mismatch, not installed`, no folder. 2: `refused: ...
downloads must use https`, no network request is made (watch with the firewall log or Fiddler:
none).

## SQC-SEC-05 (P0) Static and preview containment

Steps:
1. `curl.exe -s -w " %{http_code}" "$U/../startup.ini"` and `"$U/..%2f..%2fstartup.ini"`
2. `curl.exe -s -w " %{http_code}" "$U/preview/..%2f..%2fstartup.ini"`
3. `curl.exe -s -w " %{http_code}" "$U/preview/png/title.png"` (with the zip-basic workspace active)
4. `curl.exe -s -w " %{http_code}" "$U/js/../viwo.css"`

Expected: 1 and 2: `404`; 3: `200` with `Accept-Ranges: bytes`; 4: `200` (normalized inside the
web root) or `404`, never a file outside `viwo\web\`.

## SQC-SEC-06 (P0) Installer unpacking: traversal, links, temp cleanup

Steps:
1. Build a zip with a `../evil.txt` member and a normal `tool.exe`, host it as `file://` in a copy
   of `tools.json` (see `tests/test_thirdparty.py` for the recipe), point `MANIFEST` at it via a
   small script, install.
2. Kill the process during a real download (`viwo install renderdoccmd`, Ctrl+C after 2 s).

Expected: 1: `evil.txt` is nowhere on disk; the tool is found. 2: `third_party\` contains no
`.renderdoccmd-xxxx` temp folder after the next `viwo install renderdoccmd` completes (the temp
dir is created fresh and the previous one is left only until the next successful install:
record what you see; a leftover temp folder is a P2 note, a partially unpacked
`third_party\renderdoccmd` without `renderdoccmd.exe` is a FAIL).

## SQC-SEC-07 (P1) Secrets never logged

Steps: SQC-SAFE-08; additionally `curl.exe -s -H "X-VIWO-Token: $T" $U/api/logs` after a UI run
with a Godot key.

Expected: no key value in the logs response, the run record or the files under `viwo-data\logs\`.

## SQC-SEC-08 (P1) Server binds to 127.0.0.1 only

Steps: `netstat -ano | findstr 8081`; from another machine on the LAN open `http://<your ip>:8081/`.

Expected: `127.0.0.1:8081 LISTENING` only; the LAN request is refused at the TCP level. (Binding
to `0.0.0.0` via `[server] host` is a deliberate user choice; the Host check then allows the
configured host.)

## SQC-SEC-09 (P2) Dependency-free runtime

Steps: `pip uninstall -y UnityPy py7zr unrpa lz4`; `viwo slots`; `viwo extract C:\sqc\zip-basic\game ...`.

Expected: the four show `missing`; zip extraction still works (stdlib only); reinstall with
`viwo install unitypy py7zr unrpa lz4` (into `third_party\python`) and `viwo slots` shows them
found again.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-SEC-01 | | version: | | |
| SQC-SEC-02 | | | | |
| SQC-SEC-03 | | | | |
| SQC-SEC-04 | | | | |
| SQC-SEC-05 | | | | |
| SQC-SEC-06 | | | | |
| SQC-SEC-07 | | | | |
| SQC-SEC-08 | | | | |
| SQC-SEC-09 | | | | |
