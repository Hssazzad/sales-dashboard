"""Profit Report page - five profit-focused analytical tabs.

Reports:
  13. Product Profit
  14. Group and Brand Profit
  15. Problem Products
  16. Monthly Profit Trend
  17. Store Profit

Registered in src/navigation.py and run by app.py via st.navigation().
This script must NOT call st.set_page_config() or auth.require_login().
"""

from __future__ import annotations

from pathlib import Path
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# Make src/ importable when Streamlit runs this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.report_helpers import (
    add_profit_columns,
    fmt_taka,
    get_sales_df,
    render_report_filters,
)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _no_data(
    message: str = "No data matches the current filters. Try widening the date range.",
) -> None:
    """Show a friendly empty-state message inside a tab."""
    st.info(message)


def _csv_button(
    df: pd.DataFrame,
    *,
    filename: str,
    key: str,
    label: str = "Download CSV",
) -> None:
    """Offer the table as a UTF-8 (Excel-friendly) CSV download."""
    st.download_button(
        label=label,
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def _fmt_pct(value: float | None) -> str:
    """Format a percentage safely, including None/NaN."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.2f}%"


def _safe_margin(profit: pd.Series, sales: pd.Series) -> pd.Series:
    """Return profit / sales x 100 with zero sales producing NaN."""
    return profit / sales.where(sales != 0) * 100


# ---------------------------------------------------------------------------
# Profit aggregations
# ---------------------------------------------------------------------------

def _product_profit_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate costed rows to one row per product."""
    summary = (
        df.groupby(["PRODUCT_ID", "PRODUCT_NAME"], as_index=False)
        .agg(
            group=("PRODUCT_GROUP_NAME", "first"),
            brand=("BRAND_NAME", "first"),
            qty=("qty", "sum"),
            sales=("line_amount", "sum"),
            cost=("cost_amount", "sum"),
            profit=("profit", "sum"),
            max_discount_pct=("DISCOUNT_PCT", "max"),
        )
    )
    summary["margin_pct"] = _safe_margin(summary["profit"], summary["sales"])
    summary["max_discount_pct"] = summary["max_discount_pct"].fillna(0.0)
    return summary


def _dimension_profit_summary(
    df: pd.DataFrame,
    id_col: str,
    name_col: str,
) -> pd.DataFrame:
    """Aggregate costed rows by a dimension such as group or brand."""
    summary = (
        df.groupby([id_col, name_col], as_index=False)
        .agg(
            sales=("line_amount", "sum"),
            cost=("cost_amount", "sum"),
            profit=("profit", "sum"),
        )
    )
    summary["margin_pct"] = _safe_margin(summary["profit"], summary["sales"])

    total_profit = summary["profit"].sum()
    if total_profit:
        summary["share_pct"] = summary["profit"] / total_profit * 100
    else:
        summary["share_pct"] = 0.0

    return summary.sort_values("profit", ascending=False).reset_index(drop=True)


def _monthly_profit_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate costed rows by calendar month."""
    monthly = (
        df.assign(month=df["SALES_DATE"].dt.to_period("M").dt.to_timestamp())
        .groupby("month", as_index=False)
        .agg(
            sales=("line_amount", "sum"),
            cost=("cost_amount", "sum"),
            profit=("profit", "sum"),
        )
    )
    monthly["margin_pct"] = _safe_margin(monthly["profit"], monthly["sales"])
    return monthly.sort_values("month").reset_index(drop=True)


def _product_month_pivot(
    df: pd.DataFrame,
    top_n: int = 15,
) -> tuple[pd.DataFrame, list[str]]:
    """Return a product x month profit pivot for the top products."""
    top = (
        df.groupby("PRODUCT_ID", as_index=False)
        .agg(
            PRODUCT_NAME=("PRODUCT_NAME", "first"),
            profit=("profit", "sum"),
        )
        .nlargest(top_n, "profit")
    )

    months = df.assign(month=df["SALES_DATE"].dt.to_period("M").dt.to_timestamp())
    pivot = months[months["PRODUCT_ID"].isin(top["PRODUCT_ID"])].pivot_table(
        index="PRODUCT_ID",
        columns="month",
        values="profit",
        aggfunc="sum",
        fill_value=0,
    )
    if pivot.empty:
        return pd.DataFrame(), []

    pivot = pivot.reindex(columns=sorted(pivot.columns))
    month_columns = [column.strftime("%b %Y") for column in pivot.columns]
    pivot.columns = month_columns
    pivot = pivot.reset_index().merge(
        top[["PRODUCT_ID", "PRODUCT_NAME"]],
        on="PRODUCT_ID",
        how="left",
    )
    pivot["Total"] = pivot[month_columns].sum(axis=1)
    pivot = pivot.sort_values("Total", ascending=False).reset_index(drop=True)
    pivot = pivot.rename(
        columns={"PRODUCT_NAME": "Product", "PRODUCT_ID": "Product ID"}
    )

    columns = ["Product", "Product ID", *month_columns, "Total"]
    return pivot[columns], month_columns


def _problem_label(row: pd.Series) -> str:
    """Build the Problem column, keeping all applicable flags."""
    labels: list[str] = []
    if row["negative_margin"]:
        labels.append("Negative margin")
    elif row["low_margin"]:
        labels.append("Low margin")
    if row["high_discount"]:
        labels.append("High discount")
    return "; ".join(labels)


def _product_profit_display(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(
        columns={
            "PRODUCT_NAME": "Product",
            "group": "Group",
            "brand": "Brand",
            "qty": "Qty",
            "sales": "Sales",
            "cost": "Cost",
            "profit": "Profit",
            "margin_pct": "Margin %",
        }
    )[
        [
            "Rank",
            "Product",
            "Group",
            "Brand",
            "Qty",
            "Sales",
            "Cost",
            "Profit",
            "Margin %",
        ]
    ]


def _product_profit_column_config() -> dict[str, object]:
    return {
        "Rank": st.column_config.NumberColumn(format="%d", width="small"),
        "Qty": st.column_config.NumberColumn(format="%,.2f"),
        "Sales": st.column_config.NumberColumn(format="%,.2f"),
        "Cost": st.column_config.NumberColumn(format="%,.2f"),
        "Profit": st.column_config.NumberColumn(format="%,.2f"),
        "Margin %": st.column_config.NumberColumn(format="%.2f%%"),
    }


def _dimension_display(
    frame: pd.DataFrame,
    name_col: str,
    label: str,
) -> pd.DataFrame:
    display = frame.rename(
        columns={
            name_col: label,
            "sales": "Sales",
            "cost": "Cost",
            "profit": "Profit",
            "margin_pct": "Margin %",
            "share_pct": "Share of Profit %",
        }
    )[[label, "Sales", "Cost", "Profit", "Margin %", "Share of Profit %"]]
    display.insert(0, "Rank", range(1, len(display) + 1))
    return display


def _dimension_column_config() -> dict[str, object]:
    return {
        "Rank": st.column_config.NumberColumn(format="%d", width="small"),
        "Sales": st.column_config.NumberColumn(format="%,.2f"),
        "Cost": st.column_config.NumberColumn(format="%,.2f"),
        "Profit": st.column_config.NumberColumn(format="%,.2f"),
        "Margin %": st.column_config.NumberColumn(format="%.2f%%"),
        "Share of Profit %": st.column_config.NumberColumn(format="%.2f%%"),
    }


def _problem_display(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(
        columns={
            "PRODUCT_NAME": "Product",
            "group": "Group",
            "brand": "Brand",
            "qty": "Qty",
            "sales": "Sales",
            "cost": "Cost",
            "profit": "Profit",
            "margin_pct": "Margin %",
            "max_discount_pct": "Discount %",
        }
    )[
        [
            "Product",
            "Group",
            "Brand",
            "Qty",
            "Sales",
            "Cost",
            "Profit",
            "Margin %",
            "Discount %",
            "Problem",
        ]
    ]


# ---------------------------------------------------------------------------
# 13. Product Profit
# ---------------------------------------------------------------------------

def _tab_product_profit(df: pd.DataFrame) -> None:
    st.caption(
        "Shows sales, cost, profit and margin for each product; use the toggle "
        "to review the lowest-profit products instead."
    )

    if df.empty:
        _no_data("No costed sales rows match the current filters.")
        return

    summary = _product_profit_summary(df)
    if summary.empty:
        _no_data("No products match the current filters.")
        return

    lowest = st.toggle(
        "Show lowest profit instead",
        value=False,
        key="profit_lowest",
    )

    if lowest:
        selected = summary.nsmallest(20, "profit").sort_values(
            "profit", ascending=True
        )
        title = "Lowest 20 products by profit"
        filename = "product_profit_lowest20.csv"
    else:
        selected = summary.nlargest(20, "profit").sort_values(
            "profit", ascending=False
        )
        title = "Top 20 products by profit"
        filename = "product_profit_top20.csv"

    selected = selected.reset_index(drop=True)
    selected.insert(0, "Rank", range(1, len(selected) + 1))

    st.subheader(title)
    st.bar_chart(
        selected.set_index("PRODUCT_NAME")["profit"],
        horizontal=True,
        height=max(420, len(selected) * 26),
        sort=False,
    )

    display = _product_profit_display(selected)
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config=_product_profit_column_config(),
    )
    _csv_button(display, filename=filename, key="product_profit_csv")

    with st.expander("Show all products"):
        full = summary.sort_values("profit", ascending=False).reset_index(drop=True)
        full.insert(0, "Rank", range(1, len(full) + 1))
        full_display = _product_profit_display(full)
        st.dataframe(
            full_display,
            hide_index=True,
            width="stretch",
            height=500,
            column_config=_product_profit_column_config(),
        )
        _csv_button(
            full_display,
            filename="product_profit_all.csv",
            key="product_profit_all_csv",
        )


# ---------------------------------------------------------------------------
# 14. Group and Brand Profit
# ---------------------------------------------------------------------------

def _tab_group_brand_profit(df: pd.DataFrame) -> None:
    st.caption(
        "Compares profit, margin and share of total profit by product group "
        "and by brand."
    )

    if df.empty:
        _no_data("No costed sales rows match the current filters.")
        return

    st.subheader("By product group")
    group = _dimension_profit_summary(
        df,
        "PRODUCT_GROUP_ID",
        "PRODUCT_GROUP_NAME",
    )
    if group.empty:
        st.info("No product groups match the current filters.")
    else:
        st.bar_chart(
            group.set_index("PRODUCT_GROUP_NAME")["profit"],
            horizontal=True,
            height=max(360, len(group) * 28),
            sort=False,
        )
        group_display = _dimension_display(group, "PRODUCT_GROUP_NAME", "Group")
        st.dataframe(
            group_display,
            hide_index=True,
            width="stretch",
            height=400,
            column_config=_dimension_column_config(),
        )
        _csv_button(
            group_display,
            filename="group_profit.csv",
            key="group_profit_csv",
        )

    st.subheader("By brand")
    brand = _dimension_profit_summary(df, "BRAND_ID", "BRAND_NAME")
    if brand.empty:
        st.info("No brands match the current filters.")
    else:
        st.bar_chart(
            brand.set_index("BRAND_NAME")["profit"],
            horizontal=True,
            height=max(360, len(brand) * 28),
            sort=False,
        )
        brand_display = _dimension_display(brand, "BRAND_NAME", "Brand")
        st.dataframe(
            brand_display,
            hide_index=True,
            width="stretch",
            height=400,
            column_config=_dimension_column_config(),
        )
        _csv_button(
            brand_display,
            filename="brand_profit.csv",
            key="brand_profit_csv",
        )


# ---------------------------------------------------------------------------
# 15. Problem Products
# ---------------------------------------------------------------------------

def _tab_problem_products(df: pd.DataFrame) -> None:
    st.caption(
        "Flags products with negative margin, margin below your threshold, or "
        "a high maximum discount; review these for pricing or purchasing."
    )

    if df.empty:
        _no_data("No costed sales rows match the current filters.")
        return

    col_low, col_discount = st.columns(2)
    with col_low:
        low_threshold = st.slider(
            "Low-margin threshold (%)",
            min_value=0,
            max_value=100,
            value=10,
            step=1,
            key="profit_low_margin",
        )
    with col_discount:
        high_threshold = st.slider(
            "High-discount threshold (%)",
            min_value=0,
            max_value=100,
            value=15,
            step=1,
            key="profit_high_discount",
        )

    products = _product_profit_summary(df)
    products["negative_margin"] = products["margin_pct"] < 0
    products["low_margin"] = (
        (products["margin_pct"] >= 0)
        & (products["margin_pct"] < low_threshold)
    )
    products["high_discount"] = (
        products["max_discount_pct"] > high_threshold
    )

    problems = products[
        products["negative_margin"]
        | products["low_margin"]
        | products["high_discount"]
    ].copy()

    if problems.empty:
        st.info(
            "No products meet the current problem thresholds. "
            "Try lowering the thresholds."
        )
        return

    problems["Problem"] = problems.apply(_problem_label, axis=1)
    problems["severity"] = np.select(
        [problems["negative_margin"], problems["low_margin"]],
        [0, 1],
        default=2,
    )
    problems = problems.sort_values(
        ["severity", "profit"],
        ascending=[True, True],
    ).reset_index(drop=True)

    st.caption(
        f"{len(problems):,} products flagged · "
        f"Negative margin: {int(products['negative_margin'].sum()):,} · "
        f"Low margin: {int(products['low_margin'].sum()):,} · "
        f"High discount: {int(products['high_discount'].sum()):,}"
    )

    chart_df = problems.nsmallest(15, "profit").sort_values(
        "profit", ascending=True
    )
    st.subheader("Lowest-profit flagged products")
    st.bar_chart(
        chart_df.set_index("PRODUCT_NAME")["profit"],
        horizontal=True,
        height=max(320, len(chart_df) * 26),
        sort=False,
    )

    display = _problem_display(problems)
    st.subheader("Problem product list")
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=500,
        column_config={
            "Qty": st.column_config.NumberColumn(format="%,.2f"),
            "Sales": st.column_config.NumberColumn(format="%,.2f"),
            "Cost": st.column_config.NumberColumn(format="%,.2f"),
            "Profit": st.column_config.NumberColumn(format="%,.2f"),
            "Margin %": st.column_config.NumberColumn(format="%.2f%%"),
            "Discount %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    _csv_button(
        display,
        filename="problem_products.csv",
        key="problem_products_csv",
    )


# ---------------------------------------------------------------------------
# 16. Monthly Profit Trend
# ---------------------------------------------------------------------------

def _tab_monthly_profit(df: pd.DataFrame) -> None:
    st.caption(
        "Shows monthly sales, profit and margin; the first and last months "
        "in the selected period can be partial."
    )

    if df.empty:
        _no_data("No costed sales rows match the current filters.")
        return

    monthly = _monthly_profit_summary(df)
    if monthly.empty:
        _no_data("No monthly profit data for the current filters.")
        return

    monthly["month"] = pd.to_datetime(monthly["month"])
    long = monthly.melt(
        id_vars=["month", "margin_pct"],
        value_vars=["sales", "profit"],
        var_name="measure",
        value_name="value",
    )
    long["measure"] = long["measure"].map(
        {"sales": "Sales", "profit": "Profit"}
    )

    money = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X(
            "month:T",
            title=None,
            axis=alt.Axis(format="%b %Y"),
        ),
        y=alt.Y("value:Q", title="Amount (৳)"),
        color=alt.Color(
            "measure:N",
            title="Measure",
            scale=alt.Scale(
                domain=["Sales", "Profit"],
                range=["#4C78A8", "#54A24B"],
            ),
        ),
        tooltip=[
            alt.Tooltip("month:T", title="Month", format="%b %Y"),
            alt.Tooltip("measure:N", title="Measure"),
            alt.Tooltip("value:Q", title="Amount", format=",.2f"),
        ],
    )

    margin = alt.Chart(monthly).mark_line(
        point=True,
        color="#E45756",
        strokeDash=[5, 3],
    ).encode(
        x=alt.X(
            "month:T",
            title=None,
            axis=alt.Axis(format="%b %Y"),
        ),
        y=alt.Y(
            "margin_pct:Q",
            title="Margin %",
            axis=alt.Axis(format=".1f", orient="right"),
        ),
        tooltip=[
            alt.Tooltip("month:T", title="Month", format="%b %Y"),
            alt.Tooltip("margin_pct:Q", title="Margin %", format=".2f"),
        ],
    )

    chart = (
        alt.layer(money, margin)
        .resolve_scale(y="independent")
        .properties(height=420)
    )

    st.subheader("Monthly sales, profit and margin")
    st.altair_chart(chart, width="stretch")
    st.caption(
        "Left axis: sales and profit (৳). Right axis: margin %. "
        "The first and last months in the selected period may be partial."
    )

    monthly_display = monthly.assign(
        Month=monthly["month"].dt.strftime("%b %Y")
    ).rename(
        columns={
            "sales": "Sales",
            "cost": "Cost",
            "profit": "Profit",
            "margin_pct": "Margin %",
        }
    )[["Month", "Sales", "Cost", "Profit", "Margin %"]]

    st.subheader("Monthly totals")
    st.dataframe(
        monthly_display,
        hide_index=True,
        width="stretch",
        column_config={
            "Sales": st.column_config.NumberColumn(format="%,.2f"),
            "Cost": st.column_config.NumberColumn(format="%,.2f"),
            "Profit": st.column_config.NumberColumn(format="%,.2f"),
            "Margin %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    _csv_button(
        monthly_display,
        filename="monthly_profit_totals.csv",
        key="monthly_totals_csv",
    )

    st.subheader("Top 15 products by profit, by month")
    pivot, month_columns = _product_month_pivot(df)
    if pivot.empty:
        _no_data("No product-month profit data for the current filters.")
        return

    st.dataframe(
        pivot,
        hide_index=True,
        width="stretch",
        height=420,
        column_config={
            column: st.column_config.NumberColumn(format="%,.2f")
            for column in [*month_columns, "Total"]
        },
    )
    _csv_button(
        pivot,
        filename="monthly_product_profit_pivot.csv",
        key="monthly_pivot_csv",
    )


# ---------------------------------------------------------------------------
# 17. Store Profit
# ---------------------------------------------------------------------------

def _tab_store_profit(df: pd.DataFrame) -> None:
    st.caption(
        "Shows sales, profit and margin per store; STO001 accounts for about "
        "97.8% of all rows, so compare stores with that in mind."
    )

    if df.empty:
        _no_data("No costed sales rows match the current filters.")
        return

    store = (
        df.groupby(["STORE_ID", "STORE_NAME"], as_index=False)
        .agg(
            sales=("line_amount", "sum"),
            cost=("cost_amount", "sum"),
            profit=("profit", "sum"),
        )
    )
    if store.empty:
        _no_data("No stores match the current filters.")
        return

    store["margin_pct"] = _safe_margin(store["profit"], store["sales"])
    total_sales = store["sales"].sum()
    store["share_pct"] = (
        store["sales"] / total_sales * 100 if total_sales else 0.0
    )
    store = store.sort_values("sales", ascending=False).reset_index(drop=True)

    top = store.iloc[0]
    st.caption(
        f"In this period, {top['STORE_NAME']} has the largest sales share "
        f"({top['share_pct']:.1f}%)."
    )

    chart = store.set_index("STORE_NAME")[["sales", "profit"]].rename(
        columns={"sales": "Sales", "profit": "Profit"}
    )
    st.subheader("Sales and profit by store")
    st.bar_chart(chart, stack=False, height=360, sort=False)

    display = store.rename(
        columns={
            "STORE_NAME": "Store",
            "sales": "Sales",
            "cost": "Cost",
            "profit": "Profit",
            "margin_pct": "Margin %",
            "share_pct": "Share of Sales %",
        }
    )[["Store", "Sales", "Cost", "Profit", "Margin %", "Share of Sales %"]]
    display.insert(0, "Rank", range(1, len(display) + 1))

    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d", width="small"),
            "Sales": st.column_config.NumberColumn(format="%,.2f"),
            "Cost": st.column_config.NumberColumn(format="%,.2f"),
            "Profit": st.column_config.NumberColumn(format="%,.2f"),
            "Margin %": st.column_config.NumberColumn(format="%.2f%%"),
            "Share of Sales %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    _csv_button(
        display,
        filename="store_profit.csv",
        key="store_profit_csv",
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Profit Report")
    st.caption(
        "Five profit views using AVG_COST. Zero-cost lines are excluded from "
        "profit and margin and shown separately."
    )

    date_from, date_to, store_id, group_id, brand_id = render_report_filters(
        key_prefix="profit_report"
    )

    try:
        df = get_sales_df(
            date_from,
            date_to,
            store=store_id,
            group=group_id,
            brand=brand_id,
        )
    except Exception:
        st.error(
            "Could not load sales data. Check that MySQL is running and that "
            ".env has the correct database settings."
        )
        st.stop()

    df = add_profit_columns(df)
    zero_cost_df = df[~df["costed"]].copy()
    costed_df = df[df["costed"]].copy()

    if not zero_cost_df.empty:
        st.warning(
            f"{len(zero_cost_df):,} lines have zero cost, excluded from profit "
            f"and margin (sales amount "
            f"{fmt_taka(zero_cost_df['line_amount'].sum())})."
        )
        with st.expander("Show zero-cost lines"):
            zero_display = zero_cost_df.rename(
                columns={
                    "SALES_DATE": "Date",
                    "SALES_ID": "Sales ID",
                    "PRODUCT_NAME": "Product",
                    "STORE_NAME": "Store",
                    "qty": "Qty",
                    "UNIT_PRICE": "Unit Price",
                    "line_amount": "Sales Amount",
                    "AVG_COST": "AVG Cost",
                    "ORG_COST": "ORG Cost",
                    "DISCOUNT_PCT": "Discount %",
                }
            )[
                [
                    "Date",
                    "Sales ID",
                    "Product",
                    "Store",
                    "Qty",
                    "Unit Price",
                    "Sales Amount",
                    "AVG Cost",
                    "ORG Cost",
                    "Discount %",
                ]
            ]
            st.dataframe(
                zero_display,
                hide_index=True,
                width="stretch",
                height=320,
                column_config={
                    "Date": st.column_config.DateColumn(
                        format="DD MMM YYYY"
                    ),
                    "Qty": st.column_config.NumberColumn(format="%,.2f"),
                    "Unit Price": st.column_config.NumberColumn(
                        format="%,.2f"
                    ),
                    "Sales Amount": st.column_config.NumberColumn(
                        format="%,.2f"
                    ),
                    "AVG Cost": st.column_config.NumberColumn(format="%,.2f"),
                    "ORG Cost": st.column_config.NumberColumn(format="%,.2f"),
                    "Discount %": st.column_config.NumberColumn(
                        format="%.2f%%"
                    ),
                },
            )
            _csv_button(
                zero_display,
                filename="zero_cost_lines.csv",
                key="zero_cost_csv",
            )

    if not costed_df.empty:
        total_sales = costed_df["line_amount"].sum()
        total_cost = costed_df["cost_amount"].sum()
        total_profit = costed_df["profit"].sum()
        total_margin = (
            total_profit / total_sales * 100 if total_sales else None
        )

        col_sales, col_cost, col_profit, col_margin = st.columns(4)
        col_sales.metric("Sales amount", fmt_taka(total_sales))
        col_cost.metric("Cost", fmt_taka(total_cost))
        col_profit.metric("Profit", fmt_taka(total_profit))
        col_margin.metric("Margin", _fmt_pct(total_margin))

    st.caption(
        f"{len(costed_df):,} costed rows · "
        f"{date_from:%d %b %Y} to {date_to:%d %b %Y}"
    )

    tabs = st.tabs(
        [
            "Product Profit",
            "Group & Brand Profit",
            "Problem Products",
            "Monthly Profit Trend",
            "Store Profit",
        ]
    )

    with tabs[0]:
        _tab_product_profit(costed_df)
    with tabs[1]:
        _tab_group_brand_profit(costed_df)
    with tabs[2]:
        _tab_problem_products(costed_df)
    with tabs[3]:
        _tab_monthly_profit(costed_df)
    with tabs[4]:
        _tab_store_profit(costed_df)


main()
