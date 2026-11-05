"""Core round-trip packers: zip containers rebuilt with edited members replaced."""

import os
import zipfile

from viwo.contracts.slots import Packer
from viwo.contracts.types import Outcome, OutcomeKind


class ZipPacker(Packer):
    backend_id, license = "zip-packer", "PSF-2.0"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def pack(self, container, members, ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            with zipfile.ZipFile(container) as src, zipfile.ZipFile(temp, "w") as out:
                for info in src.infolist():
                    data = (
                        members[info.filename].read_bytes()
                        if info.filename in members
                        else src.read(info)
                    )
                    out.writestr(info, data, compress_type=info.compress_type)
                for name in sorted(set(members) - set(src.namelist())):
                    out.write(members[name], name, compress_type=zipfile.ZIP_DEFLATED)
            os.replace(temp, container)
        except (OSError, zipfile.BadZipFile) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return Outcome(OutcomeKind.OK, len(members))
