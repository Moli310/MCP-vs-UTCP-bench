"""Benchmarks Paths A, B and C on identical tools.

Each run:
  1. checks that the REST API is running and history.xlsx is closed
  2. adds the previous run to history.xlsx if it never got there
  3. checks that all paths return the same data, and measures sizes (bench/extras.py)
  4. times every tool on every path
  5. replaces results/bench_results.csv and adds this run to results/history.xlsx
"""
import asyncio
import csv
import logging
import random
import statistics
import sys
import time
from datetime import datetime

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from utcp.utcp_client import UtcpClient

from bench import history
from bench.extras import collect_extras
from check_setup import HISTORY_PATH, api_running, file_is_locked
from shared.utcp_templates import API_TEMPLATE, MCP_TEMPLATE, ROOT

# Silence INFO logs from all libraries, so no path pays for printing to the console
logging.disable(logging.INFO)

N_CALLS = 200  # timed calls per tool
RUNS = 3       # full repeats; path order is shuffled each run
CASES = [      # (tool name, arguments), identical for every path
    ("find_identity", {"name": "Ann"}),
    ("get_entitlements", {"user_id": "U1001"}),
    ("find_orphaned_accounts", {}),
]
CSV_PATH = ROOT / "results" / "bench_results.csv"


def ms_since(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


async def bench(call):
    await call()  # warm-up, not timed
    times = []
    for _ in range(N_CALLS):
        t0 = time.perf_counter()
        await call()
        times.append(ms_since(t0))
    return statistics.median(times), statistics.quantiles(times, n=20)[18]  # median, p95


async def run_path_a(run, rows):
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "path_a_mcp.mcp_server"], cwd=str(ROOT))
    t0 = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool(*CASES[0])
            cold = ms_since(t0)
            for tool, args in CASES:
                med, p95 = await bench(lambda t=tool, a=args: session.call_tool(t, a))
                rows.append([run, "A_mcp", tool, med, p95, cold])


async def run_utcp_path(run, rows, label, template, prefix):
    t0 = time.perf_counter()
    client = await UtcpClient.create(config={"manual_call_templates": [template]})
    await client.call_tool(prefix + CASES[0][0], CASES[0][1])
    cold = ms_since(t0)
    for tool, args in CASES:
        med, p95 = await bench(lambda t=prefix + tool, a=args: client.call_tool(t, a))
        rows.append([run, label, tool, med, p95, cold])


PATHS = {
    "A_mcp": run_path_a,
    "B_utcp_http": lambda run, rows: run_utcp_path(
        run, rows, "B_utcp_http", API_TEMPLATE, "sql_api."),
    "C_utcp_mcp_bridge": lambda run, rows: run_utcp_path(
        run, rows, "C_utcp_mcp_bridge", MCP_TEMPLATE, "sql_mcp.iam."),
}


def preflight():
    if not api_running():
        print("The REST API is not running. Start task '2. Start REST API (Path B)',")
        print("or use task '5. Run everything', which starts it for you.")
        sys.exit(1)
    if file_is_locked(HISTORY_PATH):
        print("results/history.xlsx is open in Excel. Close it, then run the task again.")
        sys.exit(1)
    history.add_csv_if_missing(CSV_PATH)


async def check_before_timing():
    print("Checking that all paths return the same data...")
    extras = await collect_extras(CASES)
    for tool, check in extras["correctness"].items():
        size = extras["response_bytes"][tool]
        status = "OK" if check["match"] else "MISMATCH"
        print(f"  {tool:<24} {check['rows']:>4} rows  {status:<8}  "
              f"REST {size['rest_body']:>7,} bytes   MCP {size['mcp_message']:>7,} bytes")
    sizes = ", ".join(f"{path} {value:,} bytes" if value is not None else f"{path} not available"
                      for path, value in extras["tool_description_bytes"].items())
    print(f"  Tool descriptions: {sizes}")

    if not extras["all_match"]:
        print("\nThe paths returned different data, so the benchmark has stopped.")
        print("Speed comparisons only mean something when every path gives the same answer.")
        sys.exit(1)
    print("All paths agree. Starting the timed runs.\n")
    return extras


def build_rows(session_id, timing_rows, extras):
    """One CSV row per run, path and tool, with this session's extra measurements."""
    packages = extras["environment"]["packages"]
    rows = []
    for run, path, tool, med, p95, cold in timing_rows:
        size = extras["response_bytes"][tool]
        is_rest = path == "B_utcp_http"  # A and C both receive the same MCP message
        rows.append({
            "session_id": session_id, "run": run, "path": path, "tool": tool,
            "median_ms": round(med, 2), "p95_ms": round(p95, 2), "cold_start_ms": round(cold, 2),
            "rows_returned": size["rows"],
            "response_bytes": size["rest_body"] if is_rest else size["mcp_message"],
            "mcp_text_blocks": None if is_rest else size["mcp_text_blocks"],
            "mcp_structured_copy": None if is_rest else size["mcp_has_structured_copy"],
            "tool_description_bytes": extras["tool_description_bytes"].get(path),
            "all_paths_agree": extras["all_match"],
            "python_version": extras["environment"]["python"],
            "mcp_version": packages.get("mcp"),
            "utcp_version": packages.get("utcp"),
            "utcp_http_version": packages.get("utcp-http"),
            "utcp_mcp_version": packages.get("utcp-mcp"),
        })
    return rows


def write_csv(rows):
    CSV_PATH.parent.mkdir(exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=history.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


async def main():
    preflight()
    session_id = datetime.now().strftime(history.SESSION_FORMAT)
    extras = await check_before_timing()

    timing = []
    for run in range(1, RUNS + 1):
        order = list(PATHS)
        random.shuffle(order)
        print(f"Run {run}: {' -> '.join(order)}")
        for name in order:
            await PATHS[name](run, timing)

    rows = build_rows(session_id, timing, extras)
    write_csv(rows)
    for r in rows:
        print(f"run {r['run']}  {r['path']:<18} {r['tool']:<24} "
              f"median {r['median_ms']:7.2f} ms   p95 {r['p95_ms']:7.2f} ms")
    print(f"\nSaved {CSV_PATH}")
    if history.add_session(rows):
        print(f"Added this run ({session_id}) to {HISTORY_PATH}")


if __name__ == "__main__":
    asyncio.run(main())