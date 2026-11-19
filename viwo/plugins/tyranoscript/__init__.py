"""TyranoScript / TyranoBuilder games: HTML5/JS visual novels. The engine (`tyrano/`) and the
game data (`data/` with `data/scenario/*.ks` scenario scripts, `data/system/Config.tjs`, and
images / sound / video as plain files) sit loose on disk; the engine itself packs and encrypts
nothing. ViWo recognises the engine so its scripts and assets are surfaced as themselves (never
carved or misread), names the scenario scripts as its completeness claim, and the round trip
replaces an edited file loosely in the patched copy, which the engine reads straight from disk
(the "loose game files" row of doc 18.3).

A TyranoScript game shipped inside an Electron / NW.js shell (`app.asar`, `package.nw`) is
unpacked by the `electron` plugin first; wrapper re-detection (doc 3.1) then finds these loose
files and this plugin takes over. RPG Maker MV also ships `data/`, `index.html` and a shell, and
KiriKiri also uses `.ks` / `.tjs`, so detection keys on the web engine's own `tyrano/` folder,
not the shell or the extensions alone. No per-title logic: it holds for every TyranoScript game."""

from viwo.contracts.plugin import EnginePlugin, ExtractionContext, GameProbe, PluginManifest
from viwo.contracts.types import DetectionResult

MANIFEST = PluginManifest(
    "tyranoscript",
    "TyranoScript",
    "0.1.0",
    engine_type="tyranoscript",
    priority=12,
    description="TyranoScript / TyranoBuilder games: loose HTML5/JS data (scenario, assets)",
    capabilities=("detect", "inventory"),
)


class TyranoScriptPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        tyrano = probe.has_name("tyrano") or probe.has_name("libs.js", "tyrano.js")
        scenario = bool(probe.find("**/*.ks", 1))
        config = bool(probe.find("**/config.tjs", 1))
        evidence = []
        if tyrano:
            evidence.append("TyranoScript engine (tyrano/)")
        if scenario:
            evidence.append("scenario scripts (*.ks)")
        if config:
            evidence.append("TyranoScript config (Config.tjs)")
        strong = tyrano and (scenario or config or probe.has_name("index.html"))
        score = 0.9 if strong else (0.5 if tyrano else 0.0)
        return DetectionResult("tyranoscript", score, tuple(evidence), "tyranoscript")

    def inventory(self, ctx: ExtractionContext):
        if ctx.probe is None:
            return ()
        root = ctx.game_root
        return tuple(
            sorted(p.relative_to(root).as_posix() for p in ctx.probe.find("**/*.ks", 2000))
        )
