"""CSV upload and persistence wrapper for the shared report engine."""

from __future__ import annotations

from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reports.engine import STANDARD_FIELDS, is_mapped, render_reports, to_number
from src.db import get_engine

ALIASES = {
    "product_name": ("product", "item", "name", "productname", "itemname", "description", "sku", "প্রোডাক্ট", "পণ্য", "আইটেম"),
    "quantity": ("qty", "quantity", "qnty", "pcs", "units", "soldqty", "পরিমাণ", "সংখ্যা"),
    "sales_amount": ("sales", "amount", "total", "price", "revenue", "linetotal", "netamount", "টাকা", "দাম", "মোট"),
    "date": ("date", "orderdate", "invoicedate", "saledate", "createdat", "time", "তারিখ"),
    "product_group": ("group", "category", "type", "গ্রুপ", "ক্যাটাগরি"),
    "brand": ("brand", "ব্র্যান্ড"),
    "stock_quantity": ("stock", "stockqty", "onhand", "balance", "স্টক"),
    "cost": ("cost", "buyingprice", "purchaseprice", "unitcost", "ক্রয়মূল্য"),
    "profit": ("profit", "margin", "লাভ"),
    "returns": ("return", "returns", "returnqty", "ফেরত"),
    "customer": ("customer", "client", "party", "buyer", "customername", "গ্রাহক", "কাস্টমার", "পার্টি"),
    "invoice": ("invoice", "invoiceno", "billno", "voucher", "memo", "ইনভয়েস", "মেমো"),
    "due": ("due", "outstanding", "বাকি", "বকেয়া"),
    "paid": ("paid", "received", "payment", "জমা", "পরিশোধ"),
}
NUMERIC_FIELDS = {"quantity", "sales_amount", "stock_quantity", "cost", "profit", "returns", "due", "paid"}
LABELS = {field: field.replace("_", " ").title() for field in STANDARD_FIELDS}
LEGACY_FIELDS = {"amount": "sales_amount", "stock": "stock_quantity"}


def _normalise_header(value: Any) -> str:
    return "".join(
        str(value).replace("\ufeff", "").strip().casefold().split()
    ).replace("_", "").replace(".", "").replace("-", "")


def _detect(frame: pd.DataFrame) -> dict[str, str]:
    headers = list(frame.columns)
    normalised = {header: _normalise_header(header) for header in headers}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for field, aliases in ALIASES.items():
        alias_values = {_normalise_header(alias) for alias in aliases}
        hit = next((h for h in headers if h not in used and normalised[h] in alias_values), None)
        if hit is None:
            hit = next((h for h in headers if h not in used and any(alias in normalised[h] for alias in alias_values)), None)
        if hit is None and field == "date":
            for h in headers:
                if h in used:
                    continue
                values = pd.to_datetime(frame[h], errors="coerce")
                non_null = frame[h].notna().sum()
                if non_null and values.notna().sum() / non_null >= 0.8:
                    hit = h
                    break
        if hit is None and field in {"quantity", "sales_amount"}:
            for h in headers:
                if h in used:
                    continue
                numeric = to_number(frame[h])
                if numeric.notna().any() and any(alias in normalised[h] for alias in alias_values):
                    hit = h
                    break
        if hit is not None:
            mapping[field] = hit
            used.add(hit)
    return mapping


def _advanced_mapping(frame: pd.DataFrame, detected: dict[str, str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    all_options = ["Not mapped", *frame.columns.tolist()]
    used: set[str] = set()
    with st.expander("Advanced: fix columns", expanded=False):
        for field in STANDARD_FIELDS:
            default = detected.get(field, "Not mapped")
            options = [
                option for option in all_options
                if option == "Not mapped" or option == default or option not in used
            ]
            index = options.index(default) if default in options else 0
            selected = st.selectbox(
                LABELS[field], options, index=index, key=f"csv_mapping_{field}"
            )
            if selected != "Not mapped":
                mapping[field] = selected
                used.add(selected)
    return mapping


@st.cache_data(ttl=300, show_spinner="Preparing CSV report...")
def _clean(frame: pd.DataFrame, mapping_json: str) -> pd.DataFrame:
    mapping = json.loads(mapping_json)
    result = pd.DataFrame(index=frame.index)
    for field in STANDARD_FIELDS:
        source = mapping.get(field)
        if not source or source not in frame.columns:
            continue
        result[field] = frame[source]
        if field in NUMERIC_FIELDS:
            values = to_number(result[field])
            if values.notna().sum() == 0:
                result.drop(columns=[field], inplace=True)
            else:
                result[field] = values
                if field in {"quantity", "sales_amount", "returns", "due", "paid"}:
                    result[field] = result[field].fillna(0)
        elif field == "date":
            result[field] = pd.to_datetime(result[field], errors="coerce")
        else:
            result[field] = result[field].fillna("Unknown").astype(str).str.strip()
    if "date" in result:
        result = result.dropna(subset=["date"])
    return result.reset_index(drop=True)


def _read_csv(uploaded_file: Any) -> pd.DataFrame | None:
    try:
        content = uploaded_file.getvalue()
        if not content:
            return None
        frame = pd.read_csv(io.BytesIO(content))
    except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError, ValueError) as exc:
        st.warning(f"Could not read the CSV: {exc}")
        return None
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame.dropna(how="all").reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner="Loading saved CSV report...")
def _load_saved_rows(upload_id: int) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    with get_engine().connect() as connection:
        upload = connection.execute(text("SELECT id, report_name, original_filename, uploaded_at, row_count, date_from, date_to, column_mapping FROM csv_uploads WHERE id = :id"), {"id": upload_id}).mappings().one_or_none()
        if upload is None:
            raise RuntimeError("The selected saved report no longer exists.")
        rows = connection.execute(text("SELECT row_data FROM csv_upload_rows WHERE upload_id = :id ORDER BY row_number"), {"id": upload_id}).mappings().all()
    decode = lambda value: json.loads(value) if isinstance(value, str) else value
    return pd.DataFrame([decode(row["row_data"]) for row in rows]), dict(upload), decode(upload["column_mapping"])


def _saved_reports() -> pd.DataFrame:
    with get_engine().connect() as connection:
        rows = connection.execute(text("SELECT id, report_name, uploaded_at, original_filename, row_count, date_from, date_to FROM csv_uploads ORDER BY uploaded_at DESC, id DESC")).mappings().all()
    return pd.DataFrame(rows)


def _save_upload(frame: pd.DataFrame, mapping: dict[str, str], report_name: str, filename: str) -> int:
    data = frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
    valid_dates = frame["date"].dropna() if "date" in frame else pd.Series(dtype="datetime64[ns]")
    with get_engine().begin() as connection:
        result = connection.execute(text("INSERT INTO csv_uploads (report_name, original_filename, row_count, date_from, date_to, column_mapping) VALUES (:name, :filename, :row_count, :date_from, :date_to, :mapping)"), {"name": report_name, "filename": filename, "row_count": len(data), "date_from": valid_dates.min().date() if not valid_dates.empty else None, "date_to": valid_dates.max().date() if not valid_dates.empty else None, "mapping": json.dumps(mapping)})
        upload_id = int(result.lastrowid)
        statement = text("INSERT INTO csv_upload_rows (upload_id, row_number, row_data) VALUES (:upload_id, :row_number, :row_data)")
        for start in range(0, len(data), 1000):
            connection.execute(statement, [{"upload_id": upload_id, "row_number": index + 1, "row_data": json.dumps(row, default=str)} for index, row in enumerate(data[start:start + 1000], start=start)])
    return upload_id


def _render_saved_reports(reports: pd.DataFrame) -> int | None:
    if reports.empty:
        st.info("No saved CSV reports yet.")
        return None
    st.dataframe(reports.drop(columns=["id"]).rename(columns={"report_name": "Report name"}), hide_index=True, width="stretch")
    ids = reports["id"].astype(int).tolist()
    selected = st.selectbox("Select saved report", ids, format_func=lambda value: reports.loc[reports["id"] == value, "report_name"].iloc[0], key="csv_saved_report")
    return int(selected)


def main() -> None:
    st.title("CSV Analysis")
    uploaded_file = st.file_uploader("Upload sales CSV", type=["csv"])
    if uploaded_file is not None:
        content_hash = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
        if st.session_state.get("csv_saved_hash") != content_hash:
            raw = _read_csv(uploaded_file)
            if raw is None or raw.empty:
                st.error("No data in CSV file")
                return
            detected = _detect(raw)
            mapping = _advanced_mapping(raw, detected)
            cleaned = _clean(raw, json.dumps(mapping))
            if cleaned.empty or not mapping:
                st.error("No data in CSV file")
                return
            name = f"{uploaded_file.name} - {datetime.now():%Y-%m-%d}"
            try:
                upload_id = _save_upload(cleaned, {field: field for field in cleaned.columns}, name, uploaded_file.name)
                st.session_state.csv_saved_hash = content_hash
                st.session_state.csv_open_report_id = upload_id
                _load_saved_rows.clear()
                st.rerun()
            except Exception as exc:
                st.warning(f"Could not save the CSV report; the transaction was rolled back: {exc}")
    try:
        reports = _saved_reports()
    except Exception as exc:
        st.warning(f"Could not load saved reports: {exc}")
        return
    selected_id = _render_saved_reports(reports)
    if selected_id is None:
        return
    try:
        stored, upload, old_mapping = _load_saved_rows(selected_id)
        mapping = {LEGACY_FIELDS.get(field, field): source for field, source in old_mapping.items()}
        frame = _clean(stored, json.dumps(mapping))
    except Exception as exc:
        st.warning(f"Could not open the saved report: {exc}")
        return
    if frame.empty:
        st.error("No data in CSV file")
        return
    if "date" in frame:
        dates = frame["date"].dropna()
        if not dates.empty:
            date_range = st.sidebar.date_input("Date range", value=(dates.min().date(), dates.max().date()), min_value=dates.min().date(), max_value=dates.max().date(), key=f"csv_dates_{selected_id}")
            if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
                frame = frame[(frame["date"].dt.date >= date_range[0]) & (frame["date"].dt.date <= date_range[1])]
    st.info(f"Showing CSV report: {upload['report_name']}")
    section = st.radio("Section", ["Reports", "Customers"], horizontal=True, key="csv_section")
    render_reports(frame, "csv", section.lower())


main()
