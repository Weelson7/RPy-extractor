# 10 Merger

Area code `MERGE`. Fixture: `merger` (frames `01_walk..05_walk.png`, `01_run..03_run.png`,
`walk_01..02.png`, `03_walk.mp4` when ffmpeg was on PATH, `loop.wav`). Extract it first:
`viwo extract C:\sqc\merger\game --workspace C:\sqc\_ws\merge --on-existing replace`, switch the
UI workspace to it. Needs ffmpeg + ffprobe (pinned, installed by 01).

## SQC-MERGE-01 (P0) Groups, timeline, one build

Steps:
1. `MERGER`. Read `GROUPS`.
2. Select the group `walk` (5 frames + the mp4 if present). Read `TIMELINE`.
3. In the output panel: `OUTPUT NAME` = `walk-test`, `IMAGE HOLD (S)` = 0.5, `TRANSITION` =
   `CROSSFADE`, `CROSSFADE (S)` = 0.2, click `BUILD VIDEOS`.
4. Open the output folder (`viwo-data\merged\`).

Expected: 1: groups `walk (5)`, `run (3)`, `walk_ (2)` (prefix and suffix numbering both
detected), filter chips `ALL`, `IMG`, `VID`, `AUD`. 2: the timeline lists the items in numeric
order with thumbnails; `03_walk.png` and `03_walk.mp4` (same number) appear as one slot with the
video preferred and the note. 3: progress `RENDERING` with the rail `probe › encode › write`,
counters `VIDEOS WRITTEN 1`, `SECONDS ENCODED`; result lists `walk-test.mp4` with duration and a
player. 4: the mp4 plays; duration about `5 x 0.5 - 4 x 0.2` seconds (plus the clip length if
the mp4 was included).

## SQC-MERGE-02 (P0) CLI-free check of the ffmpeg command with the pinned build

Steps: in the activity console (`// ACTIVITY CONSOLE` at the bottom) read the `[MERGER]` lines of
the build.

Expected: the ffmpeg path is `third_party\ffmpeg\ffmpeg.exe` (unless a system ffmpeg is in
`[tools]`); the filter graph ends each input chain with `fps=30` before `xfade`; no
`Could not open encoder` error. Repeat the build with a system ffmpeg 7.x on PATH in `[tools]`:
same success.

## SQC-MERGE-03 (P1) Overlay audio, volume, hold last frame, fade-out

Steps: `OVERLAY AUDIO > BROWSE` = `C:\sqc\merger\loop.wav`, `VOLUME` 50 %, `HOLD LAST FRAME (S)`
1, `END FADE-OUT (S)` 0.5, `+ PART LOOP` once; build.

Expected: the output has an audio track (ffprobe: 2 streams), total length = frames + 1 s hold;
the audio fades at the end; a loop part repeats the overlay.

## SQC-MERGE-04 (P1) Trash inputs after build, undo from WORKSPACE

Steps: tick `trash inputs after build` (if present in the settings), build the `run` group.

Expected: the 3 frames move to `.trash\merger\`; `WORKSPACE` shows them in the trash section
with `RESTORE`.

## SQC-MERGE-05 (P1) Group with failures

Steps: replace `02_run.png` in the workspace with a 0-byte file; build `run`.

Expected: `GROUPS THAT FAILED` lists `run` with the ffmpeg message tail; other groups still
build; the toast says how many succeeded.

## SQC-MERGE-06 (P1) Long filter graph (many frames)

Steps: create 300 numbered PNGs in a workspace (`1..300 | % { Copy-Item 01_walk.png ("f_{0:000}.png" -f $_) }`),
build.

Expected: the build succeeds (the graph goes through `-filter_complex_script`, no `WinError 206`).

## SQC-MERGE-07 (P2) ffmpeg missing

Steps: remove `third_party\ffmpeg` and `third_party\ffprobe`, make sure no system ffmpeg is on
PATH, reload the page, `MERGER`.

Expected: the view shows the note `Some of this needs an optional tool. See SYSTEM for what to
install →`; `BUILD VIDEOS` gives the error box `TOOL NOT INSTALLED` with the link to SYSTEM.
Cleanup: SYSTEM > INSTALL both.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-MERGE-01 | | version: | | |
| SQC-MERGE-02 | | | | |
| SQC-MERGE-03 | | | | |
| SQC-MERGE-04 | | | | |
| SQC-MERGE-05 | | | | |
| SQC-MERGE-06 | | | | |
| SQC-MERGE-07 | | | | |
