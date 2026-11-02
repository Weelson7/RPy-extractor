"""Build the synthetic fixture folders used by the SQC suite (no real game data).

Run from the repository root, inside the venv where ViWo is installed:

    python sqc\\fixtures\\build_fixtures.py --out C:\\sqc
    python sqc\\fixtures\\build_fixtures.py --out C:\\sqc --only renpy zip-basic
    python sqc\\fixtures\\build_fixtures.py --list

Every fixture lands in <out>\\<name>\\ and is rebuilt from scratch (the folder is deleted first).
The byte builders are the repository's own test builders (tests/helpers.py and the engine
test modules), so the fixtures match what the automated tests use. Fake tools are small Python
scripts with a .cmd wrapper on Windows; their ini files land in <out>\\ini\\.

To use the fixtures on a machine without Python (portable bundle check), build them here and
copy the whole <out> folder over.
"""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.helpers import make_game, make_png, make_rar, make_tar, make_zip  # noqa: E402
from tests.test_carve import blob, jpeg, ogg_page, wav  # noqa: E402
from tests.test_doom import PALETTE, make_picture, make_sound, make_wad  # noqa: E402
from tests.test_formats import asar, ba2, bsa, vpk, xp3  # noqa: E402
from tests.test_godot import embed, make_pck  # noqa: E402
from tests.test_godot import fake_tools as godot_tools  # noqa: E402
from tests.test_renpy import make_rpa  # noqa: E402
from tests.test_rpgmaker import KEY as MV_KEY  # noqa: E402
from tests.test_rpgmaker import encrypt_mv, rgssad_v1, rgssad_v3  # noqa: E402
from tests.test_unreal import KEY as UE_KEY  # noqa: E402
from tests.test_unreal import key_exe, make_pak  # noqa: E402
from tests.test_unreal import fake_tools as unreal_tools  # noqa: E402

FIXTURES = {}


def fixture(name: str):
    def register(fn):
        FIXTURES[name] = fn
        return fn

    return register


def png(path: Path, size: int = 64, rgb=(255, 59, 59)) -> Path:
    return make_png(path, size, size, rgb)


def script_tool(folder: Path, name: str, body: str) -> Path:
    """A fake command-line tool: <name>.py, plus <name>.cmd on Windows. Returns the runnable."""
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / f"{name}.py"
    script.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    if sys.platform == "win32":
        wrapper = folder / f"{name}.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return wrapper
    return script


def ini(out: Path, name: str, body: str) -> Path:
    path = out / "ini" / f"{name}.ini"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# --- generic archives ------------------------------------------------------------------


@fixture("zip-basic")
def zip_basic(base: Path, out: Path) -> None:
    """game\\ : title.png, music\\theme.ogg (loose) and data.zip with img\\a.png + text\\readme.txt."""
    game = base / "game"
    png(game / "title.png")
    (game / "music").mkdir(parents=True)
    (game / "music" / "theme.ogg").write_bytes(ogg_page())
    a = png(base / "_src" / "a.png", 32, (0, 128, 255)).read_bytes()
    make_zip(game / "data.zip", {"img/a.png": a, "text/readme.txt": b"hello\r\n"})
    shutil.rmtree(base / "_src")


@fixture("nested-traversal")
def nested_traversal(base: Path, out: Path) -> None:
    """tests.helpers.make_game: bg.png, outer.zip > nested/inner.zip > voice/hello.ogg,
    extra.tar.gz with a "../escape.txt" member."""
    make_game(base)
    shutil.rmtree(base / "build")


@fixture("archives-all")
def archives_all(base: Path, out: Path) -> None:
    """game\\ : pack.tar.gz, pack.rar (RAR4 stored), pack.7z (only when py7zr is installed)."""
    game = base / "game"
    make_tar(game / "pack.tar.gz", {"tar/one.txt": b"one"})
    make_rar(game / "pack.rar", {"rar/two.txt": b"two"})
    try:
        import py7zr

        with py7zr.SevenZipFile(game / "pack.7z", "w") as sz:
            sz.writestr(b"three", "7z/three.txt")
    except ImportError:
        (base / "NO-7Z-README.txt").write_text(
            "py7zr is not installed: create pack.7z yourself with 7-Zip:\n"
            '  & "C:\\Program Files\\7-Zip\\7z.exe" a game\\pack.7z <a folder 7z\\three.txt>\n'
        )


@fixture("deep-nesting")
def deep_nesting(base: Path, out: Path) -> None:
    """game\\level00.zip holds level01.zip ... level12.zip holds deep.txt (13 zip levels)."""
    data = b"bottom of the well"
    inner = ("deep.txt", data)
    for level in range(12, -1, -1):
        path = base / "_build" / f"level{level:02d}.zip"
        make_zip(path, {inner[0]: inner[1]})
        inner = (path.name, path.read_bytes())
    (base / "game").mkdir()
    shutil.copy2(base / "_build" / "level00.zip", base / "game" / "level00.zip")
    shutil.rmtree(base / "_build")


@fixture("hostile-names")
def hostile_names(base: Path, out: Path) -> None:
    """game\\evil.zip and game\\evil.tar with traversal, absolute, drive-letter, device and
    unicode member names, plus a tar symlink and hardlink pointing outside."""
    import io
    import tarfile

    members = {
        "../escape-dotdot.txt": b"x",
        "..\\escape-backslash.txt": b"x",
        "/abs-root.txt": b"x",
        "C:/drive-abs.txt": b"x",
        "C:drive-rel.txt": b"x",
        "aux.txt": b"x",
        "sub/CON": b"x",
        "trailing-dot.": b"x",
        "trailing-space ": b"x",
        "stream.txt:hidden": b"x",
        "ok/normal.txt": b"normal",
        "\u30b2\u30fc\u30e0/\u753b\u50cf.txt": b"unicode",
    }
    game = base / "game"
    game.mkdir(parents=True)
    with zipfile.ZipFile(game / "evil.zip", "w") as zf:
        for name, data in members.items():
            zf.writestr(zipfile.ZipInfo(name), data)
    with tarfile.open(game / "evil.tar", "w") as tf:
        for name, data in (("../tar-escape.txt", b"x"), ("ok/tar-normal.txt", b"normal")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for kind, name, target in (
            (tarfile.SYMTYPE, "link-out", "../../../../Windows/win.ini"),
            (tarfile.LNKTYPE, "hard-out", "/etc/hostname"),
        ):
            info = tarfile.TarInfo(name)
            info.type, info.linkname = kind, target
            tf.addfile(info)


@fixture("encrypted-zip")
def encrypted_zip(base: Path, out: Path) -> None:
    """Instructions only: the standard library cannot write encrypted zips (7-Zip can)."""
    game = base / "game"
    game.mkdir(parents=True)
    (base / "_src").mkdir()
    (base / "_src" / "secret.txt").write_text("top secret")
    (base / "MAKE-ME.txt").write_text(
        "Run from this folder (needs 7-Zip):\n"
        '  & "C:\\Program Files\\7-Zip\\7z.exe" a -tzip -pSQC-PASS game\\locked.zip _src\\secret.txt\n'
        '  & "C:\\Program Files\\7-Zip\\7z.exe" a -t7z -pSQC-PASS -mhe=on game\\locked.7z _src\\secret.txt\n'
    )


@fixture("zip-bomb")
def zip_bomb(base: Path, out: Path) -> None:
    """game\\bomb.zip: one member of 1 GiB of zeros, about 1 MB on disk (streamed: no RAM spike)."""
    game = base / "game"
    game.mkdir(parents=True)
    chunk = bytes(1 << 20)
    with zipfile.ZipFile(game / "bomb.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        with zf.open("zeros.bin", "w", force_zip64=True) as fh:
            for _ in range(1024):
                fh.write(chunk)


# --- engines ---------------------------------------------------------------------------


@fixture("renpy")
def renpy(base: Path, out: Path) -> None:
    """Ren'Py layout: renpy\\, game\\script.rpy, game\\images.rpa (bg.png, theme.ogg, ../escape)."""
    game = base / "game"
    (game / "renpy").mkdir(parents=True)
    (game / "renpy" / "__init__.py").write_text("")
    (game / "game").mkdir()
    (game / "game" / "script.rpy").write_text('label start:\n    "Hello."\n')
    bg = png(base / "_src" / "bg.png").read_bytes()
    make_rpa(
        game / "game" / "images.rpa",
        {"images/bg.png": bg, "audio/theme.ogg": ogg_page(), "../escape.txt": b"bad"},
    )
    (game / "MyVN.exe").write_bytes(b"MZ" + b"\0" * 64)
    shutil.rmtree(base / "_src")


@fixture("godot")
def godot(base: Path, out: Path) -> None:
    """standalone\\game.pck, embedded\\Game.exe (PCK appended), encrypted\\data.pck (needs key),
    broken\\data.pck (main tool fails, spare works). Fake GDRE + GodotPckTool: ini\\godot-fake.ini."""
    (base / "standalone").mkdir(parents=True)
    (base / "standalone" / "game.pck").write_bytes(make_pck())
    (base / "embedded").mkdir()
    embed(base / "embedded" / "Game.exe", make_pck())
    (base / "encrypted").mkdir()
    (base / "encrypted" / "data.pck").write_bytes(make_pck(b"ENC"))
    (base / "broken").mkdir()
    (base / "broken" / "data.pck").write_bytes(make_pck(b"BROKEN"))
    tools = base / "_tools"
    tools.mkdir()
    ini(out, "godot-fake", godot_tools(tools))


@fixture("unreal")
def unreal(base: Path, out: Path) -> None:
    """plain\\ (unencrypted pak), keyinexe\\ (encrypted pak + key inlined in the shipping exe),
    locked\\ (encrypted pak, no key anywhere), iostore\\ (global.utoc/.ucas). Fake repak/retoc:
    ini\\unreal-fake.ini. The AES key for locked\\ is in unreal-key.txt."""
    for name in ("plain", "keyinexe", "locked"):
        (base / name / "Game" / "Content" / "Paks").mkdir(parents=True)
    make_pak(base / "plain" / "Game" / "Content" / "Paks" / "pakchunk0-Windows.pak")
    make_pak(base / "keyinexe" / "Game" / "Content" / "Paks" / "pakchunk0-Windows.pak", UE_KEY)
    exe = base / "keyinexe" / "Game" / "Binaries" / "Win64" / "Game-Win64-Shipping.exe"
    exe.parent.mkdir(parents=True)
    key_exe(exe, UE_KEY)
    make_pak(base / "locked" / "Game" / "Content" / "Paks" / "pakchunk0-Windows.pak", UE_KEY)
    from viwo.plugins.unreal.pak import UTOC_MAGIC

    io_dir = base / "iostore" / "Game" / "Content" / "Paks"
    io_dir.mkdir(parents=True)
    (io_dir / "global.utoc").write_bytes(UTOC_MAGIC + b"\0" * 100)
    (io_dir / "global.ucas").write_bytes(b"\0" * 64)
    (base / "unreal-key.txt").write_text("0x" + UE_KEY.hex() + "\n")
    tools = base / "_tools"
    tools.mkdir()
    ini(out, "unreal-fake", unreal_tools(tools))


@fixture("doom")
def doom(base: Path, out: Path) -> None:
    """game\\doom2.wad (IWAD: palette, picture, flat, sound, music, map, DEHACKED), game\\mod.wad
    (PWAD) and game\\broken.wad (bad directory)."""
    game = base / "game"
    game.mkdir(parents=True)
    make_wad(
        game / "doom2.wad",
        [
            ("PLAYPAL", PALETTE),
            ("TITLEPIC", make_picture()),
            ("DSPISTOL", make_sound(b"\x01\x02")),
            ("D_RUNNIN", b"MUS\x1a" + b"\0" * 12),
            ("DEHACKED", b"Patch File\n"),
            ("MAP01", b""),
            ("THINGS", b"\0" * 10),
            ("LINEDEFS", b"\0" * 14),
            ("F_START", b""),
            ("FLOOR0_1", bytes(4096)),
            ("F_END", b""),
            ("S_START", b""),
            ("TROOA1", make_picture()),
            ("S_END", b""),
        ],
        b"IWAD",
    )
    make_wad(game / "mod.wad", [("S_START", b""), ("POSSA1", make_picture()), ("S_END", b"")])
    (game / "broken.wad").write_bytes(b"PWAD" + struct.pack("<ii", 3, 999999))


@fixture("rpgmaker")
def rpgmaker(base: Path, out: Path) -> None:
    """xp\\Game.rgssad (v1), vxace\\Game.rgss3a (v3, with a ..\\ traversal entry),
    mv\\www\\ (System.json key + img\\faces\\Actor2.rpgmvp + audio\\bgm\\Theme.rpgmvo)."""
    face = png(base / "_src" / "face.png", 48).read_bytes()
    (base / "xp").mkdir(parents=True)
    (base / "xp" / "Game.rgssad").write_bytes(rgssad_v1({"Graphics\\Titles\\title.png": face}))
    (base / "xp" / "RGSS102E.dll").write_bytes(b"MZ")
    (base / "vxace").mkdir()
    (base / "vxace" / "Game.rgss3a").write_bytes(
        rgssad_v3({"Graphics\\Faces\\Actor1.png": face, "..\\evil.txt": b"x"})
    )
    www = base / "mv" / "www"
    for sub in ("data", "img/faces", "audio/bgm", "js"):
        (www / sub).mkdir(parents=True)
    (www / "data" / "System.json").write_text(
        json.dumps({"hasEncryptedImages": True, "hasEncryptedAudio": True, "encryptionKey": MV_KEY.hex()})
    )
    (www / "img" / "faces" / "Actor2.rpgmvp").write_bytes(encrypt_mv(face))
    (www / "audio" / "bgm" / "Theme.rpgmvo").write_bytes(encrypt_mv(ogg_page()))
    (www / "js" / "rpg_core.js").write_text("//")
    shutil.rmtree(base / "_src")


@fixture("kirikiri")
def kirikiri(base: Path, out: Path) -> None:
    """plain\\data.xp3 (2 plain entries) and mixed\\data.xp3 (1 plain + 1 encrypted entry)."""
    bg = png(base / "_src" / "bg.png").read_bytes()
    (base / "plain").mkdir(parents=True)
    (base / "plain" / "data.xp3").write_bytes(
        xp3([("bgimage/bg.png", bg, False), ("scenario/first.ks", b"*start\r\nHello", False)])
    )
    (base / "mixed").mkdir()
    (base / "mixed" / "data.xp3").write_bytes(
        xp3([("bgimage/bg.png", bg, False), ("bgimage/secret.png", bg, True)])
    )
    shutil.rmtree(base / "_src")


@fixture("electron")
def electron(base: Path, out: Path) -> None:
    """game\\resources\\app.asar (index.html, img\\logo.png) + game\\Game.exe and electron.exe marker;
    nw\\package.nw (a zip) + nw\\nw.exe marker."""
    logo = png(base / "_src" / "logo.png").read_bytes()
    res = base / "game" / "resources"
    res.mkdir(parents=True)
    (res / "app.asar").write_bytes(asar({"index.html": b"<html></html>", "img/logo.png": logo}))
    (base / "game" / "electron.exe").write_bytes(b"MZ")
    (base / "nw").mkdir()
    make_zip(base / "nw" / "package.nw", {"index.html": b"<html></html>", "img/logo.png": logo})
    (base / "nw" / "nw.exe").write_bytes(b"MZ")
    shutil.rmtree(base / "_src")


@fixture("source-vpk")
def source_vpk(base: Path, out: Path) -> None:
    """game\\pak01_dir.vpk (one inline file) + game\\pak01_000.vpk (one file in part 000)."""
    sky = png(base / "_src" / "sky.png").read_bytes()
    head, part = vpk({"materials/m.vmt": (b'"LightmappedGeneric" {}', 0), "materials/sky.png": (sky, 1)})
    (base / "game").mkdir(parents=True)
    (base / "game" / "pak01_dir.vpk").write_bytes(head)
    (base / "game" / "pak01_000.vpk").write_bytes(part)
    shutil.rmtree(base / "_src")


@fixture("bethesda")
def bethesda(base: Path, out: Path) -> None:
    """game\\Data\\Interface.bsa (v104, 2 files) and game\\Data\\Main - Misc.ba2 (GNRL, 1 file)."""
    data = base / "game" / "Data"
    data.mkdir(parents=True)
    (data / "Interface.bsa").write_bytes(bsa({"ui.txt": b"ui" * 10, "hud.txt": b"hud" * 10}))
    (data / "Main - Misc.ba2").write_bytes(ba2({"misc/notes.txt": b"notes" * 10}))


@fixture("overwatch")
def overwatch(base: Path, out: Path) -> None:
    """Markers only: Overwatch\\Overwatch.exe, .build.info, data\\casc\\ (no game data).
    Fake DataTool writes one PNG per mode: ini\\overwatch-fake.ini."""
    game = base / "Overwatch"
    (game / "data" / "casc").mkdir(parents=True)
    (game / "data" / "casc" / "data.000").write_bytes(b"\0" * 64)
    (game / "Overwatch.exe").write_bytes(b"MZ")
    (game / ".build.info").write_text("Branch!STRING:0\n")
    tool = script_tool(
        base / "_tools",
        "DataTool",
        "import sys\nfrom pathlib import Path\n"
        "game, mode, out = sys.argv[1:4]\n"
        "Path(out).mkdir(parents=True, exist_ok=True)\n"
        "(Path(out) / (mode + '.txt')).write_text('fake ' + mode)\n",
    )
    ini(out, "overwatch-fake", f"[tools]\ndatatool = {tool}\n")


@fixture("quickbms")
def quickbms(base: Path, out: Path) -> None:
    """game\\data.foo (custom format) + scripts\\foo.bms; fake quickbms copies the input to out\\.
    ini\\quickbms-fake.ini points [options.quickbms] scripts at scripts\\."""
    game = base / "game"
    game.mkdir(parents=True)
    (game / "data.foo").write_bytes(b"FOO1" + b"\0" * 60)
    scripts = base / "scripts"
    scripts.mkdir()
    (scripts / "foo.bms").write_text("# dummy script for the SQC fixture\nget SIZE asize\nlog \"inside.bin\" 0 SIZE\n")
    tool = script_tool(
        base / "_tools",
        "quickbms",
        "import sys, shutil\nfrom pathlib import Path\n"
        "args = [a for a in sys.argv[1:] if not a.startswith('-')]\n"
        "script, src, out = args[-3:]\n"
        "Path(out).mkdir(parents=True, exist_ok=True)\n"
        "shutil.copy(src, Path(out) / 'inside.bin')\n",
    )
    ini(out, "quickbms-fake", f"[tools]\nquickbms = {tool}\n\n[options.quickbms]\nscripts = {scripts}\n")


@fixture("unity-markers")
def unity_markers(base: Path, out: Path) -> None:
    """Detection only: game\\UnityPlayer.dll, game\\MyGame_Data\\globalgamemanagers (fake bytes).
    Real Unity extraction needs a real Unity game (see 04-extraction-per-engine)."""
    game = base / "game"
    (game / "MyGame_Data").mkdir(parents=True)
    (game / "UnityPlayer.dll").write_bytes(b"MZ")
    (game / "MyGame.exe").write_bytes(b"MZ")
    (game / "MyGame_Data" / "globalgamemanagers").write_bytes(b"\0" * 8)


# --- carver, survey, curation, merger --------------------------------------------------


@fixture("carve")
def carve(base: Path, out: Path) -> None:
    """game\\assets.bin: 16 known formats (png, jpg, gif, wav, wem, ogg, mid, mp4, bik, fsb, bnk,
    dds, glb, zip, 7z) between random bytes (tests.test_carve.blob, seed 7)."""
    data, _ = blob(base)
    (base / "game").mkdir(exist_ok=True)
    (base / "game" / "assets.bin").write_bytes(data)
    for leftover in base.glob("*.png"):
        leftover.unlink()


@fixture("library")
def library(base: Path, out: Path) -> None:
    """lib\\Doomish (IWAD + readme) and lib\\Odd (random secret.pak, structured assets.bin,
    extra.zip, Game.exe): tests.test_survey.make_library."""
    from tests.test_survey import make_library

    make_library(base)
    for leftover in base.glob("*.png"):
        leftover.unlink()


@fixture("dirty-workspace")
def dirty_workspace(base: Path, out: Path) -> None:
    """A ready ViWo workspace (ws\\ with the marker) for 08 CLEANUP and the sanitizer:
    empty file, Thumbs.db, .import junk, a PNG named .jpg, a duplicate, a truncated PNG."""
    from tests.test_sanitizer import make_workspace

    make_workspace(base)
    for leftover in ("real.png", "b.png"):
        (base / leftover).unlink(missing_ok=True)


@fixture("sort-game")
def sort_game(base: Path, out: Path) -> None:
    """game\\ with 3 PNG, 2 WAV, 1 TXT, 1 BIN and 1 JPG: extract it, then sort the workspace.
    Videos for the preview check come from ffmpeg (see 07-workspace-sort-trash)."""
    game = base / "game"
    for i, rgb in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255)), 1):
        png(game / "img" / f"pic{i}.png", 64 + 32 * i, rgb)
    (game / "snd").mkdir()
    for i in (1, 2):
        (game / "snd" / f"beep{i}.wav").write_bytes(_tone(440 * i))
    (game / "notes.txt").write_text("line 1\nline 2\nline 3\n")
    (game / "blob.bin").write_bytes(bytes(range(256)) * 4)
    (game / "photo.jpg").write_bytes(jpeg())


def _tone(freq: int, seconds: float = 1.0, rate: int = 22050) -> bytes:
    import io
    import math
    import wave

    frames = bytes(int(128 + 100 * math.sin(2 * math.pi * freq * i / rate)) for i in range(int(rate * seconds)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


@fixture("merger")
def merger(base: Path, out: Path) -> None:
    """game\\ with frames 01_walk..05_walk.png, 01_run..03_run.png, walk_01..walk_02.png and a
    same-number pair 03_walk.png + 03_walk.mp4 when ffmpeg is on PATH; loop.wav for the overlay."""
    game = base / "game"
    for i in range(1, 6):
        png(game / f"{i:02d}_walk.png", 64, (40 * i, 80, 160))
    for i in range(1, 4):
        png(game / f"{i:02d}_run.png", 64, (200, 40 * i, 40))
    for i in range(1, 3):
        png(game / f"walk_{i:02d}.png", 64, (20, 20, 100 * i))
    (base / "loop.wav").write_bytes(_tone(330, 3.0))
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        import subprocess

        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=64x64:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=880:duration=2", "-shortest", "-pix_fmt", "yuv420p",
             str(game / "03_walk.mp4")],
            check=True,
        )
    else:
        (base / "NO-FFMPEG.txt").write_text("ffmpeg not on PATH: 03_walk.mp4 was not made.\n")


@fixture("roundtrip")
def roundtrip(base: Path, out: Path) -> None:
    """One game per round-trip strategy: loose\\ (loose PNG + TXT), rpa\\ (Ren'Py images.rpa),
    zip\\ (data.zip), mv\\ (RPG Maker MV encrypted PNG). Godot and Unreal use the fixtures of
    the same name with their fake-tool ini."""
    pic = png(base / "_src" / "p.png").read_bytes()
    (base / "loose" / "img").mkdir(parents=True)
    (base / "loose" / "img" / "hero.png").write_bytes(pic)
    (base / "loose" / "readme.txt").write_text("original text\n")
    (base / "rpa" / "renpy").mkdir(parents=True)
    (base / "rpa" / "game").mkdir()
    make_rpa(base / "rpa" / "game" / "images.rpa", {"images/bg.png": pic, "script.txt": b"original"})
    make_zip(base / "zip" / "data.zip", {"img/a.png": pic, "cfg/settings.txt": b"original"})
    www = base / "mv" / "www"
    for sub in ("data", "img/faces", "js"):
        (www / sub).mkdir(parents=True)
    (www / "data" / "System.json").write_text(json.dumps({"encryptionKey": MV_KEY.hex()}))
    (www / "img" / "faces" / "Actor2.rpgmvp").write_bytes(encrypt_mv(pic))
    (www / "js" / "rpg_core.js").write_text("//")
    shutil.rmtree(base / "_src")


@fixture("capture")
def capture(base: Path, out: Path) -> None:
    """Capture policy games: clean\\Game.exe, anticheat\\Game.exe + EasyAntiCheat\\ folder,
    'Apex Legends'\\r5apex.exe (online title), plus ini\\capture-on.ini (features + capture)."""
    (base / "clean").mkdir(parents=True)
    (base / "clean" / "Game.exe").write_bytes(b"MZ" + b"\0" * 64)
    (base / "anticheat" / "EasyAntiCheat").mkdir(parents=True)
    (base / "anticheat" / "Game.exe").write_bytes(b"MZ" + b"\0" * 64)
    (base / "Apex Legends").mkdir()
    (base / "Apex Legends" / "r5apex.exe").write_bytes(b"MZ" + b"\0" * 64)
    (base / "outside.exe").write_bytes(b"MZ" + b"\0" * 64)
    ini(out, "capture-on", "[startup]\nfeatures = extraction, sorting, merger, capture\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, help="folder that receives one sub-folder per fixture")
    ap.add_argument("--only", nargs="*", help="fixture names (default: all but zip-bomb)")
    ap.add_argument("--list", action="store_true", help="list the fixtures and exit")
    args = ap.parse_args()
    if args.list or not args.out:
        for name, fn in FIXTURES.items():
            print(f"{name:18} {' '.join((fn.__doc__ or '').split())}")
        return 0
    names = args.only or [n for n in FIXTURES if n != "zip-bomb"]
    unknown = [n for n in names if n not in FIXTURES]
    if unknown:
        print(f"unknown fixture(s): {', '.join(unknown)}; see --list", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    for name in names:
        base = args.out / name
        if base.exists():
            shutil.rmtree(base)
        base.mkdir(parents=True)
        FIXTURES[name](base, args.out)
        print(f"built {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
