"""A Volatility 3 plugin ViWo loads in its volatility worker (memory.py; never in ViWo's own
process): every process of a guest RAM image with the root of its page tables (the DTB the live
page walk starts from), the paging mode, and every file mapped in it, whatever its kind (a native
module, a managed assembly, a shared object, a script runtime's archive). Windows: the loader's
list, then the file-backed VADs it does not list (a WoW64 process's 32-bit DLLs, mapped data).
Linux: the file-backed VMAs of the task's mm, grouped by file. One row per module; a process
with no readable module still gets one row (Module empty)."""

from volatility3.framework import exceptions, interfaces, renderers
from volatility3.framework.configuration import requirements
from volatility3.framework.layers import intel
from volatility3.framework.renderers import format_hints
from volatility3.plugins.linux import pslist as lpslist
from volatility3.plugins.windows import pslist

BAD = (exceptions.InvalidAddressException, AttributeError, TypeError, ValueError)


class Guest(interfaces.plugins.PluginInterface):
    """Processes with their DTB and mapped files, for ViWo's per-process live patching."""

    _required_framework_version = (2, 0, 0)
    _version = (1, 0, 0)

    @classmethod
    def get_requirements(cls):
        return [
            requirements.ModuleRequirement(
                name="kernel", description="OS kernel", architectures=["Intel32", "Intel64"]
            ),
            requirements.VersionRequirement(
                name="pslist", component=pslist.PsList, version=(3, 0, 0)
            ),
            requirements.VersionRequirement(
                name="lpslist", component=lpslist.PsList, version=(4, 0, 0)
            ),
            requirements.ListRequirement(
                name="pid", element_type=int, description="only these process ids", optional=True
            ),
        ]

    def _mode(self, layer) -> tuple[str, int]:
        if isinstance(layer, intel.Intel32e):
            return "x64", ~0xFFF
        if isinstance(layer, intel.IntelPAE):
            return "pae", ~0x1F
        return "x86", ~0xFFF

    @staticmethod
    def _win_dtb(proc) -> int:
        dtb = proc.Pcb.DirectoryTableBase
        if hasattr(dtb, "cast"):
            try:
                return int(dtb.cast("unsigned long long"))
            except (AttributeError, TypeError, exceptions.VolatilityException):
                pass
        return int(dtb)

    @staticmethod
    def _win_modules(proc):
        seen: set[int] = set()
        try:
            for entry in proc.load_order_modules():
                try:
                    base = int(entry.DllBase)
                    name, path = entry.BaseDllName.get_string(), entry.FullDllName.get_string()
                except BAD:
                    continue
                seen.add(base)
                yield name, base, int(entry.SizeOfImage), path
        except BAD:
            pass
        try:
            for vad in proc.get_vad_root().traverse():
                path, start = vad.get_file_name(), int(vad.get_start())
                if isinstance(path, str) and path and start not in seen:
                    seen.add(start)
                    name = path.replace("\\", "/").rsplit("/", 1)[-1]
                    yield name, start, int(vad.get_end()) - start + 1, path
        except BAD:
            pass

    def _windows(self, mode, mask, pids):
        for proc in pslist.PsList.list_processes(
            context=self.context,
            kernel_module_name=self.config["kernel"],
            filter_func=pslist.PsList.create_pid_filter(pids),
        ):
            try:
                pid, dtb = int(proc.UniqueProcessId), self._win_dtb(proc) & mask
                name = proc.ImageFileName.cast(
                    "string", max_length=proc.ImageFileName.vol.count, errors="replace"
                )
            except BAD:
                continue
            yield pid, name, dtb, list(self._win_modules(proc))

    def _linux_modules(self, task):
        spans: dict[str, list[int]] = {}
        try:
            for vma in task.mm.get_vma_iter():
                path = vma.get_name(self.context, task)
                if isinstance(path, str) and path.startswith("/"):
                    span = spans.setdefault(path, [int(vma.vm_start), int(vma.vm_end)])
                    span[0], span[1] = (
                        min(span[0], int(vma.vm_start)),
                        max(span[1], int(vma.vm_end)),
                    )
        except BAD:
            pass
        for path, (start, end) in sorted(spans.items(), key=lambda kv: kv[1][0]):
            yield path.rsplit("/", 1)[-1], start, end - start, path

    def _linux(self, layer, mask, pids):
        for task in lpslist.PsList.list_tasks(
            self.context, self.config["kernel"], lpslist.PsList.create_pid_filter(pids)
        ):
            try:
                if not task.mm:
                    continue  # a kernel thread: no user address space
                pid, name = int(task.pid), task.comm.cast("string", max_length=16, errors="replace")
                dtb = layer.translate(int(task.mm.pgd))[0] & mask
            except (*BAD, exceptions.VolatilityException):
                continue
            yield pid, name, dtb, list(self._linux_modules(task))

    def _generator(self):
        kernel = self.context.modules[self.config["kernel"]]
        layer = self.context.layers[kernel.layer_name]
        mode, mask = self._mode(layer)
        pids = self.config.get("pid", None)
        if kernel.has_type("_EPROCESS"):
            system, found = "windows", self._windows(mode, mask, pids)
        else:
            system, found = "linux", self._linux(layer, mask, pids)
        for pid, name, dtb, modules in found:
            head = (system, pid, name, format_hints.Hex(dtb), mode)
            for module, base, size, path in modules or [("", 0, 0, "")]:
                yield 0, (*head, module, format_hints.Hex(base), format_hints.Hex(size), path)

    def run(self):
        hexa = format_hints.Hex
        return renderers.TreeGrid(
            [("OS", str), ("PID", int), ("Process", str), ("DTB", hexa), ("Mode", str),
             ("Module", str), ("Base", hexa), ("Size", hexa), ("Path", str)],
            self._generator(),
        )  # fmt: skip
