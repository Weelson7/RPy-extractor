"""Signing a rebuilt APK, a separate process: uber-apk-signer (Apache-2.0, one jar, run on the
pinned JDK; it aligns with its bundled zipalign, signs v1/v2/v3 with apksigner and verifies).
The user's keystore when `[options.android]` names one (its passwords from the user, never logged
nor written), else the tool's debug key. Android installs an APK signed by another key only after
the original app is removed: said every time the debug key is used. No tool: the APK is left
unsigned and aligned, and that is said too."""

import shutil
import tempfile
from pathlib import Path

from viwo.contracts.plugin import masked
from viwo.contracts.types import DependencySpec

SIGNER = DependencySpec.of("uber-apk-signer")
UNSIGNED = (
    "left UNSIGNED: Android refuses to install it until it is signed "
    "(`viwo install uber-apk-signer`, or sign it with your own apksigner)"
)
DEBUG = (
    "signed with a debug key: Android installs it only after the original app is uninstalled "
    "(its data goes with it), and it can never update the store's version"
)
TIMEOUT = 900


def _keystore(settings: dict) -> tuple[list[str], list[str], str]:
    """(signer arguments, the secrets in them, why the user's keystore cannot be used or "")."""
    store = str(settings.get("keystore") or "")
    if not store:
        return [], [], ""
    alias = str(settings.get("key_alias") or "")
    password = str(settings.get("keystore_password") or "")
    key_password = str(settings.get("key_password") or password)
    if not Path(store).is_file() or not alias or not password:
        return [], [], "the keystore option needs an existing file, key_alias and its password"
    args = ["--ks", store, "--ksAlias", alias, "--ksPass", password, "--ksKeyPass", key_password]
    return args, [password, key_password], ""


def _hidden(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = masked(text, secret)
    return text


def sign(apk: Path, ctx, settings: dict) -> list[str]:
    """Sign `apk` in place; the notes that say how (or why not)."""
    tool = ctx.os.tools.locate(SIGNER)
    if tool is None:
        return [UNSIGNED]
    args, secrets, refused = _keystore(settings)
    if refused:
        return [f"{refused}: {UNSIGNED}"]
    ctx.scratch.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="sign-", dir=ctx.scratch))
    try:
        argv = [*tool.argv_prefix, "-a", str(apk), "--allowResign", "-o", str(out), *args]
        ctx.log(f"Signing {apk.name} (uber-apk-signer)", stage="repack")
        result = ctx.os.process.run(argv, timeout=TIMEOUT, cancel=ctx.cancel)
        signed = sorted(out.glob("*.apk"))
        if not result.ok or len(signed) != 1:
            why = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["no output"]
            return [f"signing failed ({_hidden(why[0], secrets)[:200]}): {UNSIGNED}"]
        shutil.copyfile(signed[0], apk)  # the scratch folder may be on another drive
    finally:
        shutil.rmtree(out, ignore_errors=True)
    return [f"signed with the keystore {Path(args[1]).name}"] if args else [DEBUG]
