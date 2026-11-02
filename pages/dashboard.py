from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.shared import (
    apply_sales_filters,
    load_sales_details,
    render_caption,
    render_sidebar_filters,
)


def _render_dashboard_style() -> None:
    st.markdown(
        """
        <style>
        .dashboard-hero {
          background: linear-gradient(135deg, #1d4ed8, #2563eb);
          border-radius: .85rem;
          color: #fff;
          margin-bottom: 1rem;
          padding: 1.75rem 2rem;
        }
        .dashboard-hero h1 { font-size: 2rem; margin: 0; }
        .dashboard-hero p { margin: .4rem 0 0; opacity: .82; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
          border-color: rgba(148, 163, 184, .32);
          border-radius: .75rem;
          box-shadow: 0 5px 18px rgba(15, 23, 42, .06);
        }
        div[data-testid="stMetricLabel"] { color: #64748b; }
        div[data-testid="stMetricValue"] { color: #0f172a; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    _render_dashboard_style()
    st.markdown(
        """
        <div class="dashboard-hero">
          <h1>Sales Dashboard</h1>
          <p>Track sales performance and product trends.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        df = load_sales_details()
    except Exception:
        st.error(
            "Could not load sales data. Check that MySQL is running in XAMPP "
            "and that .env has the correct database settings."
        )
        st.stop()

    start_date, end_date, selected_groups, selected_brands = render_sidebar_filters(
        df
    )
    filtered = apply_sales_filters(
        df,
        start_date,
        end_date,
        selected_groups,
        selected_brands,
    )

    render_caption(df)

    if filtered.empty:
        st.warning("No sales data matches the selected filters.")
        st.stop()

    month_count = filtered["SALES_DATE"].dt.strftime("%Y-%m").nunique()
    total_qty = filtered["QTY"].sum()
    total_sales = filtered["AMOUNT"].sum()

    kpi_one, kpi_two, kpi_three = st.columns(3)
    for column, label, value in (
        (kpi_one, "Months", f"{month_count:,}"),
        (kpi_two, "Total Qty", f"{total_qty:,.2f}"),
        (kpi_three, "Total Sales Amount", f"{total_sales:,.2f}"),
    ):
        with column:
            with st.container(border=True):
                st.metric(label, value)

    monthly_sales = (
        filtered.assign(
            MONTH=filtered["SALES_DATE"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby("MONTH", as_index=False)["AMOUNT"]
        .sum()
        .sort_values("MONTH")
    )
    with st.container(border=True):
        st.subheader("Monthly Sales Amount")
        st.line_chart(monthly_sales, x="MONTH", y="AMOUNT", height=350)

    top_products = (
        filtered.groupby("PRODUCT_NAME", as_index=False)
        .agg(QTY=("QTY", "sum"), AMOUNT=("AMOUNT", "sum"))
        .nlargest(10, "QTY")
        .reset_index(drop=True)
    )
    top_products.insert(0, "RANK", range(1, len(top_products) + 1))

    table_column, chart_column = st.columns([1.1, 1])
    with table_column:
        with st.container(border=True):
            st.subheader("Top 10 Products by Quantity")
            st.dataframe(
                top_products.rename(
                    columns={
                        "RANK": "#",
                        "PRODUCT_NAME": "Product",
                        "QTY": "Qty",
                        "AMOUNT": "Sales Amount",
                    }
                ),
                hide_index=True,
                width="stretch",
                column_config={
                    "Qty": st.column_config.NumberColumn(format="%.2f"),
                    "Sales Amount": st.column_config.NumberColumn(format="%.2f"),
                },
            )
    with chart_column:
        with st.container(border=True):
            st.subheader("Product Quantity")
            st.bar_chart(
                top_products.set_index("PRODUCT_NAME")["QTY"],
                horizontal=True,
                height=400,
                sort=False,
            )


main()
