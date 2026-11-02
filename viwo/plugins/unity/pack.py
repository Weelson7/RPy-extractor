"""Unity round trip with UnityPy: TextAsset text (exact) and Texture2D images (stored as
lossless RGBA32) written back into the copied container, then read back to verify."""

from __future__ import annotations

import gc
from pathlib import Path

from viwo.contracts.slots import Packer
from viwo.contracts.types import Outcome, OutcomeKind

from .exporters import UNITYPY

RGBA32 = 4  # UnityPy TextureFormat.RGBA32


def _objects(unitypy, path: Path) -> tuple[object, dict]:
    env = unitypy.load(str(path))
    return env, {str(o.path_id): o for o in env.objects}


def _apply(obj, source: Path) -> None:
    data = obj.parse_as_object()
    if obj.type.name == "TextAsset":
        data.m_Script = source.read_bytes().decode("utf-8", "surrogateescape")
    elif obj.type.name == "Texture2D":
        from PIL import Image

        with Image.open(source) as img:
            data.set_image(img.convert("RGBA"), target_format=RGBA32)
    else:
        raise ValueError(f"{obj.type.name} cannot be written back yet")
    data.save()


def _same(obj, source: Path) -> bool:
    data = obj.parse_as_object()
    if obj.type.name == "TextAsset":
        script = data.m_Script
        raw = (
            script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
        )
        return raw == source.read_bytes()
    from PIL import Image

    with Image.open(source) as img:
        return data.image.convert("RGBA").tobytes() == img.convert("RGBA").tobytes()


class UnityPyPacker(Packer):
    backend_id, owner, license = "unitypy-pack", "unity", "MIT"

    def dependencies(self):
        return (UNITYPY,)

    def pack(self, container, members, ctx) -> Outcome:
        try:
            import UnityPy
        except ImportError:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNITYPY.hint)
        try:
            env, objects = _objects(UnityPy, container)
            for member, source in members.items():
                if member not in objects:
                    raise ValueError(f"object {member} not found in {container.name}")
                _apply(objects[member], source)
            payload = next(iter(env.files.values())).save(packer="original")
            del env, objects
            gc.collect()  # release the file before overwriting it (Windows)
            container.write_bytes(payload)
        except Exception as exc:  # UnityPy raises many types on unsupported data
            return Outcome(OutcomeKind.FAILED, error=f"{type(exc).__name__}: {exc}"[:300])
        return Outcome(OutcomeKind.OK, len(members))

    def verify(self, output: Path, members: dict[str, Path], ctx) -> list[str]:
        import UnityPy

        _, objects = _objects(UnityPy, output)
        bad = [m for m, src in members.items() if m not in objects or not _same(objects[m], src)]
        gc.collect()
        return bad
