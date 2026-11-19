"""PLAN of the round trip (doc 18.3): which container each edit goes into, by which packer, and
whether as a **mod** (what the engine loads over its own files: an override archive, loose files
it reads first) or by **overwriting** the container in the patched copy. Where an engine offers
only one of the two, the item says which one is used and why. An edited decoded file carries its
way back (roundtrip_encode.Way): the member it becomes, the encoder, and a member it replaces."""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .pipeline.identify import identify

MODES = ("mod", "overwrite")
CORE_PACK = {"unarchive.zip": "pack.zip"}


@dataclass
class PlanItem:
    container: str  # game-relative; "" for loose files
    slot: str  # "override" or a pack.* slot
    members: dict[str, Path | None] = field(default_factory=dict)  # None: removed (a drop)
    untouched: dict[str, str] = field(default_factory=dict)  # member -> original sha256
    mode: str = ""  # mod | overwrite: what this item does to the game's own files
    why: str = ""
    ways: dict = field(default_factory=dict)  # member -> Way (an edited decoded file)


def _pack_slot(rt, match) -> str:
    if match is None:
        return ""
    owner = rt.slots[match.slot_id].owner
    if owner == "core":
        return CORE_PACK.get(match.slot_id, "")
    plugin = rt.plugins.get(owner)
    return plugin.pack_slot(match.slot_id) if plugin else ""


def _slot_of(rt, game: Path, container: str, owner: str) -> tuple[str, str, object]:
    """(pack slot or "", why there is none, the plugin that owns the container or None)."""
    if owner:  # exported by a plugin: its packer writes straight into the container
        plugin = rt.plugins.get(owner)
        return (plugin.pack_slot("exported") if plugin else ""), "", plugin
    match = identify(game / container, rt.slots.values())
    plugin = rt.plugins.get(rt.slots[match.slot_id].owner) if match else None
    if match is not None and match.embedded:
        return "", "no packer for this container (yet)", plugin
    return _pack_slot(rt, match), "", plugin


def _put(item: PlanItem, member: str, edit) -> None:
    item.members[member] = edit.file
    if edit.way is not None:
        item.ways[member] = edit.way


def _loose_item(edits) -> PlanItem | None:
    loose = PlanItem("", "override")
    for edit in edits:
        _put(loose, edit.member, edit)
        if edit.way is not None and edit.way.drop:  # e.g. the .rpyc an edited .rpy replaces
            loose.members[edit.way.drop] = None
    if not loose.members:
        return None
    if any(e.kind == "loose" for e in edits):
        loose.mode, loose.why = "overwrite", "loose game files, replaced in the copy"
    else:
        loose.mode, loose.why = "mod", "new files added to the copy"
    if any(m is None for m in loose.members.values()):
        loose.mode, loose.why = "overwrite", f"{loose.why}; a replaced file is removed"
    return loose


def plan(rt, game: Path, edits: list, originals=None, mode: str = "mod"):
    """(items, warnings). originals: container -> {member: sha256} of the extraction, for the
    untouched check. mode: `mod` or `overwrite`, followed where the engine offers both."""
    groups = defaultdict(list)
    for edit in (e for e in edits if e.kind in ("member", "exported")):
        groups[(edit.container, edit.plugin)].append(edit)
    loose = [e for e in edits if e.kind in ("loose", "added")]
    items, warnings = [], []
    for (container, owner), group in sorted(groups.items()):
        slot, why, plugin = _slot_of(rt, game, container, owner)
        binding = rt.bindings.get(slot)
        if not slot:
            warnings.append(f"{container}: {why or 'no packer for this container (yet)'}")
        elif binding is None or not binding.bound:
            warnings.append(f"{container}: {slot} has no available backend (see `viwo slots`)")
        else:
            got, extra = _container(rt, (container, slot, plugin), group, originals, mode)
            items += got
            warnings += extra
    head = _loose_item(loose)
    return ([head] if head else []) + items, warnings


def _container(rt, where: tuple, group: list, originals, mode: str):
    """The items of one container: its packer's, and loose files where the engine loads them
    over it (`mod`); (items, warnings)."""
    container, slot, plugin = where
    packer = rt.backends.get(rt.bindings[slot].main)
    root = plugin.loose_root(container) if plugin is not None else None
    item, warnings, moved = PlanItem(container, slot), [], PlanItem("", "override")
    for edit in group:
        if edit.way is not None and edit.way.drop:  # a new member that replaces another
            if root is None or not getattr(packer, "drops", False):
                warnings.append(f"{edit.way.derived}: {container} cannot lose {edit.way.drop}")
                continue
            _put(moved, f"{root}/{edit.member}".lstrip("/"), edit)
            item.members[edit.way.drop] = None
        else:
            _put(item, edit.member, edit)
    item.mode, item.why = _mode(container, packer, root, mode)
    if item.mode == "mod" and root is not None:  # Ren'Py: loose files over the archive
        for member in [m for m, f in item.members.items() if f is not None]:
            moved.members[f"{root}/{member}".lstrip("/")] = item.members.pop(member)
            if member in item.ways:
                moved.ways[f"{root}/{member}".lstrip("/")] = item.ways.pop(member)
    kept = (originals or {}).get(container, {})
    item.untouched = {m: h for m, h in kept.items() if m not in item.members}
    if moved.members:
        moved.mode, moved.why = "mod", f"loose files in {root or '.'}/, loaded over {container}"
    if item.members:  # only the drops are left: the container still loses them
        item.mode, item.why = _dropping(item, container)
    return [i for i in (moved, item) if i.members], warnings


def _dropping(item: PlanItem, container: str) -> tuple[str, str]:
    if all(f is None for f in item.members.values()):
        gone = ", ".join(sorted(item.members))
        return "overwrite", f"{container} rewritten without {gone}: the stale member must not win"
    return item.mode, item.why


def _mode(container: str, packer, root, asked: str) -> tuple[str, str]:
    """What one container's edits do: mod or overwrite, and why (said when not as asked)."""
    if getattr(packer, "override", False):
        why = f"a separate file the engine loads over {container}"
        return "mod", why + ("; this engine has no rewrite of it" if asked == "overwrite" else "")
    if asked == "mod" and root is not None:
        return "mod", f"loose files the engine loads over {container}"
    why = f"{container} rewritten in the copy"
    if asked == "mod":
        why += ": the engine loads nothing over it, so there is no mod form"
    return "overwrite", why


def describe(items: list[PlanItem]) -> list[dict]:
    """The plan as the report and the UI show it: per item what each edited file becomes."""
    return [
        {
            "container": i.container,
            "slot": i.slot,
            "members": sorted(m for m, f in i.members.items() if f is not None),
            "drops": sorted(m for m, f in i.members.items() if f is None),
            "mode": i.mode,
            "why": i.why,
            "ways": [w.shown(m) for m, w in sorted(i.ways.items())],
        }
        for i in items
    ]
