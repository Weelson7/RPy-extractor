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
| `views/home.js` | the three arm homes: each arm's end-to-end path, every step SHIPPED or ROADMAP |
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
- `themes/<name>.css`: tokens (`--bg`, `--red`, `--text`, `--line`, `--f-head`, `--f-body`,
  `--f-mono`...) plus every colour, font, glow, border, transition and keyframe. It must not
  contain layout declarations (`display`, `grid-template*`, `position`).
- Shipped themes: `wormhole` (the red terminal HUD) and `plain` (neutral, high contrast, no
  motion). The active theme is `<html data-theme>` and the `#theme-link` stylesheet; the user
  picks it in SETTINGS > APPEARANCE (a browser preference, `pref("theme")`, not an ini key).

To write a theme: copy `themes/plain.css`, change the `:root` tokens first (that alone restyles
everything), then override component skins (`.panel`, `.btn`, `.badge[data-kind="ok"]`...).
Keep layout out of it; the lint test checks every file under `themes/`.

To add a component: put it in `ui/components.js` (or a new `ui/<area>.js` re-exported from
`ui/index.js`), give it a class name and data attributes for its states, add its structure to
`base.css` and its skin to every theme.

## Arms and the global strip

Every view declares an `arm`: `static` (the game is not running: survey, extract, workspace, sort,
cleanup, merger, analysis), `dynamic` (it runs: capture, runtime), `patching` (you change its
content: patched copy, patches + mods) or `global`. The rail shows one arm at a time, opening on
that arm's home (`#static`, `#dynamic`, `#patching`); the arm switch sits above it. The global
views (SYSTEM, JOBS, SETTINGS) sit in the strip of the top bar with the shared GAME selector and
the WORKSPACE; opening one keeps the arm you were in. The game selector is one browser
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
  `D0`… in DYNAMIC, `P0`… in PATCHING (the arm home is 0) and `00`, `01`, `02` for the global
  views (SYSTEM, JOBS, SETTINGS), from the arm and the place in it at render time; an add-on view
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

## Tests

- `tests/test_ui_lint.py` (L0, no browser): the rules above, on every view, `base.css` and
  every theme.
- `tests/test_ui_smoke.py` (L6): starts a server with a temp workspace and a synthetic game,
  drives a headless browser through `tests/ui/smoke.mjs`, and asserts zero console errors on
  every view, no literal null text, the toast at the top right under the bar, the computed tab codes, the SYSTEM gap, the SETTINGS formats
  table width, the theme switch, detect percentages without zero padding, the visible "skipped"
  rail stage after an extraction, workspace-wide type counts in SORT, and the cleanup scan as
  a visible job. Skipped when no Chromium or Node is found; `VIWO_UI=0` disables it;
  `VIWO_UI_OUT=<folder>` keeps the screenshots.
