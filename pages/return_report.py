"""Return Report (Report 18)."""

from __future__ import annotations

from pathlib import Path
import sys

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db import get_engine
from src.report_helpers import fmt_taka, get_sales_df, render_report_filters


def _csv_button(df: pd.DataFrame, key: str) -> None:
    st.download_button(
        "Download CSV", df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{key}.csv", mime="text/csv", key=key,
    )


def _returns(date_from, date_to, store=None, group=None, brand=None) -> pd.DataFrame:
    filters = ["r.RETURN_DATE BETWEEN :date_from AND :date_to"]
    params = {"date_from": date_from, "date_to": date_to}
    if store:
        filters.append("r.STORE_ID = :store_id")
        params["store_id"] = store
    if group:
        filters.append("r.PRODUCT_GROUP_ID = :group_id")
        params["group_id"] = group
    if brand:
        filters.append("r.BRAND_ID = :brand_id")
        params["brand_id"] = brand
    sql = text(
        f"""
        SELECT r.PRODUCT_ID, COALESCE(p.PRODUCT_NAME, 'Unknown') AS PRODUCT_NAME,
               COALESCE(SUM(r.QTY), 0) AS returned_qty,
               COALESCE(SUM(r.TOTAL_PRICE), 0) AS return_amount
        FROM sales_return_details AS r
        LEFT JOIN product AS p ON p.PRODUCT_ID = r.PRODUCT_ID
        WHERE {' AND '.join(filters)}
        GROUP BY r.PRODUCT_ID, p.PRODUCT_NAME
        """
    )
    df = pd.read_sql_query(sql, get_engine(), params=params)
    for column in ("returned_qty", "return_amount"):
        if column not in df:
            df[column] = 0.0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return df


def main() -> None:
    st.title("Return Report")
    st.caption("See which products are returned most often and remove persistent return problems from buying plans.")
    date_from, date_to, store, group, brand = render_report_filters(key_prefix="return_report")
    return_threshold = st.sidebar.slider("Do-not-buy return rate (%)", 0.0, 100.0, 10.0, 0.5, key="return_rate")
    minimum_sold = st.sidebar.slider("Minimum sold quantity", 1, 100, 5, key="return_min_sold")
    try:
        sales = get_sales_df(date_from, date_to, store=store, group=group, brand=brand)
        returns = _returns(date_from, date_to, store, group, brand)
    except Exception as exc:
        st.error(f"Could not load return data: {exc}")
        st.stop()
    gross = sales["line_amount"].sum() if not sales.empty else 0.0
    returned_total = returns["return_amount"].sum() if not returns.empty else 0.0
    cards = st.columns(3)
    cards[0].metric("Gross sales", fmt_taka(gross))
    cards[1].metric("Returns", fmt_taka(returned_total))
    cards[2].metric("Net sales", fmt_taka(gross - returned_total))
    if sales.empty and returns.empty:
        st.info("No sales or returns match the selected period.")
        return
    sold = sales.groupby(["PRODUCT_ID", "PRODUCT_NAME"], as_index=False).agg(
        sold_qty=("qty", "sum"), sales_amount=("line_amount", "sum")
    ) if not sales.empty else pd.DataFrame(columns=["PRODUCT_ID", "PRODUCT_NAME", "sold_qty", "sales_amount"])
    table = sold.merge(returns, on=["PRODUCT_ID", "PRODUCT_NAME"], how="outer").fillna(0)
    table["return_rate_pct"] = table["returned_qty"].div(table["sold_qty"].where(table["sold_qty"] > 0)) * 100
    table["return_rate_pct"] = table["return_rate_pct"].fillna(0.0)
    table = table.sort_values("returned_qty", ascending=False)
    st.subheader("Top returned products")
    chart = table.head(15)
    if not chart.empty:
        st.altair_chart(
            alt.Chart(chart).mark_bar().encode(
                x=alt.X("returned_qty:Q", title="Returned quantity"),
                y=alt.Y("PRODUCT_NAME:N", sort="-x", title="Product"),
                tooltip=["PRODUCT_NAME", "returned_qty", "return_rate_pct"],
            ),
            use_container_width=True,
        )
    display = table.rename(columns={"PRODUCT_NAME": "Product", "sold_qty": "Qty sold", "returned_qty": "Qty returned", "return_rate_pct": "Return rate %", "return_amount": "Return amount"})[
        ["Product", "Qty sold", "Qty returned", "Return rate %", "Return amount"]
    ]
    st.dataframe(display, hide_index=True, width="stretch")
    _csv_button(display, "return_report")
    st.subheader("Do not buy list")
    avoid = table[(table["return_rate_pct"] > return_threshold) & (table["sold_qty"] >= minimum_sold)]
    if avoid.empty:
        st.info("No products exceed the return-rate rule.")
    else:
        avoid_display = avoid.rename(columns={"PRODUCT_NAME": "Product", "sold_qty": "Qty sold", "returned_qty": "Qty returned", "return_rate_pct": "Return rate %"})[
            ["Product", "Qty sold", "Qty returned", "Return rate %"]
        ]
        st.dataframe(avoid_display, hide_index=True, width="stretch")
        _csv_button(avoid_display, "return_do_not_buy")


main()
