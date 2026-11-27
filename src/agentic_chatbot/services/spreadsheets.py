"""
Spreadsheets as queryable tables.

Uploaded Excel/CSV files are also chunked as text for document search, but
text search can't add up a column. So a copy of each spreadsheet is kept in
``workspace/data/<doc_id>.<ext>`` (with ``<doc_id>.json`` holding its display
name), parsed into one table per sheet, and the agent queries them with
read-only SQL through DuckDB: sums, averages, filters, group-bys, top-N.

Parsing handles typical exported reports: title rows above the header,
empty rows and columns, numbers written as "1,23,456.00", "₹ 500" or "(300)",
"Total" rows (removed, so sums aren't doubled), and duplicate or blank column
names. Column names become snake_case so the model can write SQL without quoting.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SHEET_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv"}
MAX_RESULT_ROWS = 50
_lock = threading.Lock()
_cache: dict[tuple[str, float], list[Table]] = {}


def data_dir() -> Path:
    from agentic_chatbot.core.settings import get_settings

    return get_settings().workspace_dir / "data"


@dataclass
class Table:
    name: str            # SQL table name
    file: str            # display name of the uploaded file
    sheet: str | None
    df: Any              # pandas.DataFrame
    original: dict[str, str] = field(default_factory=dict)  # sql column -> header as written


# ── storage ──────────────────────────────────────────────────────────────────

def is_spreadsheet(name: str) -> bool:
    return Path(name).suffix.lower() in SHEET_EXTENSIONS


def save_copy(src: Path, doc_id: str, display_name: str) -> None:
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(display_name).suffix.lower() or src.suffix.lower()
    shutil.copyfile(src, folder / f"{doc_id}{ext}")
    (folder / f"{doc_id}.json").write_text(json.dumps({"name": display_name}), encoding="utf-8")


def remove_copies(doc_id: str) -> None:
    folder = data_dir()
    if folder.is_dir():
        for p in folder.glob(f"{doc_id}.*"):
            with _lock:
                for key in [k for k in _cache if k[0] == str(p)]:
                    del _cache[key]
            p.unlink(missing_ok=True)


def warm_cache() -> int:
    """Parse every stored spreadsheet once (blocking: run in a thread). Returns the number of tables."""
    try:
        return len(load_tables())
    except Exception as exc:  # never break startup or an upload over this
        logger.warning("Couldn't read the stored spreadsheets: %s", exc)
        return 0


def _files() -> list[tuple[Path, str]]:
    """Kept spreadsheet files (``<doc_id>.<ext>``) the current turn may use (see core/scope.py)."""
    from agentic_chatbot.core.scope import current_scope

    scope = current_scope()
    folder = data_dir()
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() in SHEET_EXTENSIONS and (scope is None or scope.allows(p.stem)):
            meta = p.with_suffix(".json")
            name = p.name
            if meta.is_file():
                try:
                    name = json.loads(meta.read_text(encoding="utf-8")).get("name") or name
                except ValueError:
                    pass
            out.append((p, name))
    return out


def sheets_available() -> bool:
    return bool(_files())


_SHEET_WORDS = re.compile(r"\b(sheets?|spreadsheets?|excel|xlsx?|xlsm|csv|workbook|columns?|rows?|tables?)\b", re.I)
CALC_INTENT = re.compile(
    r"\b(total|sum|average|avg|mean|median|count|how many|how much|highest|lowest|max(?:imum)?|min(?:imum)?|"
    r"top \d+|largest|smallest|biggest|group|per (?:month|year|party|customer|vendor|item|invoice)|"
    r"by (?:month|year|party|customer|vendor|item)|month[- ]?wise|party[- ]?wise|breakdown|percentage|share|"
    r"compare|trend|difference|calculate|compute)\b",
    re.I,
)
_STOP = {"date", "name", "amount", "value", "total", "type", "code", "number", "sheet", "data", "file", "with", "from"}


def mentions_sheets(text: str) -> bool:
    """True when the message is about the uploaded spreadsheets: it says "sheet"/"excel"/"column",
    or uses a word from a spreadsheet's file name or column names (e.g. "refund", "igst")."""
    if _SHEET_WORDS.search(text):
        return True
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    if not words:
        return False
    vocab: set[str] = set()
    for _path, display in _files():
        vocab |= set(re.findall(r"[a-z]{4,}", Path(display).stem.lower()))
    for t in _cache_snapshot():
        vocab |= {w for c in t.df.columns for w in re.findall(r"[a-z]{4,}", c)}
    return bool((words & vocab) - _STOP)


def _cache_snapshot() -> list[Table]:
    with _lock:
        return [t for tables in _cache.values() for t in tables]


# ── parsing ──────────────────────────────────────────────────────────────────

def snake(text: str, fallback: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(text)).strip("_").lower()
    if not s:
        s = fallback
    if s[0].isdigit():
        s = f"c_{s}"
    return s[:48]


def _unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 1
            out.append(n)
    return out


_TOTAL = re.compile(r"^(grand\s*|sub\s*-?\s*)?totals?\s*:?$", re.I)
_NUM = re.compile(r"^\(?-?\s*(?:₹|rs\.?|inr|\$|€|£)?\s*-?[\d,]*\.?\d+\s*%?\)?$", re.I)


def _numeric(series):
    """The column as numbers when at least 80% of its filled cells look numeric, else None."""
    import pandas as pd

    filled = series.dropna()
    if not len(filled):
        return None
    if filled.map(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)).all():
        return pd.to_numeric(series, errors="coerce")
    text = filled.astype(str).str.strip()
    if text.str.match(_NUM).mean() < 0.8:
        return None
    cleaned = (text.str.replace(r"(?i)₹|rs\.?|inr|\$|€|£|,|%|\s", "", regex=True)
               .str.replace(r"^\((.*)\)$", r"-\1", regex=True))  # (123) means -123 in accounting
    out = pd.Series(float("nan"), index=series.index)
    out.loc[filled.index] = pd.to_numeric(cleaned, errors="coerce")
    return out


def frame_from_raw(raw):
    """Find the header row in a sheet read without headers, and clean the table under it."""
    import pandas as pd

    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return raw, {}
    head = raw.head(30)
    counts = head.notna().sum(axis=1)
    target = max(2, int(counts.max() * 0.6))
    header_at = raw.index[0]
    for idx in raw.head(20).index:
        values = raw.loc[idx].dropna()
        if counts.get(idx, 0) >= target and len(values) and values.map(lambda v: isinstance(v, str)).mean() >= 0.5:
            header_at = idx
            break
    headers = [("" if pd.isna(v) else str(v).strip()) for v in raw.loc[header_at]]
    body = raw.loc[raw.index > header_at].dropna(how="all")
    # Report totals ("Total", "Grand total", "Sub total") would be double-counted by SUM: drop them.
    is_total = body.apply(lambda row: any(isinstance(v, str) and _TOTAL.match(v.strip()) for v in row), axis=1)
    removed = int(is_total.sum()) if len(body) else 0
    if removed:
        body = body.loc[~is_total]
    sql_names = _unique([snake(h, f"col_{i + 1}") for i, h in enumerate(headers)])
    original = {s: (h or s) for s, h in zip(sql_names, headers, strict=False)}
    body = body.copy()
    body.columns = sql_names
    body = body.reset_index(drop=True)
    for col in body.columns:
        s = body[col]
        if s.dtype != object:
            continue
        num = _numeric(s)
        if num is not None:
            body[col] = num
            continue
        filled = s.dropna()
        if len(filled) and filled.map(lambda v: hasattr(v, "year") and hasattr(v, "month")).all():
            body[col] = pd.to_datetime(s, errors="coerce")
            continue
        if re.search(r"date|period|month", col):
            parsed = pd.to_datetime(s, errors="coerce", dayfirst=True, format="mixed")
            years = parsed.dropna().dt.year
            if len(years) >= 0.8 * max(s.notna().sum(), 1) and years.between(1900, 2200).all():
                body[col] = parsed
                continue
        body[col] = s.map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip())
    if removed:
        original["__totals_removed__"] = str(removed)
    return body, original


def _read(path: Path) -> list[tuple[str | None, Any]]:
    import warnings

    import pandas as pd

    ext = path.suffix.lower()
    if ext in (".csv", ".tsv"):
        sep = "\t" if ext == ".tsv" else None
        raw = pd.read_csv(path, header=None, sep=sep, engine="python", dtype=object, encoding_errors="replace")
        return [(None, raw)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        sheets = pd.read_excel(path, sheet_name=None, header=None, engine=engine, dtype=object)
    return list(sheets.items())


def load_tables() -> list[Table]:
    tables: list[Table] = []
    used: set[str] = set()
    for path, display in _files():
        key = (str(path), path.stat().st_mtime)
        with _lock:
            cached = _cache.get(key)
        if cached is None:
            cached = []
            try:
                for sheet, raw in _read(path):
                    df, original = frame_from_raw(raw)
                    if df.empty or not len(df.columns):
                        continue
                    cached.append(Table(name="", file=display, sheet=sheet, df=df, original=original))
            except Exception as exc:
                logger.warning("Couldn't read spreadsheet %s: %s", display, exc)
            with _lock:
                _cache[key] = cached
        for t in cached:
            base = snake(Path(display).stem, "sheet")[:40]
            if t.sheet:
                base = f"{base}__{snake(t.sheet, 'sheet')[:24]}"
            name, n = base, 2
            while name in used:
                name, n = f"{base}_{n}", n + 1
            used.add(name)
            tables.append(Table(name=name, file=t.file, sheet=t.sheet, df=t.df, original=t.original))
    return tables


# ── describe and query ───────────────────────────────────────────────────────

def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:  # NaN
            return ""
        return f"{v:,.2f}" if abs(v) >= 1000 or v != int(v) else f"{int(v)}"
    if hasattr(v, "isoformat"):
        iso = v.isoformat()
        return iso[:10] if iso[11:19] in ("", "00:00:00") else iso[:16].replace("T", " ")
    return str(v).replace("|", "/").replace("\n", " ")


def _sample(series, k: int = 3) -> str:
    vals = [_fmt(v) for v in series.dropna().unique()[:k]]
    return ", ".join(v[:24] for v in vals)


def describe(tables: list[Table] | None = None, max_chars: int = 6000) -> str:
    tables = load_tables() if tables is None else tables
    if not tables:
        return "No spreadsheets have been uploaded."
    blocks = []
    for t in tables:
        where = f"{t.file}" + (f", sheet \"{t.sheet}\"" if t.sheet else "")
        cols = []
        for c in t.df.columns:
            dtype = str(t.df[c].dtype)
            kind = "number" if dtype.startswith(("float", "int")) else "date" if dtype.startswith("datetime") else "text"
            orig = t.original.get(c)
            label = f"{c} ({kind}" + (f", header \"{orig}\"" if orig and snake(orig, c) != orig else "") + ")"
            sample = _sample(t.df[c])
            cols.append(f"  - {label}" + (f": e.g. {sample}" if sample else ""))
        note = f"; {t.original['__totals_removed__']} total row(s) removed" if "__totals_removed__" in t.original else ""
        blocks.append(f"Table {t.name}  [{where}, {len(t.df)} rows{note}]\n" + "\n".join(cols))
    text = "\n\n".join(blocks)
    return text if len(text) <= max_chars else text[:max_chars] + "\n… (more columns; call describe_spreadsheets)"


_FORBIDDEN = re.compile(
    r"\b(copy|attach|detach|install|load|pragma|export|import|create|insert|update|delete|drop|alter|call|set|reset|"
    r"read_csv\w*|read_parquet|read_json\w*|read_text|read_blob|glob|httpfs)\b",
    re.I,
)


def run_query(sql: str, tables: list[Table] | None = None, max_rows: int = MAX_RESULT_ROWS) -> tuple[str, list[str]]:
    """Run one read-only SELECT. Returns (Markdown result, names of files used)."""
    import duckdb

    query = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^(with|select)\b", query) or ";" in query:
        raise ValueError("Only a single SELECT (or WITH … SELECT) query is allowed.")
    bad = _FORBIDDEN.search(query)
    if bad:
        raise ValueError(f"'{bad.group(1)}' isn't allowed: queries can only read the uploaded spreadsheets.")
    tables = load_tables() if tables is None else tables
    if not tables:
        raise ValueError("No spreadsheets have been uploaded.")
    con = duckdb.connect(":memory:")
    try:
        # No file or network access from SQL, and no way to switch it back on.
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")
        for t in tables:
            con.register(t.name, t.df)
        cur = con.execute(query)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    finally:
        con.close()
    used = sorted({t.file for t in tables if re.search(rf"\b{re.escape(t.name)}\b", query)})
    if not rows:
        return "The query returned no rows.", used
    more = len(rows) > max_rows
    rows = rows[:max_rows]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(_fmt(v) for v in r) + " |" for r in rows]
    if more:
        lines.append(f"\n(Showing the first {max_rows} rows; add LIMIT or aggregate to narrow it.)")
    return "\n".join(lines), used
