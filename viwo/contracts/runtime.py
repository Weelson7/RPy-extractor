"""Runtime agents (doc 11.2, rung D2): a pinned tool that runs inside the game (UE4SS, BepInEx)
and writes what static extraction cannot see (UE5 mappings, IL2CPP interop assemblies). It is
installed into a ViWo patched copy, never into the game folder; core launches that copy,
waits for `finished`, stops it and collects `outputs` into the workspace."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from .slots import Backend


class RuntimeAgent(Backend):
    """A backend in a `runtime.<engine>` slot, owned by that engine's plugin."""

    families = frozenset({"runtime"})

    def accepts(self, copy: Path, exe: Path) -> str:
        """ "" when this agent fits the game copy, else why not (shown to the user)."""
        return ""

    @abstractmethod
    def install(self, copy: Path, exe: Path, ctx) -> list[str]:
        """Put the agent and its settings into the copy (every first-run question pre-answered:
        no console, no dialog) and remove what a previous run left (a reused copy must not look
        finished); return the extra launch arguments (windowed, small)."""

    @abstractmethod
    def finished(self, copy: Path, exe: Path) -> bool:
        """True once the agent has written everything it was installed for."""

    @abstractmethod
    def outputs(self, copy: Path, exe: Path) -> list[Path]:
        """The files the agent wrote, inside the copy."""
