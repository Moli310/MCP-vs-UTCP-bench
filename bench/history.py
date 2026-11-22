"""Keeps results/history.xlsx. Every run is added as new rows; old rows are never deleted.

Sheets, in this order:
  Charts   Excel charts for the latest run and the trend across all runs
  Summary  one line per run, path and tool, averaged over the repeated timing rounds
  History  every measurement from every run
Charts and Summary use formulas over History and are rebuilt after every run,
so make any edits in History, not in those two sheets.
"""
import csv
import time
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.marker import Marker
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from check_setup import HISTORY_PATH

SESSION_FORMAT = "%Y-%m-%d_%H-%M-%S"  # sorts by time, and Excel never mistakes it for a date
COLUMNS = [
    "session_id", "run", "path", "tool", "median_ms", "p95_ms", "cold_start_ms",
    "rows_returned", "response_bytes", "mcp_text_blocks", "mcp_structured_copy",
    "tool_description_bytes", "all_paths_agree", "python_version",
    "mcp_version", "utcp_version", "utcp_http_version", "utcp_mcp_version",
]
TEXT_COLUMNS = {"session_id", "path", "tool", "python_version", "mcp_version",
                "utcp_version", "utcp_http_version", "utcp_mcp_version"}
PATHS = ["A_mcp", "B_utcp_http", "C_utcp_mcp_bridge"]
COL = {name: get_column_letter(i) for i, name in enumerate(COLUMNS, 1)}  # History column letters

FONT = Font(name="Arial", size=10)
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
TITLE_FONT = Font(name="Arial", size=12, bold=True)
LABEL_FONT = Font(name="Arial", size=10, bold=True)
NOTE_FONT = Font(name="Arial", size=9, italic=True, color="666666")


# ---------- reading ----------

def _convert(column, text):
    if text is None or text == "":
        return None
    if column in TEXT_COLUMNS:
        return text
    if text in ("True", "False"):
        return text == "True"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def read_csv(csv_path):
    """Rows from bench_results.csv. A file from before history.xlsx existed
    gets a session_id from the file's last-modified time."""
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))
    if not raw:
        return []
    if "session_id" not in raw[0]:
        stamp = datetime.fromtimestamp(csv_path.stat().st_mtime).strftime(SESSION_FORMAT)
        for r in raw:
            r["session_id"] = stamp
    return [{c: _convert(c, r.get(c)) for c in COLUMNS} for r in raw]


def _load():
    """The existing workbook (or None) and every row in its History sheet."""
    if not HISTORY_PATH.exists():
        return None, []
    wb = load_workbook(HISTORY_PATH)
    if "History" not in wb.sheetnames:
        return wb, []
    values = list(wb["History"].iter_rows(values_only=True))
    if not values:
        return wb, []
    header = list(values[0])
    rows = [dict(zip(header, v)) for v in values[1:] if any(x is not None for x in v)]
    for r in rows:
        if isinstance(r.get("session_id"), datetime):
            r["session_id"] = r["session_id"].strftime(SESSION_FORMAT)
    return wb, rows


# ---------- formulas ----------

def _criteria(session, path, tool=None):
    parts = [f"History!${COL['session_id']}:${COL['session_id']},{session}",
             f"History!${COL['path']}:${COL['path']},{path}"]
    if tool is not None:
        parts.append(f"History!${COL['tool']}:${COL['tool']},{tool}")
    return ",".join(parts)


def _avg(column, session, path, tool=None):
    """Formula: average of a History column for one session, path and (optionally) tool."""
    letter = COL[column]
    return f'=IFERROR(AVERAGEIFS(History!${letter}:${letter},{_criteria(session, path, tool)}),"")'


# ---------- sheets ----------

def _header(ws, row, names, col=1):
    for j, name in enumerate(names, start=col):
        cell = ws.cell(row, j, name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL


def _set_widths(ws, widths):
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width


def _write_history(ws, rows):
    _header(ws, 1, COLUMNS)
    for i, r in enumerate(rows, start=2):
        for j, column in enumerate(COLUMNS, start=1):
            ws.cell(i, j, r.get(column)).font = FONT
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for j, column in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(j)].width = max(len(column) + 2, 12)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 24


def _write_summary(ws, rows):
    names = ["session_id", "path", "tool", "runs_averaged", "rows_returned", "avg_median_ms",
             "avg_p95_ms", "avg_cold_start_ms", "response_bytes", "tool_description_bytes",
             "all_paths_agree"]
    _header(ws, 1, names)
    keys = sorted({(r["session_id"], r["path"], r["tool"]) for r in rows},
                  key=lambda k: (k[0], PATHS.index(k[1]) if k[1] in PATHS else len(PATHS), k[2]))
    agree = COL["all_paths_agree"]
    for i, (session, path, tool) in enumerate(keys, start=2):
        s, p, t = f"$A{i}", f"$B{i}", f"$C{i}"
        crit = _criteria(s, p, t)
        values = [
            session, path, tool,
            f"=COUNTIFS({crit})",
            _avg("rows_returned", s, p, t),
            _avg("median_ms", s, p, t),
            _avg("p95_ms", s, p, t),
            _avg("cold_start_ms", s, p, t),
            _avg("response_bytes", s, p, t),
            _avg("tool_description_bytes", s, p, t),
            f'=IF(COUNTIFS({crit},History!${agree}:${agree},FALSE)>0,"No",'
            f'IF(COUNTIFS({crit},History!${agree}:${agree},TRUE)>0,"Yes","Not checked"))',
        ]
        for j, value in enumerate(values, start=1):
            cell = ws.cell(i, j, value)
            cell.font = FONT
            if j in (6, 7, 8):
                cell.number_format = "0.00"
            elif j in (5, 9, 10):
                cell.number_format = "#,##0"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    _set_widths(ws, {"A": 22, "B": 20, "C": 24, "D": 15, "E": 15, "F": 16, "G": 13,
                     "H": 19, "I": 16, "J": 23, "K": 17})


def _style_chart(chart, title, y_title):
    chart.title = title
    chart.y_axis.title = y_title
    chart.title.overlay = False
    chart.y_axis.title.overlay = False
    chart.roundedCorners = False
    chart.legend.position = "b"
    chart.legend.overlay = False
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.width = 18
    chart.height = 8.5


def _write_charts(ws, rows):
    sessions = sorted({r["session_id"] for r in rows})
    latest = sessions[-1]
    tools = sorted({r["tool"] for r in rows if r["session_id"] == latest})

    ws["A1"], ws["B1"] = "Latest run", latest
    ws["A1"].font = ws["B1"].font = TITLE_FONT
    ws["A2"] = "Tables use formulas over the History sheet. This sheet is rebuilt after every run."
    ws["A2"].font = NOTE_FONT

    # Table 1: latest run, median latency per tool and path
    top = 5
    ws.cell(top - 1, 1, "Median latency per call (ms)").font = LABEL_FONT
    _header(ws, top, ["tool"] + PATHS)
    for i, tool in enumerate(tools, start=top + 1):
        ws.cell(i, 1, tool).font = FONT
        for j, path in enumerate(PATHS, start=2):
            cell = ws.cell(i, j, _avg("median_ms", "$B$1", f'"{path}"', f"$A{i}"))
            cell.font, cell.number_format = FONT, "0.00"
    end = top + len(tools)
    chart = BarChart()
    chart.type, chart.grouping = "col", "clustered"
    chart.add_data(Reference(ws, min_col=2, max_col=1 + len(PATHS), min_row=top, max_row=end),
                   titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=top + 1, max_row=end))
    _style_chart(chart, "Latest run: median latency per call", "ms")
    ws.add_chart(chart, "G4")

    # Table 2: latest run, response size (REST body vs MCP message)
    top2 = end + 4
    ws.cell(top2 - 1, 1, "Response size (bytes)").font = LABEL_FONT
    _header(ws, top2, ["tool", "REST body (B)", "MCP message (A, C)"])
    for i, tool in enumerate(tools, start=top2 + 1):
        ws.cell(i, 1, tool).font = FONT
        for j, path in ((2, "B_utcp_http"), (3, "A_mcp")):
            cell = ws.cell(i, j, _avg("response_bytes", "$B$1", f'"{path}"', f"$A{i}"))
            cell.font, cell.number_format = FONT, "#,##0"
    end2 = top2 + len(tools)
    chart2 = BarChart()
    chart2.type, chart2.grouping = "col", "clustered"
    chart2.add_data(Reference(ws, min_col=2, max_col=3, min_row=top2, max_row=end2),
                    titles_from_data=True)
    chart2.set_categories(Reference(ws, min_col=1, min_row=top2 + 1, max_row=end2))
    _style_chart(chart2, "Latest run: response size", "bytes")
    ws.add_chart(chart2, "G22")

    # Table 3: every run, average median latency per path
    top3 = end2 + 4
    ws.cell(top3 - 1, 1, "Average median latency per path, all runs (ms)").font = LABEL_FONT
    _header(ws, top3, ["run"] + PATHS)
    for i, session in enumerate(sessions, start=top3 + 1):
        ws.cell(i, 1, session).font = FONT
        for j, path in enumerate(PATHS, start=2):
            cell = ws.cell(i, j, _avg("median_ms", f"$A{i}", f'"{path}"'))
            cell.font, cell.number_format = FONT, "0.00"
    end3 = top3 + len(sessions)
    chart3 = LineChart()
    chart3.add_data(Reference(ws, min_col=2, max_col=1 + len(PATHS), min_row=top3, max_row=end3),
                    titles_from_data=True)
    chart3.set_categories(Reference(ws, min_col=1, min_row=top3 + 1, max_row=end3))
    for series in chart3.series:
        series.marker = Marker(symbol="circle", size=7)
        series.smooth = False
    _style_chart(chart3, "Trend across runs: average median latency", "ms")
    ws.add_chart(chart3, "G40")

    _set_widths(ws, {"A": 26, "B": 20, "C": 20, "D": 20, "E": 4, "F": 4})


def _rebuild(wb, rows):
    if wb is None:
        wb = Workbook()
        wb.remove(wb.active)
    for name in ("Charts", "Summary", "History"):
        if name in wb.sheetnames:
            del wb[name]
    _write_charts(wb.create_sheet("Charts", 0), rows)
    _write_summary(wb.create_sheet("Summary", 1), rows)
    _write_history(wb.create_sheet("History", 2), rows)
    for ws in wb.worksheets:
        ws.sheet_view.tabSelected = ws.title == "Charts"
    wb.active = 0
    wb.calculation.fullCalcOnLoad = True  # Excel calculates the formulas when the file opens
    return wb


def _save(wb, attempts=6, wait_seconds=10):
    HISTORY_PATH.parent.mkdir(exist_ok=True)
    for attempt in range(1, attempts + 1):
        try:
            wb.save(HISTORY_PATH)
            return True
        except PermissionError:
            if attempt < attempts:
                print(f"history.xlsx is open in Excel. Please close it. "
                      f"Retrying in {wait_seconds} seconds ({attempt}/{attempts - 1})...")
                time.sleep(wait_seconds)
    print("Could not update history.xlsx because it is still open in Excel.")
    print("This run is safe in bench_results.csv and will be added automatically next time.")
    return False


# ---------- public ----------

def add_csv_if_missing(csv_path):
    """If the last run never reached history.xlsx, add it before the CSV is replaced."""
    rows = read_csv(csv_path)
    if not rows:
        return
    wb, history = _load()
    session = rows[0]["session_id"]
    if session in {r["session_id"] for r in history}:
        return
    print(f"Adding the previous run ({session}) to history.xlsx first...")
    _save(_rebuild(wb, history + rows))


def add_session(rows):
    """Adds this run to history.xlsx. Returns True if it was saved."""
    wb, history = _load()
    session = rows[0]["session_id"]
    history = [r for r in history if r["session_id"] != session] + rows
    return _save(_rebuild(wb, history))