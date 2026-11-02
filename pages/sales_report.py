"""Sales Report page - six product-level analytical tabs.

Reports:
  7. Top Sellers
  8. Bottom Sellers
  9. ABC Analysis
 10. Group-wise Best and Worst
 11. Brand Performance
 12. Growing vs Declining

Registered in src/navigation.py and run by app.py via st.navigation().
This script must NOT call st.set_page_config() or auth.require_login().
"""

from __future__ import annotations

from datetime import date, timedelta
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

from src.report_helpers import fmt_taka, get_sales_df, render_report_filters


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


def _product_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the filtered rows to one row per product."""
    if df.empty:
        return pd.DataFrame(
            columns=["PRODUCT_ID", "PRODUCT_NAME", "qty", "line_amount"]
        )
    return (
        df.groupby(["PRODUCT_ID", "PRODUCT_NAME"], as_index=False)
        .agg(qty=("qty", "sum"), line_amount=("line_amount", "sum"))
        .reset_index(drop=True)
    )


def _ranked_product_table(
    summary: pd.DataFrame,
    metric: str,
    n: int,
    *,
    ascending: bool,
) -> pd.DataFrame:
    """Return the requested top/bottom products with a rank column."""
    if ascending:
        ranked = summary.nsmallest(n, metric).sort_values(metric, ascending=True)
    else:
        ranked = summary.nlargest(n, metric).sort_values(metric, ascending=False)

    ranked = ranked.reset_index(drop=True)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    return ranked


def _product_display(ranked: pd.DataFrame) -> pd.DataFrame:
    return ranked.rename(
        columns={
            "rank": "Rank",
            "PRODUCT_NAME": "Product",
            "qty": "Qty",
            "line_amount": "Amount",
        }
    )[["Rank", "Product", "Qty", "Amount"]]


def _product_column_config() -> dict[str, object]:
    return {
        "Rank": st.column_config.NumberColumn(format="%d", width="small"),
        "Qty": st.column_config.NumberColumn(format="%,.2f"),
        "Amount": st.column_config.NumberColumn(format="%,.2f"),
    }


# ---------------------------------------------------------------------------
# 7. Top Sellers
# ---------------------------------------------------------------------------

def _tab_top_sellers(df: pd.DataFrame) -> None:
    st.caption(
        "The products with the highest sales in the selected period, "
        "ranked by quantity and by sales amount."
    )

    if df.empty:
        _no_data()
        return

    n = st.selectbox("Number of products", (10, 20, 50), index=0, key="top_n")
    summary = _product_summary(df)
    if summary.empty:
        _no_data()
        return

    col_qty, col_amount = st.columns(2)

    with col_qty:
        st.subheader(f"Top {n} by quantity")
        ranked = _ranked_product_table(summary, "qty", n, ascending=False)
        st.bar_chart(
            ranked.set_index("PRODUCT_NAME")["qty"],
            horizontal=True,
            height=max(320, len(ranked) * 26),
            sort=False,
        )
        display = _product_display(ranked)
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            column_config=_product_column_config(),
        )
        _csv_button(display, filename="top_sellers_by_qty.csv", key="top_qty_csv")

    with col_amount:
        st.subheader(f"Top {n} by amount")
        ranked = _ranked_product_table(summary, "line_amount", n, ascending=False)
        st.bar_chart(
            ranked.set_index("PRODUCT_NAME")["line_amount"],
            horizontal=True,
            height=max(320, len(ranked) * 26),
            sort=False,
        )
        display = _product_display(ranked)
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            column_config=_product_column_config(),
        )
        _csv_button(
            display,
            filename="top_sellers_by_amount.csv",
            key="top_amount_csv",
        )


# ---------------------------------------------------------------------------
# 8. Bottom Sellers
# ---------------------------------------------------------------------------

def _tab_bottom_sellers(df: pd.DataFrame) -> None:
    st.caption(
        "Products that did sell in the period but had the lowest quantity "
        "or amount. Products with no sales are excluded."
    )

    if df.empty:
        _no_data()
        return

    n = st.selectbox("Number of products", (10, 20, 50), index=0, key="bottom_n")
    summary = _product_summary(df)

    # A product "did sell" when it has positive net quantity in the period.
    summary = summary[summary["qty"] > 0]
    if summary.empty:
        _no_data("No products with positive sales in this period.")
        return

    col_qty, col_amount = st.columns(2)

    with col_qty:
        st.subheader(f"Bottom {n} by quantity")
        ranked = _ranked_product_table(summary, "qty", n, ascending=True)
        st.bar_chart(
            ranked.set_index("PRODUCT_NAME")["qty"],
            horizontal=True,
            height=max(320, len(ranked) * 26),
            sort=False,
        )
        display = _product_display(ranked)
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            column_config=_product_column_config(),
        )
        _csv_button(
            display,
            filename="bottom_sellers_by_qty.csv",
            key="bottom_qty_csv",
        )

    with col_amount:
        st.subheader(f"Bottom {n} by amount")
        ranked = _ranked_product_table(summary, "line_amount", n, ascending=True)
        st.bar_chart(
            ranked.set_index("PRODUCT_NAME")["line_amount"],
            horizontal=True,
            height=max(320, len(ranked) * 26),
            sort=False,
        )
        display = _product_display(ranked)
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            column_config=_product_column_config(),
        )
        _csv_button(
            display,
            filename="bottom_sellers_by_amount.csv",
            key="bottom_amount_csv",
        )


# ---------------------------------------------------------------------------
# 9. ABC Analysis
# ---------------------------------------------------------------------------

def _tab_abc_analysis(df: pd.DataFrame) -> None:
    st.caption(
        "Ranks products by sales amount and groups them into A, B and C "
        "classes using cumulative share (Pareto analysis)."
    )

    if df.empty:
        _no_data()
        return

    st.markdown("**Class thresholds**")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        a_raw = st.slider(
            "A share (%)", min_value=0, max_value=100, value=80, step=1, key="abc_a"
        )
    with col_b:
        b_raw = st.slider(
            "B share (%)", min_value=0, max_value=100, value=15, step=1, key="abc_b"
        )
    with col_c:
        c_raw = st.slider(
            "C share (%)", min_value=0, max_value=100, value=5, step=1, key="abc_c"
        )

    total_raw = a_raw + b_raw + c_raw
    if total_raw <= 0:
        st.warning("Set at least one class share above zero.")
        return

    # Normalise the three sliders so they always add up to 100%.
    a_pct = a_raw / total_raw * 100
    b_pct = b_raw / total_raw * 100
    c_pct = c_raw / total_raw * 100
    st.caption(
        f"Normalised thresholds: A {a_pct:.1f}% · B {b_pct:.1f}% · C {c_pct:.1f}%"
    )

    summary = _product_summary(df)
    summary = summary[summary["line_amount"] >= 0].copy()
    if summary.empty:
        _no_data("No products with sales in this period.")
        return

    summary = summary.sort_values("line_amount", ascending=False).reset_index(drop=True)
    total_amount = summary["line_amount"].sum()
    if total_amount <= 0:
        _no_data("No products with a positive sales amount in this period.")
        return
    summary["share_pct"] = summary["line_amount"] / total_amount * 100
    summary["cum_pct"] = summary["share_pct"].cumsum()

    # Use the cumulative share before each product so the item that crosses a
    # boundary is included in that class (A always covers at least its share).
    summary["cum_before"] = summary["cum_pct"] - summary["share_pct"]
    a_boundary = a_pct
    b_boundary = a_pct + b_pct
    summary["class"] = np.select(
        [
            summary["cum_before"] < a_boundary,
            summary["cum_before"] < b_boundary,
        ],
        ["A", "B"],
        default="C",
    )
    summary.insert(0, "rank", range(1, len(summary) + 1))

    # Pareto chart: amount bars plus a cumulative-percent line.
    chart_df = summary.head(50).copy()
    base = alt.Chart(chart_df).encode(
        x=alt.X(
            "PRODUCT_NAME:N",
            sort=None,
            title=None,
            axis=alt.Axis(labelAngle=-45, labelLimit=180),
        )
    )
    bars = base.mark_bar(color="#4C78A8").encode(
        y=alt.Y("line_amount:Q", title="Sales amount (৳)"),
        tooltip=[
            alt.Tooltip("PRODUCT_NAME:N", title="Product"),
            alt.Tooltip("line_amount:Q", title="Amount", format=",.2f"),
            alt.Tooltip("cum_pct:Q", title="Cumulative %", format=".2f"),
        ],
    )
    line = base.mark_line(color="#E45756", point=True).encode(
        y=alt.Y(
            "cum_pct:Q",
            title="Cumulative %",
            axis=alt.Axis(format=".0f", orient="right"),
        )
    )
    chart = (
        alt.layer(bars, line)
        .resolve_scale(y="independent")
        .properties(height=420)
    )

    st.subheader("Pareto chart")
    st.caption("Top 50 products by amount; the table below lists all products.")
    st.altair_chart(chart, width="stretch")

    # Products per class, including empty classes.
    class_summary = (
        summary.groupby("class", as_index=True)
        .agg(
            products=("PRODUCT_ID", "nunique"),
            amount=("line_amount", "sum"),
        )
        .reindex(["A", "B", "C"], fill_value=0)
        .reset_index()
    )
    class_summary["share_pct"] = class_summary["amount"] / total_amount * 100

    class_display = class_summary.rename(
        columns={
            "class": "Class",
            "products": "Products",
            "amount": "Amount",
            "share_pct": "Share %",
        }
    )
    st.subheader("Products per class")
    st.dataframe(
        class_display,
        hide_index=True,
        width="stretch",
        column_config={
            "Products": st.column_config.NumberColumn(format="%d"),
            "Amount": st.column_config.NumberColumn(format="%,.2f"),
            "Share %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    _csv_button(
        class_display,
        filename="abc_class_summary.csv",
        key="abc_class_csv",
    )

    detail = summary.rename(
        columns={
            "rank": "Rank",
            "PRODUCT_NAME": "Product",
            "qty": "Qty",
            "line_amount": "Amount",
            "share_pct": "Share %",
            "cum_pct": "Cumulative %",
            "class": "Class",
        }
    )[["Rank", "Product", "Qty", "Amount", "Share %", "Cumulative %", "Class"]]

    st.subheader("Product detail")
    st.dataframe(
        detail,
        hide_index=True,
        width="stretch",
        height=500,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d", width="small"),
            "Qty": st.column_config.NumberColumn(format="%,.2f"),
            "Amount": st.column_config.NumberColumn(format="%,.2f"),
            "Share %": st.column_config.NumberColumn(format="%.2f%%"),
            "Cumulative %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    _csv_button(detail, filename="abc_analysis.csv", key="abc_detail_csv")


# ---------------------------------------------------------------------------
# 10. Group-wise Best and Worst
# ---------------------------------------------------------------------------

def _tab_group_best_worst(df: pd.DataFrame) -> None:
    st.caption(
        "For each product group, shows the best and worst product by sales "
        "amount and the group total."
    )

    if df.empty:
        _no_data()
        return

    product_agg = (
        df.groupby(
            [
                "PRODUCT_GROUP_ID",
                "PRODUCT_GROUP_NAME",
                "PRODUCT_ID",
                "PRODUCT_NAME",
            ],
            as_index=False,
        )
        .agg(line_amount=("line_amount", "sum"))
    )

    if product_agg.empty:
        _no_data()
        return

    idx_best = product_agg.groupby("PRODUCT_GROUP_ID")["line_amount"].idxmax()
    idx_worst = product_agg.groupby("PRODUCT_GROUP_ID")["line_amount"].idxmin()

    best = product_agg.loc[
        idx_best,
        ["PRODUCT_GROUP_ID", "PRODUCT_GROUP_NAME", "PRODUCT_NAME", "line_amount"],
    ].copy()
    best.columns = ["GROUP_ID", "Group", "Best Product", "Best Amount"]

    worst = product_agg.loc[
        idx_worst,
        ["PRODUCT_GROUP_ID", "PRODUCT_NAME", "line_amount"],
    ].copy()
    worst.columns = ["GROUP_ID", "Worst Product", "Worst Amount"]

    group_totals = (
        product_agg.groupby("PRODUCT_GROUP_ID", as_index=False)["line_amount"]
        .sum()
        .rename(
            columns={
                "PRODUCT_GROUP_ID": "GROUP_ID",
                "line_amount": "Group Total",
            }
        )
    )

    merged = (
        best.merge(worst, on="GROUP_ID")
        .merge(group_totals, on="GROUP_ID")
        .sort_values("Group Total", ascending=False)
        .reset_index(drop=True)
    )
    merged.insert(0, "rank", range(1, len(merged) + 1))

    display = merged.rename(columns={"rank": "Rank"})[
        [
            "Rank",
            "Group",
            "Best Product",
            "Best Amount",
            "Worst Product",
            "Worst Amount",
            "Group Total",
        ]
    ]

    st.subheader("Best and worst product amount by group")
    st.bar_chart(
        merged.set_index("Group")[["Best Amount", "Worst Amount"]],
        height=max(360, len(merged) * 30),
        stack=False,
        sort=False,
    )

    st.subheader("Group detail")
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=500,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d", width="small"),
            "Best Amount": st.column_config.NumberColumn(format="%,.2f"),
            "Worst Amount": st.column_config.NumberColumn(format="%,.2f"),
            "Group Total": st.column_config.NumberColumn(format="%,.2f"),
        },
    )
    _csv_button(display, filename="group_best_worst.csv", key="group_csv")


# ---------------------------------------------------------------------------
# 11. Brand Performance
# ---------------------------------------------------------------------------

def _tab_brand_performance(df: pd.DataFrame) -> None:
    st.caption(
        "Shows sales amount, quantity, number of products and share of "
        "total sales for each brand."
    )

    if df.empty:
        _no_data()
        return

    brand_agg = (
        df.groupby(["BRAND_ID", "BRAND_NAME"], as_index=False)
        .agg(
            qty=("qty", "sum"),
            line_amount=("line_amount", "sum"),
            products=("PRODUCT_ID", "nunique"),
        )
    )

    if brand_agg.empty:
        _no_data()
        return

    total_amount = brand_agg["line_amount"].sum()
    if total_amount:
        brand_agg["share_pct"] = brand_agg["line_amount"] / total_amount * 100
    else:
        brand_agg["share_pct"] = 0.0
    brand_agg = brand_agg.sort_values(
        "line_amount", ascending=False
    ).reset_index(drop=True)
    brand_agg.insert(0, "rank", range(1, len(brand_agg) + 1))

    display = brand_agg.rename(
        columns={
            "rank": "Rank",
            "BRAND_NAME": "Brand",
            "qty": "Qty",
            "line_amount": "Amount",
            "products": "Products",
            "share_pct": "Share %",
        }
    )[["Rank", "Brand", "Qty", "Amount", "Products", "Share %"]]

    st.subheader("Sales amount by brand")
    st.bar_chart(
        brand_agg.set_index("BRAND_NAME")["line_amount"],
        horizontal=True,
        height=max(360, len(brand_agg) * 24),
        sort=False,
    )

    st.subheader("Brand detail")
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=500,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d", width="small"),
            "Qty": st.column_config.NumberColumn(format="%,.2f"),
            "Amount": st.column_config.NumberColumn(format="%,.2f"),
            "Products": st.column_config.NumberColumn(format="%d"),
            "Share %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    _csv_button(display, filename="brand_performance.csv", key="brand_csv")


# ---------------------------------------------------------------------------
# 12. Growing vs Declining
# ---------------------------------------------------------------------------

def _change_display(frame: pd.DataFrame) -> pd.DataFrame:
    view = frame.copy()
    view.insert(0, "rank", range(1, len(view) + 1))
    return view.rename(
        columns={
            "rank": "Rank",
            "PRODUCT_NAME": "Product",
            "current_amount": "Current Amount",
            "previous_amount": "Previous Amount",
            "change": "Change",
            "change_pct": "Change %",
            "label": "Status",
        }
    )[
        [
            "Rank",
            "Product",
            "Current Amount",
            "Previous Amount",
            "Change",
            "Change %",
            "Status",
        ]
    ]


def _change_column_config() -> dict[str, object]:
    return {
        "Rank": st.column_config.NumberColumn(format="%d", width="small"),
        "Current Amount": st.column_config.NumberColumn(format="%,.2f"),
        "Previous Amount": st.column_config.NumberColumn(format="%,.2f"),
        "Change": st.column_config.NumberColumn(format="%,.2f"),
        "Change %": st.column_config.NumberColumn(format="%.2f%%"),
    }


def _tab_growing_declining(
    df: pd.DataFrame,
    date_from: date,
    date_to: date,
    store_id: str | None,
    group_id: str | None,
    brand_id: str | None,
) -> None:
    st.caption(
        "Compares each product's sales amount with the immediately preceding "
        "period of equal length. 'New' means there were no sales previously."
    )

    if df.empty:
        _no_data()
        return

    period_days = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=period_days - 1)

    st.info(
        f"**Current period:** {date_from:%d %b %Y} to {date_to:%d %b %Y} "
        f"({period_days} days)  \n"
        f"**Previous period:** {prev_from:%d %b %Y} to {prev_to:%d %b %Y}"
    )

    try:
        prev_df = get_sales_df(
            prev_from,
            prev_to,
            store=store_id,
            group=group_id,
            brand=brand_id,
        )
    except Exception:
        st.warning("Could not load the previous period for comparison.")
        return

    current = _product_summary(df).rename(
        columns={
            "PRODUCT_NAME": "CURRENT_NAME",
            "qty": "current_qty",
            "line_amount": "current_amount",
        }
    )
    previous = _product_summary(prev_df).rename(
        columns={
            "PRODUCT_NAME": "PREVIOUS_NAME",
            "qty": "previous_qty",
            "line_amount": "previous_amount",
        }
    )

    merged = current.merge(previous, on="PRODUCT_ID", how="outer")
    merged["PRODUCT_NAME"] = (
        merged["CURRENT_NAME"].fillna(merged["PREVIOUS_NAME"]).fillna("Unknown")
    )
    for column in (
        "current_qty",
        "current_amount",
        "previous_qty",
        "previous_amount",
    ):
        merged[column] = pd.to_numeric(
            merged[column], errors="coerce"
        ).fillna(0.0)

    merged["change"] = merged["current_amount"] - merged["previous_amount"]
    # Replace zero denominators with NaN so the division cannot fail.
    safe_previous = merged["previous_amount"].where(
        merged["previous_amount"] != 0
    )
    merged["change_pct"] = merged["change"] / safe_previous * 100

    # Exactly the three requested labels.  A zero change is grouped with
    # Declining so the label set stays Growing / Declining / New.
    merged["label"] = np.select(
        [
            (merged["previous_amount"] == 0) & (merged["current_amount"] > 0),
            merged["change"] > 0,
        ],
        ["New", "Growing"],
        default="Declining",
    )

    growing = (
        merged[merged["label"] == "Growing"]
        .nlargest(10, "change")
        .reset_index(drop=True)
    )
    declining = (
        merged[(merged["label"] == "Declining") & (merged["change"] < 0)]
        .nsmallest(10, "change")
        .reset_index(drop=True)
    )

    def render_list(
        subset: pd.DataFrame,
        title: str,
        filename: str,
        key: str,
    ) -> None:
        st.subheader(title)
        if subset.empty:
            st.info(
                f"No {title.replace('Top 10 ', '').lower()} products in this "
                "comparison."
            )
            return

        st.bar_chart(
            subset.set_index("PRODUCT_NAME")["change"],
            horizontal=True,
            height=max(300, len(subset) * 30),
            sort=False,
        )
        display = _change_display(subset)
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            column_config=_change_column_config(),
        )
        _csv_button(display, filename=filename, key=key)

    col_growing, col_declining = st.columns(2)
    with col_growing:
        render_list(
            growing,
            "Top 10 growing",
            "growing_products.csv",
            "growing_csv",
        )
    with col_declining:
        render_list(
            declining,
            "Top 10 declining",
            "declining_products.csv",
            "declining_csv",
        )

    with st.expander("Show all products"):
        full = merged.sort_values("change", ascending=False).reset_index(drop=True)
        display = _change_display(full)
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            height=500,
            column_config=_change_column_config(),
        )
        _csv_button(
            display,
            filename="growing_declining_all.csv",
            key="all_changes_csv",
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Sales Report")
    st.caption(
        "Six product-level views of sales for the selected period. "
        "Every row in sales_details is treated as a valid sale."
    )

    date_from, date_to, store_id, group_id, brand_id = render_report_filters(
        key_prefix="sales_report"
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

    if not df.empty:
        col_amount, col_qty, col_products = st.columns(3)
        col_amount.metric("Sales amount", fmt_taka(df["line_amount"].sum()))
        col_qty.metric("Quantity sold", f"{df['qty'].sum():,.2f}")
        col_products.metric("Products sold", f"{df['PRODUCT_ID'].nunique():,}")

    st.caption(
        f"{len(df):,} rows · {date_from:%d %b %Y} to {date_to:%d %b %Y}"
    )

    tabs = st.tabs(
        [
            "Top Sellers",
            "Bottom Sellers",
            "ABC Analysis",
            "Group-wise Best & Worst",
            "Brand Performance",
            "Growing vs Declining",
        ]
    )

    with tabs[0]:
        _tab_top_sellers(df)
    with tabs[1]:
        _tab_bottom_sellers(df)
    with tabs[2]:
        _tab_abc_analysis(df)
    with tabs[3]:
        _tab_group_best_worst(df)
    with tabs[4]:
        _tab_brand_performance(df)
    with tabs[5]:
        _tab_growing_declining(
            df,
            date_from,
            date_to,
            store_id,
            group_id,
            brand_id,
        )


main()
