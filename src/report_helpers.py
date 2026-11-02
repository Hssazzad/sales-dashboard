"""Shared data access, filters and formatting for the sales reports.

Every report page imports from this module so that the sale definition,
SQL, filter widgets and currency formatting live in ONE place.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.db import get_engine

# ---------------------------------------------------------------------------
# Sale definition (single place to change later)
# ---------------------------------------------------------------------------
# Every row in sales_details is treated as a valid sale.  If the business rule
# changes, edit ONLY this constant, for example: "d.APPROVAL = 'Y'".
SALE_WHERE = "1 = 1"

_LOOKBACK_DAYS = 90


# ---------------------------------------------------------------------------
# Currency formatting
# ---------------------------------------------------------------------------

def fmt_taka(value: float | int | None, decimals: int = 2) -> str:
    """Format *value* as a BDT amount using lakh/crore grouping.

    Examples: 1234567.89 -> "৳ 12,34,567.89", None -> "—".
    """
    if value is None or pd.isna(value):
        return "—"

    value = float(value)
    sign = "-" if value < 0 else ""
    formatted = f"{abs(value):.{decimals}f}"

    if decimals:
        integer_str, decimal_str = formatted.split(".")
        decimal_part = "." + decimal_str
    else:
        integer_str = formatted
        decimal_part = ""

    # Group the integer part in the Bangladeshi lakh/crore style.
    if len(integer_str) <= 3:
        grouped = integer_str
    else:
        grouped = integer_str[-3:]
        rest = integer_str[:-3]
        while rest:
            grouped = rest[-2:] + "," + grouped
            rest = rest[:-2]

    return f"{sign}৳ {grouped}{decimal_part}"


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SALES_SQL = """
SELECT
    d.SALES_DATE,
    d.SALES_ID,
    d.PRODUCT_ID,
    p.PRODUCT_NAME,
    d.PRODUCT_GROUP_ID,
    pg.PRODUCT_GROUP_NAME,
    p.BRAND_ID,
    b.BRAND_NAME,
    d.STORE_ID,
    s.STORE_NAME,
    d.QTY,
    d.UNIT_PRICE,
    COALESCE(d.DISCOUNT, 0)                    AS DISCOUNT,
    d.DISCOUNT_PCT,
    d.AVG_COST,
    d.ORG_COST,
    d.QTY * d.UNIT_PRICE                       AS LINE_GROSS,
    d.QTY * d.UNIT_PRICE - COALESCE(d.DISCOUNT, 0) AS LINE_AMOUNT
FROM sales_details AS d
LEFT JOIN product       AS p  ON p.PRODUCT_ID        = d.PRODUCT_ID
LEFT JOIN product_group AS pg ON pg.PRODUCT_GROUP_ID = d.PRODUCT_GROUP_ID
LEFT JOIN brand         AS b  ON b.BRAND_ID          = p.BRAND_ID
LEFT JOIN store         AS s  ON s.STORE_ID          = d.STORE_ID
WHERE {sale_filter}
  AND d.SALES_DATE BETWEEN :date_from AND :date_to
  {extra}
ORDER BY d.SALES_DATE, d.SALES_ID
"""


@st.cache_data(ttl=300, show_spinner="Loading sales data...")
def get_sales_df(
    date_from: date,
    date_to: date,
    store: str | None = None,
    group: str | None = None,
    brand: str | None = None,
) -> pd.DataFrame:
    """Return sales rows for the selected period as a DataFrame.

    All user-supplied values are bound as SQL parameters.  The returned frame
    contains the raw measures, cost columns plus the computed ``qty`` and
    ``line_amount`` columns used by the reports.
    """
    extra_parts: list[str] = []
    params: dict[str, object] = {
        "date_from": date_from,
        "date_to": date_to,
    }

    if store:
        extra_parts.append("AND d.STORE_ID = :store_id")
        params["store_id"] = store
    if group:
        extra_parts.append("AND d.PRODUCT_GROUP_ID = :group_id")
        params["group_id"] = group
    if brand:
        extra_parts.append("AND p.BRAND_ID = :brand_id")
        params["brand_id"] = brand

    sql = _SALES_SQL.format(
        sale_filter=SALE_WHERE,
        extra="\n  ".join(extra_parts),
    )

    df = pd.read_sql_query(text(sql), get_engine(), params=params)

    df["SALES_DATE"] = pd.to_datetime(df["SALES_DATE"])

    for column in (
        "QTY",
        "UNIT_PRICE",
        "DISCOUNT",
        "DISCOUNT_PCT",
        "AVG_COST",
        "ORG_COST",
        "LINE_GROSS",
        "LINE_AMOUNT",
    ):
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    for column in ("PRODUCT_ID", "PRODUCT_GROUP_ID", "BRAND_ID", "STORE_ID"):
        df[column] = df[column].fillna("UNKNOWN").astype(str)

    for column in ("PRODUCT_NAME", "PRODUCT_GROUP_NAME", "BRAND_NAME", "STORE_NAME"):
        df[column] = df[column].fillna("Unknown").astype(str).str.strip()

    # Lower-case computed columns used by every report.
    df["qty"] = df["QTY"]
    df["line_amount"] = df["LINE_AMOUNT"]

    return df


@st.cache_data(ttl=300, show_spinner="Loading stock snapshot...")
def get_stock_df() -> pd.DataFrame:
    """Return one current stock row per product from both stock tables."""
    sql = text(
        """
        SELECT
            p.PRODUCT_ID,
            COALESCE(p.PRODUCT_NAME, 'Unknown') AS PRODUCT_NAME,
            COALESCE(p.PRODUCT_GROUP_ID, 'UNKNOWN') AS PRODUCT_GROUP_ID,
            COALESCE(p.RED_LEVEL, 0) AS RED_LEVEL,
            COALESCE(SUM(s.STOCK_QTY), 0) AS stock_qty,
            COALESCE(SUM(COALESCE(s.STOCK_AMT, s.STOCK_QTY * s.AVG_COST)), 0)
                AS stock_value
        FROM (
            SELECT PRODUCT_ID, STOCK_QTY, STOCK_AMT, AVG_COST
            FROM stock_non_serial
            UNION ALL
            SELECT PRODUCT_ID, STOCK_QTY, STOCK_AMT, AVG_COST
            FROM stock_serial
        ) AS s
        LEFT JOIN product AS p ON p.PRODUCT_ID = s.PRODUCT_ID
        GROUP BY p.PRODUCT_ID, p.PRODUCT_NAME, p.PRODUCT_GROUP_ID, p.RED_LEVEL
        """
    )
    df = pd.read_sql_query(sql, get_engine())
    if df.empty:
        return pd.DataFrame(
            columns=[
                "PRODUCT_ID", "PRODUCT_NAME", "PRODUCT_GROUP_ID", "RED_LEVEL",
                "stock_qty", "stock_value", "avg_cost",
            ]
        )
    for column in ("RED_LEVEL", "stock_qty", "stock_value"):
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    df["avg_cost"] = df["stock_value"].div(df["stock_qty"].where(df["stock_qty"] != 0)).fillna(0.0)
    for column in ("PRODUCT_ID", "PRODUCT_GROUP_ID"):
        df[column] = df[column].fillna("UNKNOWN").astype(str)
    df["PRODUCT_NAME"] = df["PRODUCT_NAME"].fillna("Unknown").astype(str).str.strip()
    return df


@st.cache_data(ttl=600, show_spinner=False)
def get_last_purchase_prices() -> pd.DataFrame:
    """Return the latest purchase unit price per product."""
    sql = text(
        """
        SELECT pd.PRODUCT_ID, pd.UNIT_PRICE, pd.PURCHASE_DATE
        FROM purchase_details AS pd
        INNER JOIN (
            SELECT PRODUCT_ID, MAX(PURCHASE_DATE) AS latest_date
            FROM purchase_details
            WHERE PRODUCT_ID IS NOT NULL
            GROUP BY PRODUCT_ID
        ) AS latest
            ON latest.PRODUCT_ID = pd.PRODUCT_ID
           AND latest.latest_date = pd.PURCHASE_DATE
        WHERE pd.UNIT_PRICE IS NOT NULL
        """
    )
    df = pd.read_sql_query(sql, get_engine())
    if df.empty:
        return pd.DataFrame(columns=["PRODUCT_ID", "purchase_price", "purchase_date"])
    df["UNIT_PRICE"] = pd.to_numeric(df["UNIT_PRICE"], errors="coerce")
    df = df.dropna(subset=["UNIT_PRICE"]).drop_duplicates("PRODUCT_ID")
    df = df.rename(columns={"UNIT_PRICE": "purchase_price", "PURCHASE_DATE": "purchase_date"})
    df["PRODUCT_ID"] = df["PRODUCT_ID"].astype(str)
    return df


@st.cache_data(ttl=300, show_spinner="Loading return summary...")
def get_return_summary(date_from: date, date_to: date) -> pd.DataFrame:
    """Return product-level return quantities and amounts for a date range."""
    sql = text(
        """
        SELECT
            PRODUCT_ID,
            COALESCE(SUM(QTY), 0) AS returned_qty,
            COALESCE(SUM(TOTAL_PRICE), 0) AS return_amount
        FROM sales_return_details
        WHERE RETURN_DATE BETWEEN :date_from AND :date_to
        GROUP BY PRODUCT_ID
        """
    )
    df = pd.read_sql_query(
        sql, get_engine(), params={"date_from": date_from, "date_to": date_to}
    )
    if df.empty:
        return pd.DataFrame(
            columns=["PRODUCT_ID", "returned_qty", "return_amount"]
        )
    df["PRODUCT_ID"] = df["PRODUCT_ID"].fillna("UNKNOWN").astype(str)
    for column in ("returned_qty", "return_amount"):
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return df


# ---------------------------------------------------------------------------
# Profit calculation (single place to change later)
# ---------------------------------------------------------------------------

def add_profit_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with cost, profit, margin and cost-validity columns.

    ``cost_amount`` is qty x AVG_COST.  Rows with AVG_COST <= 0 are marked
    ``costed = False`` and get a NaN margin so they cannot silently inflate
    margin percentages.  The Profit Report excludes those rows and shows them
    in a separate warning table.
    """
    result = df.copy()

    avg_cost = pd.to_numeric(result["AVG_COST"], errors="coerce").fillna(0.0)
    qty = pd.to_numeric(result["qty"], errors="coerce").fillna(0.0)
    line_amount = pd.to_numeric(result["line_amount"], errors="coerce").fillna(0.0)

    result["cost_amount"] = qty * avg_cost
    result["profit"] = line_amount - result["cost_amount"]
    result["costed"] = avg_cost > 0

    # A zero sales amount has no meaningful margin; leave it as NaN.
    safe_amount = line_amount.where(line_amount != 0)
    result["margin_pct"] = result["profit"] / safe_amount * 100
    result["margin_pct"] = result["margin_pct"].where(result["costed"])

    return result


# ---------------------------------------------------------------------------
# Cached filter options
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def _max_sale_date() -> date:
    """Latest valid sale date, falling back to today for an empty database."""
    sql = text(
        f"SELECT MAX(d.SALES_DATE) FROM sales_details AS d WHERE {SALE_WHERE}"
    )
    with get_engine().connect() as connection:
        value = connection.execute(sql).scalar()
    return pd.Timestamp(value).date() if value else date.today()


@st.cache_data(ttl=600, show_spinner=False)
def _min_sale_date() -> date:
    """Earliest valid sale date, falling back to today for an empty database."""
    sql = text(
        f"SELECT MIN(d.SALES_DATE) FROM sales_details AS d WHERE {SALE_WHERE}"
    )
    with get_engine().connect() as connection:
        value = connection.execute(sql).scalar()
    return pd.Timestamp(value).date() if value else date.today()


@st.cache_data(ttl=600, show_spinner=False)
def _store_options() -> dict[str, str]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT STORE_ID, STORE_NAME FROM store ORDER BY STORE_NAME")
        ).fetchall()
    return {row[0]: (row[1] or "").strip() for row in rows}


@st.cache_data(ttl=600, show_spinner=False)
def _group_options() -> dict[str, str]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                "SELECT PRODUCT_GROUP_ID, PRODUCT_GROUP_NAME "
                "FROM product_group ORDER BY PRODUCT_GROUP_NAME"
            )
        ).fetchall()
    return {row[0]: (row[1] or "").strip() for row in rows}


@st.cache_data(ttl=600, show_spinner=False)
def _brand_options() -> dict[str, str]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT BRAND_ID, BRAND_NAME FROM brand ORDER BY BRAND_NAME")
        ).fetchall()
    return {row[0]: (row[1] or "").strip() for row in rows}


# ---------------------------------------------------------------------------
# Reusable filter widget
# ---------------------------------------------------------------------------

def render_report_filters(
    *,
    key_prefix: str = "sales_report",
) -> tuple[date, date, str | None, str | None, str | None]:
    """Render the shared sidebar filters and return the chosen values.

    Returns ``(date_from, date_to, store_id, group_id, brand_id)`` where the
    last three are ``None`` when "All" is selected.  The default period is the
    last 90 days counted back from the latest sale date in the data.
    """
    max_date = _max_sale_date()
    min_date = _min_sale_date()
    default_from = max(max_date - timedelta(days=_LOOKBACK_DAYS - 1), min_date)

    st.sidebar.header("Report Filters")
    st.sidebar.caption(
        "Sale rule: every row in sales_details counts (no APPROVAL/STATUS filter)."
    )

    date_range = st.sidebar.date_input(
        "Date range",
        value=(default_from, max_date),
        min_value=min_date,
        max_value=max_date,
        key=f"{key_prefix}_dates",
    )

    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        st.sidebar.warning("Select both a start and an end date.")
        st.stop()

    date_from, date_to = date_range
    if date_from > date_to:
        st.sidebar.error("Start date must be on or before end date.")
        st.stop()

    stores = _store_options()
    store_choice = st.sidebar.selectbox(
        "Store",
        options=["All", *stores.keys()],
        format_func=lambda value: (
            "All stores" if value == "All" else stores.get(value, value)
        ),
        key=f"{key_prefix}_store",
    )

    groups = _group_options()
    group_choice = st.sidebar.selectbox(
        "Product group",
        options=["All", *groups.keys()],
        format_func=lambda value: (
            "All groups" if value == "All" else groups.get(value, value)
        ),
        key=f"{key_prefix}_group",
    )

    brands = _brand_options()
    brand_choice = st.sidebar.selectbox(
        "Brand",
        options=["All", *brands.keys()],
        format_func=lambda value: (
            "All brands" if value == "All" else brands.get(value, value)
        ),
        key=f"{key_prefix}_brand",
    )

    return (
        date_from,
        date_to,
        None if store_choice == "All" else store_choice,
        None if group_choice == "All" else group_choice,
        None if brand_choice == "All" else brand_choice,
    )
