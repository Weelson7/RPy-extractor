"""The memory ceiling of ViWo's own process (doc 9.2 `memory_limit`, default 50 % of the
machine). A damaged or hostile file can make a reader ask for more memory than the machine has
(a Unity object read with a layout that does not fit asked for 15 GB in three seconds and took
the PC down, twice): past the ceiling the allocation fails inside ViWo, as one counted failure.
An engineering property, so it is an option: `memory_limit = 0` lifts it."""


def guard(rt) -> tuple[str, bool]:
    """Set the ceiling once per process; (what to say, whether it holds or was switched off)."""
    percent, total = rt.config.memory_limit, rt.os.memory_bytes()
    if not percent:
        return "memory ceiling off ([startup] memory_limit = 0)", True
    if not total:
        return "no memory ceiling: this OS layer cannot tell the machine's memory", False
    ceiling = total * percent // 100
    why = rt.os.limit_memory(ceiling)
    if why:
        return f"no memory ceiling: {why}", False
    size = f"{ceiling / (1 << 30):.1f} GB ({percent} % of the machine)"
    return f"memory ceiling for ViWo's own process: {size}", True
