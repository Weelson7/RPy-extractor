# Plugins: built-in discovery and drop-in modules

ViWo hardcodes no plugin list. Every engine plugin is a module with a manifest, found in one of
three places, and known by the id in its manifest:

| Source | Where | Enabled by |
|--------|-------|------------|
| Built-in | every package under `viwo/plugins/<name>/` | on by default; `[plugins] <id> = off` disables it |
| Drop-in | every folder with a `plugin.json` under a folder listed in `[plugins] custom_dirs` | opt-in: `[plugins] <id> = on` (or `custom.<id> = on`), or `"enabled": true` in `plugin.json` |
| Installed package | the `viwo.plugins` entry-point group (`pip install` a plugin package) | same as drop-ins |

`generic` is always on. A broken plugin disables only itself; the reason appears in the startup
notes (`viwo info`, SYSTEM > STARTUP NOTES). The registry lives in
`viwo/core/wiring/registry.py`.

## Built-ins

`registry.BUILTIN_PLUGINS` is computed at import time by scanning `viwo/plugins/`: each package is
imported, its plugin class is the one named by the module-level `PLUGIN = "ClassName"` marker (or
the single `EnginePlugin` subclass defined in the module when there is no marker), and the id is
`manifest.plugin_id`. The folder name should equal the id; a mismatch is reported as a startup
problem and the manifest id wins. Adding a built-in = adding a folder.

**Game plugins** (doc 2.10): what one title adds on top of its engine lives in a game plugin under
that engine, `viwo/plugins/<engine>/games/<game>/`, whose manifest names the engine (`engine =
"redengine"`). An engine plugin keeps what holds for every game on the engine and detects by
the engine's own file signatures; a game plugin detects its title (its executables), runs only
with its engine, and offers what the engine's backends read from `ctx.games` (REDengine reads
`name_lists`). Adding a title's tooling = adding a folder under its engine's `games/`.

The distro profiles come from the plugins too (`viwo/core/wiring/distros.py`): a built-in that
names a `profile` in its manifest gets its own (`renpy`, `unity`, `unreal` and `godot` do), which
enables only it; `custom` enables every other built-in and `mixed` everything. Core lists no
engine: a new plugin with a profile gets its two distro files from `viwo config generate`. Commented `[tools]` examples come from each dependency's
own executable and install-folder names.

## Writing a drop-in plugin

Folder layout (see `examples/plugins/hello/`, a `.hello` archive that is a zip with another name):

```text
user_plugins/                 <- listed in startup.ini: [plugins] custom_dirs = user_plugins
  hello/
    plugin.json               <- manifest (below)
    __init__.py               <- the module named by "module" (a .py file or a package folder)
```

`plugin.json`:

```json
{
  "id": "hello",                      // slug: [a-z][a-z0-9_-]*; not mixed/auto/core/none
  "name": "Hello (example)",
  "version": "0.1.0",
  "contract": "1.0",
  "module": "__init__",               // file (without .py) or package folder inside this folder
  "class": "HelloPlugin",             // an EnginePlugin subclass in that module
  "requires": { "viwo": ">=1.0" },    // >=, <=, ==, >, < against the running ViWo version
  "enabled": false,                   // default when the ini does not mention the id
  "override": false                   // true: replace a built-in that has the same id
}
```

`"entry": "module:Class"` (doc 2.8) is accepted in place of `module` + `class`.

The class (contract in `viwo/contracts/plugin.py` and `viwo/contracts/slots.py`):

```python
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

MANIFEST = PluginManifest("hello", "Hello", "0.1.0", engine_type="hello", builtin=False)

class HelloPlugin(EnginePlugin):
    manifest = property(lambda self: MANIFEST)
    def detect(self, probe: GameProbe) -> DetectionResult: ...   # confidence 0..1 + evidence
    def configure(self, options) -> None: ...                     # [options.hello] keys
    def slot_definitions(self): ...                               # SlotDefinition per format
    def backends(self): ...                                       # Unarchiver / Exporter / Packer
```

Rules that apply to drop-ins exactly as to built-ins:

- `manifest.plugin_id` must equal `id` in `plugin.json`; set `builtin=False` so the UI shows
  "ADDED BY YOU".
- A slot id is `<family>.<name>` and must not clash with another plugin's slot; a backend id must
  be unique. Clashes are reported and the later one is ignored.
- Every write into a folder built from archive member names goes through
  `viwo.contracts.workspace.safe_member` (traversal, drive letters, links).
- External tools are declared with `DependencySpec` and located through `ctx.os.tools.locate`,
  never by a hardcoded path; GPL/AGPL tools run as separate processes.
- Options come from `[options.<id>]`; secrets travel with the request, never in the ini.
- Trust: a drop-in runs inside the app with your permissions. Load only what you trust.

## Testing a plugin

Use the fake-tool pattern from `tests/test_godot.py` (`fake_tools`: a `.py` script plus a `.cmd`
wrapper on Windows) and `tests.helpers.runtime(root, ini_body)` to boot a runtime from an ini
that lists your `custom_dirs`, then run `viwo.core.pipeline.runner.extract` on a synthetic game
folder. `tests/test_registry.py` shows the end-to-end case for the example plugin.

## Checking a configuration

`viwo config check startup.ini` knows every id from the built-ins, the `custom_dirs` manifests
and the entry points, so `[plugins] hello = on` is valid as soon as the folder exists.

## Add-ons: CLI commands and UI components

A plugin, built-in or drop-in, can ship its own `viwo` subcommands and its own web UI pieces.
Nothing is hardcoded: the registry collects them at boot, and ids allow overrides.

### CLI commands

```python
from viwo.contracts.plugin import CliCommand

def build(parser):                      # the argparse subparser: add arguments
    parser.add_argument("archive", type=Path, help="a .hello archive")

def run(rt, args) -> dict:              # the runtime and the parsed args; return envelope data
    return {"members": [...]}

class HelloPlugin(EnginePlugin):
    def cli_commands(self):
        return (CliCommand("hello-list", "list the members", build, run,
                           formatter=lambda d: "\n".join(d["members"])),)
```

- `viwo hello-list x.hello` runs it; `--json` prints the usual envelope; without a `formatter`
  the human output is readable JSON. Errors raise `ViwoError` like core commands (same exit codes).
- Drop-ins must opt in with `"cli": true` in `plugin.json` (a command runs with your rights);
  built-ins and installed packages (entry points) are trusted.
- A name that already exists (a core command, or another plugin's) is refused and reported in
  the startup notes, unless the command sets `override=True`: then it replaces the original.
- `viwo -h` lists add-ons with the plugin id in brackets. The runtime boots before parsing so
  the add-ons are known; bare `viwo` (no arguments) stays fast.

### UI components

A plugin declares one ES module, served as `/plugins/<id>/ui.js` (`"ui": "ui.js"` in
`plugin.json`, or `EnginePlugin.ui_module()`; the default is a `ui.js` next to the plugin's
code). Extra files (styles, images) are served only from the `ui/` folder next to that module:
`/plugins/<id>/ui/<file>`, with strict path containment. The web app loads every module listed
by `GET /api/ui-modules` after its own views and calls the default export:

```js
export default function install({ registry, api, ui }) {
  registry.registerPanel("system", { id: "hello", order: 900, render: (host) => { ... } });
  registry.registerView({ id: "hello", order: 200, title: "HELLO", subtitle: "example add-on",
    mount(root) { ... }, show() {}, hide() {} });
}
```

- `registry.registerView(view, { override })` adds a view to the rail (ordered by `order`);
  `registry.registerPanel(viewId, panel, { override })` adds a panel inside an existing view.
  An existing id is refused unless `override: true`, then the add-on replaces it.
- `ui` is the component library (`h`, `panel`, `btn`, `badge`, `table`...), `api` the API client.
  Use only components from `ui`: styling belongs to the theme layer, never to add-on code.
- Trust: a UI module runs in the page with the API token. Load only what you trust.

`examples/plugins/hello/` shows both: `viwo hello-list` and `ui.js` (a panel in SYSTEM and a
HELLO view), with `ui/hello.css` as an extra asset.
