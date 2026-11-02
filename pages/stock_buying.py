"""Stock and buying reports (Reports 1-6)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.report_helpers import (
    add_profit_columns,
    fmt_taka,
    get_last_purchase_prices,
    get_return_summary,
    get_sales_df,
    get_stock_df,
)

_SALES_EPSILON = 0.000001


def _csv_button(df: pd.DataFrame, filename: str, key: str) -> None:
    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def _no_data(message: str = "No data is available for these settings.") -> None:
    st.info(message)


def _format_cover(value: object, daily_sales: object = None) -> str:
    """Make cover days readable and avoid misleading infinite values."""
    cover = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    daily = pd.to_numeric(pd.Series([daily_sales]), errors="coerce").iloc[0]
    if pd.isna(daily) or daily <= _SALES_EPSILON or pd.isna(cover):
        return "Not selling"
    if cover > 365:
        return "1 year+"
    return f"{cover:,.0f}"


def _format_report_table(
    df: pd.DataFrame,
    columns: list[tuple[str, str]],
) -> pd.DataFrame:
    """Select, rename, and format report columns for admin-friendly display."""
    display = df[[source for source, _ in columns]].rename(
        columns=dict(columns)
    ).copy()
    for source, label in columns:
        if source == "daily_sales":
            display[label] = pd.to_numeric(display[label], errors="coerce").map(
                lambda value: "—" if pd.isna(value) else f"{value:,.1f}"
            )
        elif source in {"stock_qty", "reorder_qty", "RED_LEVEL"}:
            display[label] = pd.to_numeric(display[label], errors="coerce").map(
                lambda value: "—" if pd.isna(value) else f"{value:,.0f}"
            )
        elif source == "cover_days":
            daily = df["daily_sales"] if "daily_sales" in df else None
            display[label] = [
                _format_cover(value, daily.iloc[index] if daily is not None else None)
                for index, value in enumerate(display[label])
            ]
        elif source in {"margin_pct", "return_rate_pct"}:
            display[label] = pd.to_numeric(display[label], errors="coerce").map(
                lambda value: "—" if pd.isna(value) else f"{value:,.1f}%"
            )
        elif source in {
            "stock_value",
            "purchase_price",
            "estimated_cost",
            "return_amount",
        }:
            display[label] = pd.to_numeric(display[label], errors="coerce").map(
                lambda value: fmt_taka(value, decimals=0)
            )
    return display


def buy_reason(row: pd.Series) -> str:
    seller = "Top seller: " if row.get("top_seller", False) else ""
    return (
        f"{seller}only {_format_cover(row['cover_days'], row['daily_sales'])} "
        f"of stock, selling {row['daily_sales']:,.1f}/day, "
        f"margin {row['margin_pct']:,.1f}%"
    )


def do_not_buy_reason(
    row: pd.Series, target: int, margin: float, multiplier: int
) -> str:
    reasons: list[str] = []
    overstock = row["cover_days"] > target * multiplier
    if overstock:
        reasons.append(f"Stock for {_format_cover(row['cover_days'], row['daily_sales'])} days, target {target}")
    if row["margin_pct"] < margin:
        reasons.append(f"Margin only {row['margin_pct']:,.1f}%")
    if row["high_return"]:
        reasons.append(f"Returns are {row['return_rate_pct']:,.1f}%")
    if row.get("top_seller", False) and overstock:
        return (
            f"Top seller ({row['daily_sales']:,.1f}/day) but "
            + ", ".join(reasons)
            + ", wait before buying"
        )
    return "; ".join(reasons)


def _settings() -> tuple[int, int, int, float, float, int, int]:
    st.sidebar.header("Buying Rules")
    window = st.sidebar.select_slider(
        "Sales window (days)", options=[30, 60, 90, 180], value=90, key="stock_window"
    )
    target = st.sidebar.slider(
        "Target stock days", 1, 180, 30, key="stock_target_days"
    )
    overstock_multiple = st.sidebar.slider(
        "Strong overstock multiplier (x target)",
        2,
        10,
        3,
        key="stock_overstock_multiple",
    )
    dead = st.sidebar.slider("Dead stock days", 30, 365, 90, key="stock_dead_days")
    margin = st.sidebar.slider(
        "Low margin threshold (%)", 0.0, 100.0, 10.0, 0.5, key="stock_margin"
    )
    return_rate = st.sidebar.slider(
        "High return rate threshold (%)",
        0.0,
        100.0,
        10.0,
        0.5,
        key="stock_return_rate",
    )
    minimum_sold = st.sidebar.slider(
        "Minimum sold qty for return rule",
        1,
        100,
        5,
        key="stock_return_min_sold",
    )
    return window, target, dead, margin, return_rate, minimum_sold, overstock_multiple


def _load_analysis(
    window: int,
    target: int,
    dead: int,
    margin_threshold: float,
    return_rate_threshold: float = 10.0,
    minimum_sold: int = 5,
) -> tuple[pd.DataFrame, date, date]:
    stock = get_stock_df()
    if stock.empty:
        return stock, date.today(), date.today()
    # The helper's public sales loader is used for all sales measures.  An
    # unbounded probe finds the data maximum without using the real clock.
    probe_from = date(2000, 1, 1)
    probe = get_sales_df(probe_from, date.today())
    if probe.empty:
        today = date.today()
        sales = probe
        last_sales = pd.DataFrame(columns=["PRODUCT_ID", "last_sale_date"])
    else:
        today = pd.Timestamp(probe["SALES_DATE"].max()).date()
        last_sales = probe.groupby("PRODUCT_ID", as_index=False).agg(
            last_sale_date=("SALES_DATE", "max")
        )
        sales = probe[
            probe["SALES_DATE"].dt.date >= today - timedelta(days=window - 1)
        ].copy()
    sales = add_profit_columns(sales) if not sales.empty else sales
    if sales.empty:
        grouped = pd.DataFrame(columns=["PRODUCT_ID", "daily_sales", "sales_qty", "sales", "cost", "margin_pct"])
    else:
        grouped = (
            sales.groupby("PRODUCT_ID", as_index=False)
            .agg(
                daily_sales=("qty", lambda x: x.sum() / window),
                sales_qty=("qty", "sum"),
            )
        )
        costed = sales[sales["costed"]].groupby("PRODUCT_ID", as_index=False).agg(
            sales=("line_amount", "sum"),
            cost=("cost_amount", "sum"),
            profit=("profit", "sum"),
        )
        grouped = grouped.merge(costed, on="PRODUCT_ID", how="left")
        grouped["margin_pct"] = grouped["profit"].div(
            grouped["sales"].where(grouped["sales"] != 0)
        ) * 100
    dead_sales = get_sales_df(today - timedelta(days=dead - 1), today)
    if dead_sales.empty:
        dead_grouped = pd.DataFrame(columns=["PRODUCT_ID", "dead_sales_qty", "last_sale_date"])
    else:
        dead_grouped = dead_sales.groupby("PRODUCT_ID", as_index=False).agg(
            dead_sales_qty=("qty", "sum"), last_sale_date=("SALES_DATE", "max")
        )
    result = stock.merge(grouped, on="PRODUCT_ID", how="left")
    result = result.merge(dead_grouped, on="PRODUCT_ID", how="left")
    result = result.drop(columns=["last_sale_date"], errors="ignore").merge(
        last_sales, on="PRODUCT_ID", how="left"
    )
    for column in ("daily_sales", "sales_qty", "sales", "cost", "margin_pct"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    result["dead_sales_qty"] = pd.to_numeric(result["dead_sales_qty"], errors="coerce").fillna(0.0)
    returns = get_return_summary(today - timedelta(days=window - 1), today)
    result = result.merge(returns, on="PRODUCT_ID", how="left")
    result["returned_qty"] = pd.to_numeric(
        result["returned_qty"], errors="coerce"
    ).fillna(0.0)
    result["return_amount"] = pd.to_numeric(
        result["return_amount"], errors="coerce"
    ).fillna(0.0)
    result["return_rate_pct"] = result["returned_qty"].div(
        result["sales_qty"].where(result["sales_qty"] > 0)
    ).mul(100).fillna(0.0)
    result["cover_days"] = result["stock_qty"].div(
        result["daily_sales"].where(result["daily_sales"] > 0)
    )
    result["reorder_qty"] = np.maximum(
        0, np.ceil(result["daily_sales"] * target - result["stock_qty"])
    )
    result["purchase_price"] = result["avg_cost"]
    result["price_source"] = "Stock AVG_COST"
    prices = get_last_purchase_prices()
    if not prices.empty:
        result = result.merge(prices[["PRODUCT_ID", "purchase_price"]].rename(
            columns={"purchase_price": "last_purchase_price"}
        ), on="PRODUCT_ID", how="left")
        found = result["last_purchase_price"].notna() & (result["last_purchase_price"] > 0)
        result.loc[found, "purchase_price"] = result.loc[found, "last_purchase_price"]
        result.loc[found, "price_source"] = "Last purchase UNIT_PRICE"
        result = result.drop(columns=["last_purchase_price"])
    result["estimated_cost"] = result["reorder_qty"] * result["purchase_price"]
    result["high_return"] = (
        (result["sales_qty"] >= minimum_sold)
        & (result["return_rate_pct"] > return_rate_threshold)
    )
    result["top_seller"] = False
    sold_products = result["sales"] > 0
    if sold_products.any():
        sales_rank = result.loc[sold_products, "sales"].rank(
            method="min", ascending=False
        )
        top_seller_limit = max(1, int(np.ceil(sold_products.sum() * 0.20)))
        result.loc[sold_products, "top_seller"] = sales_rank <= top_seller_limit
    return result, today, today - timedelta(days=dead - 1)


def _display(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(
        columns={
            "PRODUCT_NAME": "Product", "daily_sales": "Daily sales", "stock_qty": "Stock",
            "cover_days": "Cover days", "margin_pct": "Margin %",
            "reorder_qty": "Suggested reorder qty", "stock_value": "Stock value",
            "purchase_price": "Purchase price", "price_source": "Price used",
            "estimated_cost": "Estimated cost", "RED_LEVEL": "RED_LEVEL",
        }
    )


def buy_now(df: pd.DataFrame, target: int, margin_threshold: float) -> pd.DataFrame:
    """Products selling briskly, under target cover, and above margin floor."""
    return df[
        (df["daily_sales"] > 0)
        & (df["cover_days"] < target)
        & (df["margin_pct"] >= margin_threshold)
    ].sort_values(["cover_days", "daily_sales"], ascending=[True, False])


def do_not_buy(
    df: pd.DataFrame,
    target: int,
    margin_threshold: float,
    overstock_multiple: int = 3,
) -> pd.DataFrame:
    """Products with clearly bad purchase signals, excluding dead stock."""
    result = df[
        (df["daily_sales"] > 0)
        & (
            (df["cover_days"] > target * overstock_multiple)
            | (df["margin_pct"] < margin_threshold)
            | df["high_return"]
        )
    ].copy()

    result["Reason"] = result.apply(
        lambda row: do_not_buy_reason(
            row, target, margin_threshold, overstock_multiple
        ),
        axis=1,
    )
    return result.sort_values("stock_value", ascending=False)


def _tab_buy_now(df: pd.DataFrame, target: int, margin: float) -> None:
    st.caption("Buy products selling quickly when their stock will run out before the target holding period.")
    table = buy_now(df, target, margin)
    if table.empty:
        _no_data("No products currently meet the Buy Now rules.")
        return
    table["Reason"] = table.apply(buy_reason, axis=1)
    display = _format_report_table(
        table,
        [
            ("PRODUCT_NAME", "Product"),
            ("daily_sales", "Daily sales"),
            ("stock_qty", "Stock"),
            ("cover_days", "Cover days"),
            ("margin_pct", "Margin %"),
            ("reorder_qty", "Suggested reorder qty"),
            ("Reason", "Reason"),
        ],
    )
    st.dataframe(display, hide_index=True, width="stretch")
    _csv_button(display, "buy_now.csv", "buy_now_csv")


def _tab_do_not_buy(
    df: pd.DataFrame, target: int, margin: float, overstock_multiple: int
) -> None:
    st.caption("Avoid buying products that are overstocked, barely selling, low-margin, or otherwise tied up in inventory.")
    table = do_not_buy(df, target, margin, overstock_multiple)
    if table.empty:
        _no_data("No products currently meet the Do Not Buy rules.")
        return
    display = _format_report_table(
        table,
        [
            ("PRODUCT_NAME", "Product"),
            ("daily_sales", "Daily sales"),
            ("stock_qty", "Stock"),
            ("cover_days", "Cover days"),
            ("margin_pct", "Margin %"),
            ("stock_value", "Money tied up in stock"),
            ("Reason", "Reason"),
        ],
    )
    st.dataframe(display, hide_index=True, width="stretch")
    _csv_button(display, "do_not_buy.csv", "do_not_buy_csv")


def _tab_reorder(df: pd.DataFrame) -> None:
    st.caption("This list shows how many units to order and the expected budget using the latest available buying price.")
    table = df[df["reorder_qty"] > 0].sort_values("estimated_cost", ascending=False)
    st.metric("Estimated purchase budget", fmt_taka(table["estimated_cost"].sum()))
    if table.empty:
        _no_data("No reorder quantity is suggested.")
        return
    display = _format_report_table(
        table,
        [
            ("PRODUCT_NAME", "Product"),
            ("stock_qty", "Stock"),
            ("daily_sales", "Daily sales"),
            ("cover_days", "Cover days"),
            ("reorder_qty", "Suggested reorder qty"),
            ("purchase_price", "Purchase price"),
            ("price_source", "Price used"),
            ("estimated_cost", "Estimated cost"),
        ],
    )
    st.dataframe(display, hide_index=True, width="stretch")
    _csv_button(display, "reorder_suggestion.csv", "reorder_csv")


def _tab_cover(df: pd.DataFrame, target: int) -> None:
    st.caption("Stock cover shows how long current inventory should last at the recent daily sales rate.")
    table = df[df["stock_qty"] > 0].copy()
    if table.empty:
        _no_data("No products currently have stock.")
        return
    table["Label"] = np.select(
        [
            table["daily_sales"] <= 0,
            table["cover_days"] < 7,
            table["cover_days"] < target,
            table["cover_days"] > target * 3,
        ],
        ["No sales", "Critical", "Low", "Overstock"],
        default="Healthy",
    )
    counts = table["Label"].value_counts().reindex(
        ["No sales", "Critical", "Low", "Healthy", "Overstock"], fill_value=0
    )
    st.bar_chart(counts)
    display = _format_report_table(
        table,
        [
            ("PRODUCT_NAME", "Product"),
            ("stock_qty", "Stock"),
            ("daily_sales", "Daily sales"),
            ("cover_days", "Cover days"),
            ("Label", "Label"),
        ],
    )
    st.dataframe(display, hide_index=True, width="stretch")
    _csv_button(display, "stock_cover_days.csv", "cover_csv")


def _tab_dead_stock(df: pd.DataFrame, dead: int, today: date) -> None:
    st.caption("Dead stock has units on hand but no sale during the selected dead-stock period.")
    table = df[(df["stock_qty"] > 0) & (df["dead_sales_qty"] <= 0)].copy()
    table = table.sort_values("stock_value", ascending=False)
    st.metric("Money stuck in dead stock", fmt_taka(table["stock_value"].sum()))
    if table.empty:
        _no_data("No dead stock was found.")
        return
    table["Last sale"] = table["last_sale_date"].dt.strftime("%d %b %Y").fillna("Never sold")
    display = _format_report_table(
        table,
        [
            ("PRODUCT_NAME", "Product"),
            ("stock_qty", "Stock"),
            ("stock_value", "Stock value"),
            ("Last sale", "Last sale"),
        ],
    )
    st.dataframe(display, hide_index=True, width="stretch")
    _csv_button(display, "dead_stock.csv", "dead_stock_csv")


def _tab_stockout(df: pd.DataFrame) -> None:
    st.caption("These products are selling but have no stock, or have fallen below their product reorder level.")
    table = df[(df["daily_sales"] > 0) & ((df["stock_qty"] <= 0) | (df["stock_qty"] < df["RED_LEVEL"]))].copy()
    table["Stockout timing"] = "Not inferable from snapshot"
    if table.empty:
        _no_data("No stockout-risk products were found.")
        return
    display = _format_report_table(
        table,
        [
            ("PRODUCT_NAME", "Product"),
            ("stock_qty", "Stock"),
            ("RED_LEVEL", "RED_LEVEL"),
            ("daily_sales", "Daily sales"),
            ("Stockout timing", "Stockout timing"),
        ],
    )
    st.dataframe(display, hide_index=True, width="stretch")
    _csv_button(display, "stockout_risk.csv", "stockout_csv")


def main() -> None:
    st.title("Stock and Buying")
    st.caption("Use these views to decide what to buy, what to hold, and where sales may be lost.")
    window, target, dead, margin, return_rate, minimum_sold, overstock_multiple = _settings()
    try:
        df, today, _ = _load_analysis(
            window, target, dead, margin, return_rate, minimum_sold
        )
    except Exception as exc:
        st.error(f"Could not load stock and sales data: {exc}")
        st.stop()
    if df.empty:
        _no_data("No stock data is available.")
        st.stop()
    tabs = st.tabs(["Buy Now", "Do Not Buy", "Reorder Suggestion", "Stock Cover Days", "Dead Stock", "Stockout Risk"])
    with tabs[0]:
        _tab_buy_now(df, target, margin)
    with tabs[1]:
        _tab_do_not_buy(df, target, margin, overstock_multiple)
    with tabs[2]:
        _tab_reorder(df)
    with tabs[3]:
        _tab_cover(df, target)
    with tabs[4]:
        _tab_dead_stock(df, dead, today)
    with tabs[5]:
        _tab_stockout(df)


main()
