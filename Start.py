import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    app = root / "RPy-extrcactor" / "extract.py"
    
    if not app.exists():
        print(f"[ERROR] Missing app file: {app}")
        return 1

    args = sys.argv[1:]
    cmd = [sys.executable, str(app), *args]
    
    print(f"[LAUNCH] Root: {root}")
    print(f"[LAUNCH] App: {app}")
    print(f"[LAUNCH] Args: {' '.join(args) if args else '(none)'}")
    print(f"[LAUNCH] Cmd: {' '.join(cmd)}")
    print("[LAUNCH] Starting RPy Extractor...")
    
    exit_code = subprocess.call(cmd, cwd=str(root))
    
    if exit_code == 0:
        print("[LAUNCH] ✓ RPy Extractor exited cleanly")
    else:
        print(f"[LAUNCH] ✗ RPy Extractor exited with code {exit_code}")
    
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
