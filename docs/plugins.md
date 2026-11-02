# Plugins: built-in discovery and drop-in modules

ViWo hardcodes no plugin list. Every engine plugin is a module with a manifest, found in one of
three places, and known by the id in its manifest:

| Source | Where | Enabled by |
|--------|-------|------------|
| Built-in | every package under `viwo/plugins/<name>/` | on by default; `[plugins] <id> = off` disables it |
| Drop-in | every folder with a `plugin.json` under a folder listed in `[plugins] custom_dirs` | opt-in: `[plugins] <id> = on` (or `custom.<id> = on`), or `"enabled": true` in `plugin.json` |
| Installed package | the `viwo.plugins` entry-point group (`pip install` a plugin package) | same as drop-ins |

`generic` is always on. A broken plugin disables only itself; the reason appears in the startup
notes (`viwo info`, 05 SYSTEM > STARTUP NOTES). The registry lives in
`viwo/core/wiring/registry.py`.

## Built-ins

`registry.BUILTIN_PLUGINS` is computed at import time by scanning `viwo/plugins/`: each package is
imported, its plugin class is the one named by the module-level `PLUGIN = "ClassName"` marker (or
the single `EnginePlugin` subclass defined in the module when there is no marker), and the id is
`manifest.plugin_id`. The folder name should equal the id; a mismatch is reported as a startup
problem and the manifest id wins. Adding a built-in = adding a folder.

The distro profiles are derived the same way (`viwo/core/wiring/distros.py`): `mixed` enables
everything, an engine profile (`renpy`, `unity`, `unreal`, `godot`) enables that engine, and
`custom` enables every other built-in. Commented `[tools]` examples come from each dependency's
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
