# The web UI: functional layer, style layer, add-ons

The UI is plain ES modules served by `viwo serve` (no build step). It is split into a
**functional layer** (JavaScript that builds semantic components and talks to the API) and a
**style layer** (CSS tokens and skins). The boundary is enforced by `tests/test_ui_lint.py`;
the real-browser behaviour by `tests/test_ui_smoke.py` (headless Edge or Chrome over the
DevTools protocol, driven by `tests/ui/smoke.mjs`).

## Functional layer (`viwo/web/js/`)

| Module | Role |
|--------|------|
| `ui/dom.js` | `h` (element builder, text only, never innerHTML), `fill`, `add`, `cssVar`, `stagger`, `state`, `busy`, formatting, `pref`, the `bus` |
| `ui/components.js` | `panel`, `viewHead`, `stat`, `badge`, `btn`, `goBtn`, `seg`, `toggle`, `field`, `table`, `meter`, `stackBar`, `bars`, `progressBar` + `setProgress`, `empty`, `alert`, `kv`, `list`, `rail`, `assure`, `toolLink` |
| `ui/feedback.js` | `errorBox` (+ the `ERRORS` table), `toast`, `toastErr`, `modal`, `confirmBox`, `promptBox`, `browseBtn`, `openBtn` |
| `ui/log.js` | `logLine`, `logView`, `lineLevel` |
| `ui.js` | the same surface, re-exported (views import `../ui.js`) |
| `registry.js` | views and panels as contributions (below); `ARMS`, `armViews(arm)` |
| `game.js` | the shared game selector: `currentGame`, `setGame`, `pickGame`, `gameField`, `followGame` |
| `views/home.js` | the three arm homes: each arm's end-to-end path, every step SHIPPED or ROADMAP; the steps one tab runs share its row (the tab's title, one line per step), so a code is shown once per home and names one view |
| `theme.js` | `THEMES`, `setTheme`, `currentTheme` |
| `progress.js` | `jobProgress(kind)`: the live job block (rail, counters, ticker, log) per job kind |
| `views/*.js` | one module per view; each registers itself |

Rules for views (the lint fails otherwise):

- No `style:` props, no `.style.`, no `innerHTML`. Numeric visuals go through a component
  (`meter`, `setProgress`, `stackBar`, `bars`) or `cssVar(el, name, value)`, which sets a CSS
  custom property the theme reads (`--p`, `--w`, `--h`, `--i`, `--n`).
- Visual state is a data attribute, never an ad-hoc class: `data-state` (idle, running, done,
  fail, on, out, locked, flat, syncing...), `data-kind` (ok, warn, err, mute, live, hi, lo...),
  `data-level` on log lines, `data-s` on rail stages, `data-type` on asset tags, `data-key` on
  category parts, `data-reveal` for the entrance animation.
- Class strings name components and layout helpers only (`panel`, `row`, `col`, `grid2`,
  `mono`, `dim`, `small`, `note`, `lbl`...). A colour or size word in a class is a lint error.
- Never `node.append(maybeNull)`: a null child renders the word "null". Use `h(...)` children,
  `fill(node, ...)` or `add(node, ...)`, which drop null and false.

## Style layer (`viwo/web/css/`)

- `base.css`: structure only. Layout, spacing, sizes, grid templates, clip paths, visibility.
  It must not contain colours, fonts, shadows or animations (lint).
- `skin.css`: the skin every theme shares (rules written only with the tokens), loaded after
  `base.css` and before the theme, so a theme's own rules win. Same rule as a theme: no layout.
- `themes/<name>.css`: tokens (`--bg`, `--red`, `--text`, `--line`, `--f-head`, `--f-body`,
  `--f-mono`...) plus the colours, fonts, glows, borders, transitions and keyframes that are
  the theme's own. It must not contain layout declarations (`display`, `grid-template*`,
  `position`).
- Shipped themes: `wormhole` (the red terminal HUD) and `plain` (neutral, high contrast, no
  motion). The active theme is `<html data-theme>` and the `#theme-link` stylesheet; the user
  picks it in SETTINGS > APPEARANCE (a browser preference, `pref("theme")`, not an ini key).

To write a theme: copy `themes/plain.css`, change the `:root` tokens first (that alone restyles
everything with `skin.css`), then override component skins (`.panel`, `.btn`,
`.badge[data-kind="ok"]`...). Keep layout out of it; the lint test checks every file under
`themes/` and `skin.css`.

To add a component: put it in `ui/components.js` (or a new `ui/<area>.js` re-exported from
`ui/index.js`), give it a class name and data attributes for its states, add its structure to
`base.css` and its skin to `skin.css` (or to every theme, when the themes differ).

## Arms and the global strip

Every view declares an `arm`: `static` (the game is not running: survey, extract, workspace,
search, sort, cleanup, merger, analysis), `dynamic` (it runs: capture, runtime), `patching` (you change its
content: patched copy, assets, patches + mods) or `global`. The rail shows one arm at a time, opening on
that arm's home (`#static`, `#dynamic`, `#patching`); the arm switch sits above it. The global
views (SYSTEM, WORKBOOKS, RUNBOOKS, SETTINGS) sit in the strip of the top bar with the job chip,
the shared GAME selector and the WORKSPACE; opening one keeps the arm you were in. JOBS has no
chip of its own: the job chip (RUNNING or JOB IDLE) opens it (`strip: false` in its
registration; its panels carry its `tag`, JOB). WORKBOOKS (doc
19.1) shows one step at a time and remembers the step reached per workbook (`pref("wb.<id>")`);
the HOW TO buttons in ANALYSIS, RUNTIME and CAPTURE open it on one tool (`pref("wbTool")`,
`howToBtn(tool)`), a runbook step on one workbook (`workbookBtn(id)`). RUNBOOKS (doc 19.2) runs
one step per request (`/api/runbooks/step`), waits for DONE, CONTINUE on a step you do, keeps
each runbook's input values (`pref("rb.<id>.<name>")`; a secret input's value stays in the page
only). Each step is a readable row (`runbook-step.js`): an action
says what it runs (the job and the tab that runs it), its target (the game, folder or target
key) and its options as key/value, each `{name}` with the run's value beside it (a secret
input's shows as `<secret>`, an empty one as "not set yet"); the step as the file holds it is
behind its JSON toggle. EDIT opens the structured step editor (`runbook-edit.js`): the
id/title/summary, the inputs (a secret toggle, a default unless secret), and the steps (add,
remove, reorder; each step's kind, an action's job and its target and options as typed key/value
with a secret-referencing value masked, or a step you do with its text and workbook). The runbook
as JSON stays a toggle away as an escape hatch, editable and kept in sync through one working
copy; SAVE validates on the server and a rule error shows inline (no step is dropped). Its RECORD A WORKFLOW panel (`recording.js`, doc 19.3)
drives the server's recorder; while it records, the status strip shows a REC chip with the
steps caught so far, whatever view is open; a replayed step that answers otherwise than
recorded pauses as DIFFERS: YOUR CALL with what changed. The game selector is one browser
preference (`gamePath`): views read it, write it through `setGame` and follow the `game` event.

## Add-ons: views and panels as contributions (`registry.js`)

```js
import { registerView, registerPanel } from "./registry.js";
registerView({ id: "mygame", arm: "static", order: 75, title: "MY GAME", subtitle: "what it does", mount(root) {...}, show() {...}, hide() {...} });
registerPanel("system", { id: "mygame-status", order: 10, render: (ctx) => panel("", "MY GAME", null, ...) });
```

- `main.js` builds one `<section id="view-<id>">` per registered view and the rail of the
  current arm, sorted by `order` within the arm. A view without `arm` joins `static`.
- Codes are computed, never written: `code(id)` in `registry.js` gives `S0`, `S1`… in STATIC,
  `D0`… in DYNAMIC, `P0`… in PATCHING (the arm home is 0) and `00`, `01`… for the global
  views of the strip (SYSTEM, WORKBOOKS, RUNBOOKS, SETTINGS), from the arm and the place in it at
  render time (a view with `strip: false` has its `tag` instead); an add-on view
  or a new `order` renumbers everything. The visible panels of a view are lettered A, B, C… in
  reading order (again when one appears, hides or comes from a plugin), so `<code>.<letter>` is
  always current. Prose names a tab by its title only ("SYSTEM"), never by a number.
- `#<view>@<word>` opens a view at the panel whose title starts with that word and stays on it
  while the view loads (the FORMATS chip opens `#system@formats`). A view that registers an existing id must pass
  `{ override: true }`; the same holds for panels.
- Views that accept panels call `addonPanels(viewId, ctx)` at mount and append the result.
- Plugin UI modules: the server lists them at `GET /api/ui-modules` as `{modules: [{plugin,
  url}]}`; `main.js` imports each module before building the shell and calls its
  `default install({ registry, api, ui, plugin })`. A missing route or a broken module is logged
  and skipped; the app always starts. A drop-in plugin ships its module as a static file in its
  own folder; the server serves it under the URL it lists.

## Previews (SORT)

A type pick in the queue (IMG, AUD, VID, 3D, TXT, BIN) lists that type over the whole
workspace: the server pages the picked types (`/api/assets-window?types=model`), so the
models of a 24,800-file workspace start on the first page. The server keeps the queue
between requests while no folder of the workspace changes; the page shows only the answer
to the latest pick.

The stage's figure carries `data-kind` (`img`, `vid`, `aud`, `mdl`, `txt`, `bin`): the size
rules of `base.css` select on it, so a picture, a video or a model fills the panel and
follows the window. A `.glb` or `.gltf` file opens in `<model-viewer>` (pinned, Apache-2.0,
installed into `third_party/` by itself the first time a model is opened and served by ViWo from `/vendor/`; nothing comes from a CDN,
except that a model packed with Draco, Basis (KTX2) or meshopt makes the viewer fetch its
decoder from the internet): drag to orbit, wheel to zoom. The preview route reads the model's
JSON (a `.glb`'s JSON chunk, a `.gltf`'s text) and answers `needsNetwork` and `decoders`; when
the model is packed, one short line under it says so ("Packed with Draco: the viewer fetches
its decoder from the internet to show it."). A `.gltf` that keeps buffers or textures in other
files cannot load from the preview route; a `.glb` holds everything. Without the viewer
installed the stage says how to install it.

## Action bars and button rows

A view that runs one thing ends with an action bar (`.actionbar`): a summary line, the reason
the primary action cannot run yet (`.ab-why`, empty when it can) and the primary button,
disabled until it can (ASSETS' WRITE, PATCHED COPY, CLEANUP, MERGER's BUILD VIDEOS).
ANALYSIS: TARGETS lists the binaries with a pick per row (`pref("anTarget")`; the first with an
analyzer when the remembered one is not listed); ANALYZE in the bar runs the picked target and
says why it waits (enter the game folder, list the targets, analysis is off, pick a target, no
analyzer for it yet); CANCEL joins it while a run goes. A target's extra slots (EMULATE,
SOLVE...) and CONTINUE IN GHIDRA stay on its row; VERSION DIFF keeps its COMPARE.
SEARCH (doc 6.7): WHERE takes a folder or one file (THE WORKSPACE, THE GAME fill it), WHAT
picks TEXT (ANY CASE), NUMBER (the integer widths) or BYTES and the caps; SEARCH in the bar says
why it waits (where, what, a search running). HITS lists file, offset, the encoding, the
section/RVA/VA in an executable and the bytes around the match; COPY PATCH copies the hit as a
patch set entry (its unique AOB when it has one, else its offset) with `patched` left to fill.
CLEANUP: SCAN's panel lists every recipe of doc 5.1 as a radio (`views/cleanup-recipes.js`,
`pref("cleanupRecipe")`), each marked LOSSLESS or LOSSY, with its phase and rule count or why
it cannot act now (no lossless decoder, no ffmpeg); SCAN runs the picked one. A plan's
`warnings` stand above the findings. Findings are ticked for you except report-only and LOSSY
ones (tick those yourself); the bar counts trash, rename, copy and LOSSY copy; an applied row
says what it became (RENAMED, IN TRASH, COPY MADE, LOSSY COPY MADE), and LAST CLEANUP lists
each file with what it became and counts the copies UNDO removes.

Spacing between buttons is `base.css`'s, never a view's: buttons in a `.row` keep its gap, and a
row of buttons right after a note, a field, a table or another row inside a panel body, a
notice or a plain block stands 14 px clear of it (a flex or grid container keeps its own gap).
The smoke test measures it on every view.

## Merger (STATIC)

GROUPS lists the names that hold several numbered files (tick one, it becomes a video). A name
with one file comes after, in one SINGLE FILES list with the count, each with its path and type
and as tickable as a group (a file alone goes on the timeline by itself or beside the groups). The server answers the groups of several files first and
counts the rest (`singleCount`), so the first page holds the merges; the header says groups,
single files and files.

## Assets (PATCHING)

ASSETS (`views/assets.js`) is the way back for what ViWo decoded (doc 18.3). MOD OR OVERWRITE
is the run's choice (`seg`, default MOD, `pref("assetsMode")`), with what each means; PLAN asks
`POST /api/repack {plan: true, mode}` and lists the edited files of the active workspace by
container: per decoded file the member it becomes, the encoder (slot and backend) and the
member it replaces, then the files edited as they are and the members removed; each container
carries its MOD or OVERWRITE badge, its packer and the reason (an engine with one form says
which one is used and why). CANNOT GO BACK lists every edited file without a way back, with its
reason. WRITE runs the same request with `out` (the patched-copy folder PATCHED COPY uses for
the workspace, `pref("repackOut:<ws>")`) as a `repack` job and shows the verify result per
container; it stays disabled, with the reason beside it, until a plan has something to write
and a folder is chosen.
PATCHED COPY plans and writes with the same choice and names it in its summary line
(`MOD (set in ASSETS)`).

## Feedback

- An error toast stays until it is dismissed (DISMISS) or the user changes view; an
  information toast leaves by itself. Toasts never cover what is under them for the pointer.
- The log dock is polled open or closed: closed, its handle shows the last line, so what the
  server last said is on every view.
- Up to 1500 px wide the strip keeps its codes and counters and drops the labels, so the top
  bar never wraps.
- A button that started work says so while it runs (CONVERTING…, SCANNING…) and an empty or
  unchanged workspace folder is answered in words before any request leaves.

## Tests

- `tests/test_ui_lint.py` (L0, no browser): the rules above, on every view, `base.css` and
  every theme.
- `tests/test_ui_smoke.py` (L6): starts a server with a temp workspace and a synthetic game,
  drives a headless browser through `tests/ui/smoke.mjs`, and asserts zero console errors on
  every view, no literal null text, the toast at the top right under the bar, the computed tab codes, the SYSTEM gap, the SETTINGS formats
  table width, the theme switch, detect percentages without zero padding, the visible "skipped"
  rail stage after an extraction, workspace-wide type counts in SORT, the cleanup scan as
  a visible job, and ASSETS' mod/overwrite choice (MOD first) and a plan with WRITE held
  back while nothing was edited; on every view, buttons with their spacing and step codes shown
  once; MERGER's single files under SINGLE FILES, tickable; ANALYZE held back with its reason; SEARCH
  held back with its reason and its TEXT/NUMBER/BYTES switch;
  each runbook step readable with its JSON behind a closed toggle; and the runbook step editor
  (EDIT, ADD STEP, a title and an option typed in, SAVE) round-tripping on reload with a boolean
  option kept and an untouched step preserved. Skipped when no Chromium or Node is found; `VIWO_UI=0` disables it;
  `VIWO_UI_OUT=<folder>` keeps the screenshots.
