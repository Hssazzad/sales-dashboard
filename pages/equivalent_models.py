"""Equivalent product lookup for the live sales source."""

from __future__ import annotations

from datetime import date, timedelta
import traceback

import pandas as pd
import streamlit as st

from reports.engine import build_equivalent_product_table, find_equivalent_products
from reports.mysql_source import load_sales_df


def _number(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])


def _stock_badge(stock: float) -> str:
    if stock > 5:
        return "🟢 In stock"
    if stock > 0:
        return "🟡 Low stock"
    return "🔴 Out of stock"


def main() -> None:
    st.title("Equivalent Models")
    st.caption("Find which product can replace another.")
    today = date.today()
    filters = st.columns(3)
    with filters[0]:
        date_range = st.date_input(
            "Date range",
            value=(today - timedelta(days=364), today),
            key="equivalent_models_dates",
        )
    with filters[2]:
        stock_filter = st.radio(
            "Stock",
            ["All", "In stock only", "Out of stock only"],
            key="equivalent_models_stock",
        )
    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        st.info("No data")
        return

    start_date, end_date = date_range
    try:
        df = load_sales_df(start_date, end_date)
        print("Equivalent Models columns after load:", df.columns.tolist())
        df = df.loc[:, ~df.columns.duplicated()].copy()
        if "product_name" not in df or df.empty:
            st.info("No data")
            return
        print("Equivalent Models columns before product table:", df.columns.tolist())
        products_table = build_equivalent_product_table(df)
        if products_table.empty:
            st.info("No data")
            return
        print("Equivalent Models columns before matching:", products_table.columns.tolist())
        equivalents = find_equivalent_products(products_table)
        if equivalents.empty:
            st.info("No equivalent found")
            return

        group_filter = "All"
        if "product_group" in products_table:
            groups = sorted(
                value for value in products_table["product_group"].dropna().astype(str).str.strip().unique() if value
            )
        else:
            groups = []
        with filters[1]:
            group_filter = st.selectbox(
                "Product group",
                ["All", *groups],
                key="equivalent_models_group",
            )
        if group_filter != "All":
            products_table = products_table[products_table["product_group"] == group_filter]
            products_table = products_table.loc[:, ~products_table.columns.duplicated()].copy()
        if group_filter != "All":
            equivalents = equivalents[equivalents["product_group"] == group_filter]
            equivalents = equivalents.loc[:, ~equivalents.columns.duplicated()].copy()
        if stock_filter == "In stock only":
            products_table = products_table[products_table["stock_quantity"] > 0]
        elif stock_filter == "Out of stock only":
            products_table = products_table[products_table["stock_quantity"] <= 0]
        products_table = products_table.loc[:, ~products_table.columns.duplicated()].copy()
        products = sorted(
            set(products_table["product_name"]) & set(equivalents["product_name"])
        )
        equivalents = equivalents[equivalents["product_name"].isin(products)]
        equivalents = equivalents.loc[:, ~equivalents.columns.duplicated()].copy()
        if stock_filter == "In stock only":
            equivalents = equivalents[equivalents["stock_quantity"] > 0]
        elif stock_filter == "Out of stock only":
            equivalents = equivalents[equivalents["stock_quantity"] <= 0]
        equivalents = equivalents.loc[:, ~equivalents.columns.duplicated()].copy()
        if equivalents.empty:
            st.info("No data")
            return

        selected = st.selectbox("Search product...", products, key="equivalent_models_product")
        selected_rows = products_table[products_table["product_name"] == selected]
        selected_rows = selected_rows.loc[:, ~selected_rows.columns.duplicated()].copy()
        selected_row = selected_rows.iloc[0]
        table = equivalents[equivalents["product_name"] == selected].copy()
        table = pd.DataFrame(
            {
                "product_name": table["equivalent_product"],
                "product_group": table["equivalent_product_group"],
                "stock_quantity": table["equivalent_stock_quantity"],
                "sold": table["equivalent_sold"],
                "shared_codes": table["shared_codes"],
            }
        )
        table = table.loc[:, ~table.columns.duplicated()].copy()
        print("Equivalent Models table columns before sort:", table.columns.tolist())
        replacements = table.sort_values(
            ["stock_quantity", "sold"], ascending=[False, False]
        ).drop_duplicates("product_name")
        replacements = replacements.loc[:, ~replacements.columns.duplicated()].copy()
        with st.container(border=True):
            st.subheader(selected)
            selected_group = selected_row.get("product_group", "")
            st.caption(selected_group or "Product group not specified")
            metrics = st.columns(3)
            selected_stock = _number(selected_row.get("stock_quantity", 0))
            selected_sold = _number(selected_row.get("sold", 0))
            metrics[0].metric("Stock", f"{selected_stock:g}")
            metrics[1].metric("Sold", f"{selected_sold:g}")
            metrics[2].metric("Equivalents found", len(replacements))
            st.markdown(_stock_badge(selected_stock))
        if selected_stock <= 5:
            best = replacements.iloc[0] if not replacements.empty else None
            if best is not None:
                best_stock = _number(best.get("stock_quantity", 0))
                message = f"Out of stock. Use this instead: {best.get('product_name', '')} ({best_stock:g} in stock)"
                if selected_stock <= 0:
                    st.error(message)
                else:
                    st.warning(message)
                st.code(str(best.get("product_name", "")))
        if replacements.empty:
            st.info("No equivalent found")
            return

        best_index = replacements.index[0]
        show_all = st.checkbox("Show all", key="equivalent_models_show_all")
        visible = replacements if show_all else replacements.head(9)
        visible = visible.loc[:, ~visible.columns.duplicated()].copy()
        for row_start in range(0, len(visible), 3):
            cards = st.columns(3)
            for card, (_, replacement) in zip(cards, visible.iloc[row_start : row_start + 3].iterrows()):
                with card:
                    with st.container(border=True):
                        replacement_stock = _number(replacement.get("stock_quantity", 0))
                        replacement_sold = _number(replacement.get("sold", 0))
                        st.markdown(f"**{replacement.get('product_name', '')}**")
                        st.caption(replacement.get("product_group", "") or "Product group not specified")
                        st.markdown(_stock_badge(replacement_stock))
                        st.write(f"Sold: {replacement_sold:g}")
                        st.caption(f"Shared model codes: {replacement.get('shared_codes', '')}")
                        if replacement.name == best_index:
                            st.caption("⭐ Best replacement")

        with st.expander("View as table"):
            table = visible.reset_index(drop=True)
            st.dataframe(table, hide_index=True, width="stretch")
            st.download_button(
                "Download CSV",
                table.to_csv(index=False).encode("utf-8-sig"),
                file_name="equivalent_models.csv",
                mime="text/csv",
                key="equivalent_models_download",
            )
        st.caption("Equivalents are found automatically from shared model codes in product names.")
    except Exception as exc:
        st.warning("This page could not be built")
        with st.expander("Error details"):
            st.write(str(exc))
            st.code(traceback.format_exc())


main()
