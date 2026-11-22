"""One click: check setup, create the database and start the API if needed, run the benchmark."""
import asyncio
import subprocess
import sys
import time

import check_setup
from shared.utcp_templates import ROOT

API_COMMAND = [sys.executable, "-m", "uvicorn", "path_b_utcp.api:app",
               "--host", "127.0.0.1", "--port", "8000",
               "--no-access-log", "--log-level", "warning"]


def wait_for_api(timeout_seconds=30):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if check_setup.api_running():
            return True
        time.sleep(0.5)
    return False


def main():
    print("Step 1 of 4: checking setup\n")
    if not check_setup.print_report(check_setup.run_checks()):
        return 1

    if check_setup.DB_PATH.exists():
        print("\nStep 2 of 4: database found")
    else:
        print("\nStep 2 of 4: creating the database")
        from data.seed_synthetic_iam import main as seed_database
        seed_database()

    api = None
    if check_setup.api_running():
        print("\nStep 3 of 4: REST API already running, using it")
    else:
        print("\nStep 3 of 4: starting the REST API")
        api = subprocess.Popen(API_COMMAND, cwd=str(ROOT))
        if not wait_for_api():
            print("The REST API did not start within 30 seconds.")
            api.terminate()
            return 1

    try:
        print("\nStep 4 of 4: running the benchmark\n")
        from bench.run_bench import main as run_benchmark
        asyncio.run(run_benchmark())
        return 0
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 1
    finally:
        if api is not None:
            api.terminate()
            try:
                api.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api.kill()
            print("Stopped the REST API.")


if __name__ == "__main__":
    sys.exit(main())