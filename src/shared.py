from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.db import get_engine
from src.queries import SALES_DETAILS_QUERY, build_all_products_report_query


@st.cache_data(ttl=600, show_spinner="Loading sales data...")
def load_sales_details() -> pd.DataFrame:
    engine = get_engine()
    df = pd.read_sql_query(text(SALES_DETAILS_QUERY), engine)
    df["SALES_DATE"] = pd.to_datetime(df["SALES_DATE"])
    return df


@st.cache_data(ttl=600, show_spinner="Building product report...")
def load_all_products_report(
    start_date: date,
    end_date: date,
    product_group_ids: tuple[str, ...] = (),
    brand_ids: tuple[str, ...] = (),
) -> pd.DataFrame:
    engine = get_engine()
    statement, params = build_all_products_report_query(
        start_date,
        end_date,
        product_group_ids,
        brand_ids,
    )
    return pd.read_sql_query(statement, engine, params=params)


def render_sidebar_filters(
    df: pd.DataFrame,
) -> tuple[date, date, tuple[str, ...], tuple[str, ...]]:
    min_date = df["SALES_DATE"].min().date()
    max_date = df["SALES_DATE"].max().date()

    st.sidebar.header("Filters")
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="filter_date_range",
    )

    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        st.sidebar.warning("Select both a start and end date.")
        st.stop()

    start_date, end_date = date_range
    if start_date > end_date:
        st.sidebar.error("Start date must be on or before end date.")
        st.stop()

    group_labels = (
        df.dropna(subset=["PRODUCT_GROUP_ID"])
        .drop_duplicates("PRODUCT_GROUP_ID")
        .set_index("PRODUCT_GROUP_ID")["PRODUCT_GROUP_NAME"]
        .fillna("")
        .to_dict()
    )
    group_options = sorted(
        group_labels, key=lambda group_id: group_labels[group_id].strip().lower()
    )
    selected_groups = st.sidebar.multiselect(
        "Product group",
        group_options,
        format_func=lambda group_id: group_labels.get(group_id, group_id).strip(),
        key="filter_product_groups",
    )

    brand_labels = (
        df.dropna(subset=["BRAND_ID"])
        .drop_duplicates("BRAND_ID")
        .set_index("BRAND_ID")["BRAND_NAME"]
        .fillna("")
        .to_dict()
    )
    brand_options = sorted(
        brand_labels, key=lambda brand_id: brand_labels[brand_id].strip().lower()
    )
    selected_brands = st.sidebar.multiselect(
        "Brand",
        brand_options,
        format_func=lambda brand_id: brand_labels.get(brand_id, brand_id).strip(),
        key="filter_brands",
    )

    return (
        start_date,
        end_date,
        tuple(selected_groups),
        tuple(selected_brands),
    )


def apply_sales_filters(
    df: pd.DataFrame,
    start_date: date,
    end_date: date,
    product_group_ids: tuple[str, ...] = (),
    brand_ids: tuple[str, ...] = (),
) -> pd.DataFrame:
    mask = (df["SALES_DATE"].dt.date >= start_date) & (
        df["SALES_DATE"].dt.date <= end_date
    )

    if product_group_ids:
        mask &= df["PRODUCT_GROUP_ID"].isin(product_group_ids)

    if brand_ids:
        mask &= df["BRAND_ID"].isin(brand_ids)

    return df.loc[mask]


def render_caption(df: pd.DataFrame, prefix: str | None = None) -> None:
    min_date = df["SALES_DATE"].min().date()
    max_date = df["SALES_DATE"].max().date()
    prefix = prefix or (
        "Source: print_db | Gross sales | Returns and APPROVAL/STATUS filters "
        "NOT yet applied |"
    )
    st.caption(
        f"{prefix} Data range: {min_date:%d %b %Y} - {max_date:%d %b %Y}"
    )
