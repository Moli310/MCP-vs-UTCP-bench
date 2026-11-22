"""Checks everything the project needs, with a clear fix for anything missing."""
import platform
import sys
import urllib.request
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "iam.db"
HISTORY_PATH = ROOT / "results" / "history.xlsx"
API_URL = "http://127.0.0.1:8000/openapi.json"
PACKAGES = ["mcp", "fastapi", "uvicorn", "utcp", "utcp-http", "utcp-mcp", "openpyxl"]
INSTALL_HINT = r".venv\Scripts\python -m pip install -r requirements.txt"


def api_running():
    try:
        with urllib.request.urlopen(API_URL, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def file_is_locked(path):
    """True if another program (such as Excel) has the file open."""
    if not path.exists():
        return False
    try:
        with open(path, "r+b"):
            return False
    except PermissionError:
        return True


def run_checks():
    """Returns a list of (check, passed, how to fix, required)."""
    checks = [
        ("Python 3.10 or newer", sys.version_info >= (3, 10),
         f"You have Python {platform.python_version()}. Install 3.10 or newer from python.org.", True),
        ("Running inside .venv", sys.prefix != sys.base_prefix,
         "Press Ctrl+Shift+P, run 'Python: Select Interpreter' and choose .venv.", True),
    ]
    for name in PACKAGES:
        try:
            checks.append((f"Package {name} {metadata.version(name)}", True, "", True))
        except metadata.PackageNotFoundError:
            checks.append((f"Package {name}", False, f"Install the packages: {INSTALL_HINT}", True))
    checks.append(("results/history.xlsx is closed", not file_is_locked(HISTORY_PATH),
                   "Close results/history.xlsx in Excel.", True))
    checks.append(("Database data/iam.db", DB_PATH.exists(),
                   "Run task '1. Seed database' (task 5 does this for you).", False))
    checks.append(("REST API on port 8000", api_running(),
                   "Run task '2. Start REST API (Path B)' (task 5 does this for you).", False))
    return checks


def print_report(checks):
    for name, passed, fix, required in checks:
        tag = "OK  " if passed else ("FAIL" if required else "NOTE")
        print(f"[{tag}] {name}")
        if not passed:
            print(f"       -> {fix}")
    failed = [c for c in checks if c[3] and not c[1]]
    if failed:
        print(f"\n{len(failed)} required check(s) failed. Fix them, then try again.")
        return False
    print("\nAll required checks passed.")
    return True


if __name__ == "__main__":
    sys.exit(0 if print_report(run_checks()) else 1)