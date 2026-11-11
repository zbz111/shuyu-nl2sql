"""把 CSV / Excel 导入成 SQLite 表。

设计要点：
- 业务人员手里是 Excel，不可能是 .db 文件，所以必须支持 CSV/XLSX；
- 自动识别列类型（日期 / 数值 / 文本），日期统一存 ISO 文本，便于 SQLite 用 substr 按月统计；
- 每个 sheet 建一张表，表名安全化（英文+下划线），并保留原始列名；
- 导入后与手工上传的 .db 走同一套只读查询链路，不引入第二种执行路径。
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

MAX_ROWS = 500_000


class ImportError_(RuntimeError):
    pass


def safe_table_name(name: str) -> str:
    """把中文表名/文件名转成合法 SQLite 标识符：保留字母数字下划线，其余转下划线。"""
    stem = Path(str(name)).stem
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", stem).strip("_")
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    if not cleaned:
        cleaned = "table"
    if cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:60]


def _read_csv(path: Path) -> pd.DataFrame:
    last: Exception | None = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return pd.read_csv(path, encoding=enc, sep=None, engine="python")
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise ImportError_(f"CSV 读取失败（尝试了 utf-8/gbk）：{last}")


def _read_excel(path: Path) -> dict[str, pd.DataFrame]:
    try:
        return pd.read_excel(path, sheet_name=None)
    except Exception as exc:  # noqa: BLE001
        raise ImportError_(f"Excel 读取失败：{exc}") from exc


def _to_datetime_series(s: pd.Series) -> pd.Series | None:
    """尝试识别日期列；成功率高才认，避免把普通数字当日期。"""
    sample = s.dropna().astype(str).head(50)
    if sample.empty:
        return None
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    if parsed.notna().mean() < 0.8:
        return None
    # 纯数字列（如 20260101 之外的 12345）不应被当成日期
    if sample.str.fullmatch(r"\d{1,6}").mean() > 0.8:
        return None
    return pd.to_datetime(s, errors="coerce", format="mixed")


def infer_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """推断列类型并规范化日期列。返回 (处理后的 df, 列元信息)。"""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    meta: list[dict] = []

    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            df[col] = s.dt.strftime("%Y-%m-%d %H:%M:%S").where(s.dt.hour.ne(0) | s.dt.minute.ne(0), s.dt.strftime("%Y-%m-%d"))
            meta.append({"name": col, "type": "date", "sql_type": "TEXT"})
            continue

        if pd.api.types.is_numeric_dtype(s):
            meta.append({"name": col, "type": "number", "sql_type": "REAL"})
            continue

        as_date = _to_datetime_series(s)
        if as_date is not None:
            has_time = as_date.dt.hour.fillna(0).ne(0).any() or as_date.dt.minute.fillna(0).ne(0).any()
            fmt = "%Y-%m-%d %H:%M:%S" if has_time else "%Y-%m-%d"
            df[col] = as_date.dt.strftime(fmt)
            meta.append({"name": col, "type": "date", "sql_type": "TEXT"})
            continue

        numeric = pd.to_numeric(s, errors="coerce")
        if numeric.notna().mean() >= 0.95 and s.notna().any():
            df[col] = numeric
            meta.append({"name": col, "type": "number", "sql_type": "REAL"})
            continue

        df[col] = s.astype(str).where(s.notna(), None)
        meta.append({"name": col, "type": "text", "sql_type": "TEXT"})

    return df, meta


def import_frames(frames: dict[str, pd.DataFrame], db_path: Path) -> list[dict]:
    """把多个 DataFrame 写成 SQLite 表，返回每张表的元信息。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    created: list[dict] = []
    try:
        for raw_name, df in frames.items():
            if df is None or df.empty:
                continue
            if len(df) > MAX_ROWS:
                raise ImportError_(f"数据行数超过上限（{MAX_ROWS}），请拆分后再上传")
            table = safe_table_name(raw_name or "data")
            df, meta = infer_frame(df)
            df = df.where(pd.notna(df), None)

            cols_ddl = ", ".join(f'"{m["name"]}" {m["sql_type"]}' for m in meta)
            conn.execute(f'CREATE TABLE "{table}" ({cols_ddl})')
            placeholders = ", ".join("?" * len(meta))
            conn.executemany(
                f'INSERT INTO "{table}" VALUES ({placeholders})',
                [tuple(row) for row in df.itertuples(index=False, name=None)],
            )
            created.append({"table": table, "columns": meta, "rows": int(len(df))})
        conn.commit()
    finally:
        conn.close()

    if not created:
        db_path.unlink(missing_ok=True)
        raise ImportError_("文件里没有可导入的数据")
    return created


def load_file(path: Path) -> tuple[dict[str, pd.DataFrame], str]:
    """读取上传文件，返回 (sheet->df, 源类型)。"""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return {"data": _read_csv(path)}, "csv"
    if suffix in {".xlsx", ".xlsm"}:
        sheets = _read_excel(path)
        if not sheets:
            raise ImportError_("Excel 里没有工作表")
        return sheets, "xlsx"
    raise ImportError_("只支持 .csv / .xlsx，SQLite 请用 .db 上传")