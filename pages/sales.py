from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from streamlit_searchbox import st_searchbox

from src.shared import (
    load_all_products_report,
    load_sales_details,
    render_caption,
    render_sidebar_filters,
)

_ROWS_PER_PAGE = 25


def main() -> None:
    st.title("Sales Report")

    try:
        base_df = load_sales_details()
    except Exception:
        st.error(
            "Could not load sales data. Check that MySQL is running in XAMPP "
            "and that .env has the correct database settings."
        )
        st.stop()

    start_date, end_date, selected_groups, selected_brands = render_sidebar_filters(
        base_df
    )

    try:
        report = load_all_products_report(
            start_date,
            end_date,
            selected_groups,
            selected_brands,
        )
    except Exception:
        st.error("Could not build the sales report. Check the database connection.")
        st.stop()

    render_caption(
        base_df,
        "All figures are gross sales. Returns and APPROVAL/STATUS filters are "
        "NOT yet applied.",
    )

    if report.empty:
        st.warning("No sales data matches the selected filters.")
        st.stop()

    total_amount = report["TOTAL_AMOUNT"].sum()
    report = report.copy()
    report["SHARE_PCT"] = (
        report["TOTAL_AMOUNT"] / total_amount * 100 if total_amount else 0.0
    ).round(2)

    def search_products(searchterm: str) -> list[str]:
        query = searchterm.strip().casefold()
        if not query:
            return []
        return (
            report.loc[
                report["PRODUCT_NAME"].str.casefold().str.contains(
                    query, regex=False, na=False
                ),
                "PRODUCT_NAME",
            ]
            .drop_duplicates()
            .head(10)
            .tolist()
        )

    search_column, sort_column_ui = st.columns([2, 1])
    with search_column:
        selected_product = st_searchbox(
            search_products,
            placeholder="Search product name",
            label="Product",
            key="sales_product_search",
        )
    with sort_column_ui:
        sort_label = st.radio(
            "Sort by",
            ["Qty", "Amount"],
            horizontal=True,
            key="sales_sort_by",
        )

    sort_column = "TOTAL_QTY" if sort_label == "Qty" else "TOTAL_AMOUNT"

    if selected_product:
        report = report[
            report["PRODUCT_NAME"].eq(selected_product)
        ]

    if report.empty:
        st.warning("No products match your search.")
        st.stop()

    report = report.sort_values(
        sort_column,
        ascending=False,
        kind="mergesort",
    ).reset_index(drop=True)
    report.insert(0, "RANK", range(1, len(report) + 1))

    display = report.rename(
        columns={
            "RANK": "Rank",
            "PRODUCT_NAME": "Product Name",
            "PRODUCT_GROUP_NAME": "Product Group",
            "BRAND_NAME": "Brand",
            "TOTAL_QTY": "Total Qty",
            "TOTAL_AMOUNT": "Total Amount",
            "SHARE_PCT": "Share %",
        }
    )[
        [
            "Rank",
            "Product Name",
            "Product Group",
            "Brand",
            "Total Qty",
            "Total Amount",
            "Share %",
        ]
    ]

    total_rows = len(display)
    total_pages = (total_rows - 1) // _ROWS_PER_PAGE + 1
    if st.session_state.get("sales_page", 1) > total_pages:
        st.session_state.sales_page = 1

    pagination_column, summary_column = st.columns([1, 3])
    with pagination_column:
        current_page = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=st.session_state.get("sales_page", 1),
            step=1,
            key="sales_page",
        )
    row_start = (current_page - 1) * _ROWS_PER_PAGE
    row_end = min(row_start + _ROWS_PER_PAGE, total_rows)
    with summary_column:
        st.caption(
            f"Showing {row_start + 1}-{row_end} of {total_rows} products "
            f"(page {current_page} of {total_pages})"
        )

    st.dataframe(
        display.iloc[row_start:row_end],
        hide_index=True,
        width="stretch",
        height=600,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d", width="small"),
            "Total Qty": st.column_config.NumberColumn(format="%,.2f"),
            "Total Amount": st.column_config.NumberColumn(format="%,.2f"),
            "Share %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )

    st.download_button(
        "Download CSV",
        data=display.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"sales_report_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv",
        mime="text/csv",
    )

    st.subheader(f"Top 20 Products by {sort_label}")
    chart_data = report.head(20).set_index("PRODUCT_NAME")[sort_column]
    st.bar_chart(
        chart_data,
        horizontal=True,
        height=600,
        sort=False,
    )


main()
