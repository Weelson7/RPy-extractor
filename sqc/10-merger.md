# 10 Merger

Area code `MERGE`. Fixture: `merger` (frames `01_walk..05_walk.png`, `01_run..03_run.png`,
`walk_01..02.png`, `03_walk.mp4` when ffmpeg was on PATH, `loop.wav`). Extract it first:
`viwo extract C:\sqc\merger\game --workspace C:\sqc\_ws\merge --on-existing replace`, switch the
UI workspace to it. Needs ffmpeg + ffprobe. Outputs go to `[server] merged`
(`viwo-data\merged\`). API form: `GET /api/media-merger/state`, `POST /api/media-merger/list
{namingPattern, includeFiles}`, `POST /api/media-merger/build {transitionType, diapoDelay,
fadeCrossTime, endFadeoutTime, endLastImageTime, overlaySound, overlayVolume, outputName,
trashAfterBuild, namingPattern, selectedCandidates: [{name, entiretyTimes, partLoops}]}`.

## SQC-MERGE-01 (P0) Groups, timeline, one build

Steps:
1. `MERGER`. Read `GROUPS` (pattern `number-to-name`, then `name-to-number`).
2. Tick the group `walk`. Read the timeline.
3. In `VIDEO SETTINGS`: `TRANSITION` = `CROSSFADE`, `IMAGE HOLD (S)` 0.5, `CROSSFADE (S)` 0.2,
   `OUTPUT NAME` = `walk-test`; `BUILD VIDEOS`.
4. Probe the output (`ffprobe`), play it.

Expected: 1: `number-to-name` gives `run (3)`, `walk (5 indexes, 6 files)` and the singles
`walk_01`, `walk_02` (`fileCount 11`, `totalCount 4`, `singleCount 2`); `name-to-number` groups
`walk_01..02` as `walk (2)`. 2: the timeline lists the items in numeric order with thumbnails;
`03_walk.png` and `03_walk.mp4` share index 03 (a conflict the card shows). 3: progress
`RENDERING…`, then `1 VIDEO(S) BUILT`; the result `walk-test_walk.mp4` with `6 CLIPS` and its
duration; the log `[MERGER:MERGE] Probing 6 input(s) for walk-test_walk.mp4`, `Encoding 3.5 s of
video with ffmpeg`, `Wrote walk-test_walk.mp4`. 4: `h264` video + `aac` audio, 3.5 s (5 images
x 0.5 + the 2 s clip - 5 x 0.2); it plays.

## SQC-MERGE-02 (P0) The ffmpeg command with the pinned build

Steps: in the activity console (`// ACTIVITY CONSOLE`) or `viwo-data\logs\viwo-<date>.log` read
the `[MERGER:MERGE]` lines of the build; repeat the build with a system ffmpeg 7.x in `[tools]`.

Expected: the ffmpeg used is the pinned one (`third_party\ffmpeg\ffmpeg.exe`, or the `[tools]`
one); no `Could not open encoder` error; with ffmpeg 7.x the same success.

## SQC-MERGE-03 (P1) Overlay audio, volume, hold last frame, fade-out, part loop

Steps: `OVERLAY AUDIO` = `C:\sqc\merger\loop.wav` (`BROWSE` or typed), `VOLUME` 50 %, `HOLD LAST
FRAME (S)` 1, `END FADE-OUT (S)` 0.5, a part loop on indexes `1-2` twice; build `walk`.

Expected: the output has a video and an audio track (ffprobe: `h264`, `aac`); duration 4.5 s
(the 3.5 s of SQC-MERGE-01 plus the 1 s hold); the audio fades at the end. The overlay formats
listed under the field are `.aac .aif .aiff .flac .m4a .mid .midi .mp3 .ogg .opus .wav .wma`.

## SQC-MERGE-04 (P1) Trash inputs after build, restore from WORKSPACE

Steps: tick `Move merged source files to the workspace trash after a successful build`, build the
`run` group; open WORKSPACE.

Expected: the result shows `3 TRASHED`; the 3 frames are in `.trash\merger\`; WORKSPACE counts
them (`IN TRASH 3`) and its `RESTORE` on `.png` brings them back (`GET /api/status` lists them in
`trashed`; `POST /api/restore {"folder": "png"}` restores them).

## SQC-MERGE-05 (P1) A group that fails

Steps: replace `png\02_run.png` in the workspace with a 0-byte file; build `run` and `walk` together.

Expected: `walk` builds; `GROUPS THAT FAILED` lists `run` with the ffmpeg message tail (`Error
opening input file ...\02_run.png ... Invalid data found when processing input`); the toast says
how many were built (`Built 1 video(s).`, `Some candidates failed.`); the answer has `partial:
true`.

## SQC-MERGE-06 (P1) Long filter graph (many frames)

Steps: 300 numbered PNGs in a workspace (`1..300 | % { Copy-Item png\01_walk.png ("png\f_{0:000}.png" -f $_) }`),
pattern `name-to-number`, group `f (300)`, `CROSSFADE`, hold 0.1, crossfade 0.04; build.

Expected: the build succeeds (the graph goes through `-filter_complex_script`, no `WinError
206`): one output with 300 clips, 45.05 s.

## SQC-MERGE-07 (P2) ffmpeg missing

Steps: remove `third_party\ffmpeg` and `third_party\ffprobe`, make sure no system ffmpeg is on
PATH, reload the page, `MERGER`.

Expected: `GET /api/media-merger/state` has no `encoder`; the action bar reads `install ffmpeg
(<SYSTEM tab>)` and `BUILD VIDEOS` is disabled. Cleanup: SYSTEM > INSTALL both.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-MERGE-01 | PASS API; NOT RUN UI | version: 1.36.0+search+apk (unreleased). Pinned ffmpeg 6.1.1 via real-tools.ini; groups as written; `walk-test_walk.mp4`, `mergedCount 6`, `totalDuration 3.5`, ffprobe `video:h264, audio:aac`, 3.500000 s | agent | 2026-11-23 |
| SQC-MERGE-02 | PASS log; NOT RUN ffmpeg 7.x | the log lines as written; no encoder error; no system ffmpeg 7.x here | agent | 2026-11-23 |
| SQC-MERGE-03 | PASS API (audio fade not heard) | `walk-audio_walk.mp4`, `h264` + `aac`, 4.500000 s; the fade-out needs ears | agent | 2026-11-23 |
| SQC-MERGE-04 | FAIL | `trashedCount 3`, the frames in `.trash\merger\`; but `/api/status` shows `trashed {}` (only `groups` and `items` are counted) and `RESTORE` on png answers `Nothing of png in the trash`: WORKSPACE neither shows nor restores them; `IN TRASH 0` also leaves `CLEAR TRASH` disabled, although clearing would delete them | agent | 2026-11-23 |
| SQC-MERGE-05 | PASS API; NOT RUN UI | `partial: true`, `walk.mp4` built, `run` failed with `Error opening input file ...\02_run.png. ... Invalid data found when processing input` (the tail begins inside ffmpeg's build banner) | agent | 2026-11-23 |
| SQC-MERGE-06 | PASS API | `many_f.mp4`, `mergedCount 300`, `totalDuration 45.05` | agent | 2026-11-23 |
| SQC-MERGE-07 | NOT RUN | would need the pinned ffmpeg removed and none on PATH | | |
