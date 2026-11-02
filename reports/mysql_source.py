"""MySQL adapter for the shared standard report dataframe."""

from __future__ import annotations

from datetime import date
import re

import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.db import get_engine
from src.report_helpers import get_return_summary, get_sales_df, get_stock_df


@st.cache_data(ttl=300, show_spinner="Loading database report data...")
def load_sales_df(start_date: date, end_date: date) -> pd.DataFrame:
    raw = get_sales_df(start_date, end_date)
    if raw.empty:
        return pd.DataFrame()
    result = pd.DataFrame(
        {
            "product_name": raw["PRODUCT_NAME"],
            "quantity": raw["qty"],
            "sales_amount": raw["line_amount"],
            "date": pd.to_datetime(raw["SALES_DATE"], errors="coerce"),
            "product_group": raw["PRODUCT_GROUP_NAME"],
            "brand": raw["BRAND_NAME"],
            "cost": raw["AVG_COST"],
        }
    )
    result["profit"] = result["sales_amount"] - result["cost"] * result["quantity"]
    stock = get_stock_df()
    if not stock.empty:
        stock = stock[["PRODUCT_ID", "stock_qty"]].rename(columns={"stock_qty": "stock_quantity"})
        result = result.join(stock.set_index("PRODUCT_ID")["stock_quantity"], on=raw["PRODUCT_ID"])
    returns = get_return_summary(start_date, end_date)
    if not returns.empty:
        return_map = returns.set_index("PRODUCT_ID")["returned_qty"]
        result["returns"] = raw["PRODUCT_ID"].map(return_map).fillna(0.0)
    return result.dropna(subset=["date"]).reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner="Loading customer sales data...")
def load_customer_sales_df(start_date: date, end_date: date) -> pd.DataFrame:
    result = load_sales_df(start_date, end_date)
    if result.empty:
        return result
    customer_rows = pd.read_sql_query(
        text(
            """
            SELECT DISTINCT d.SALES_ID, d.CS_ID, c.CS_NAME
            FROM sales_details AS d
            LEFT JOIN cs AS c ON c.CS_ID = d.CS_ID
            WHERE d.SALES_DATE BETWEEN :start_date AND :end_date
            """
        ),
        get_engine(),
        params={"start_date": start_date, "end_date": end_date},
    )
    customer_rows["customer"] = customer_rows["CS_NAME"].fillna("Unknown").astype(str).str.strip()
    customer_rows = customer_rows[["SALES_ID", "customer"]].drop_duplicates("SALES_ID")
    result = result.copy().drop(columns=["key_0"], errors="ignore")
    result["invoice"] = result.index.to_series().map(
        get_sales_df(start_date, end_date)["SALES_ID"]
    )
    result = result.merge(
        customer_rows,
        left_on="invoice",
        right_on="SALES_ID",
        how="left",
    ).drop(columns=["SALES_ID"])
    result["customer"] = result["customer"].fillna("Unknown")
    return result


@st.cache_data(ttl=300, show_spinner="Loading customer balances...")
def load_customer_due_df(start_date: date, end_date: date) -> pd.DataFrame:
    return pd.read_sql_query(
        text(
            """
            SELECT DISTINCT
                c.CS_NAME AS customer,
                GREATEST(COALESCE(c.BALANCE, 0), 0) AS due,
                collections.last_collection_date,
                sales_dates.last_sale_date,
                COALESCE(period_sales.total_sales, 0) AS total_sales
            FROM cs AS c
            LEFT JOIN (
                SELECT CS_ID, MAX(COLLECTION_DATE) AS last_collection_date
                FROM collection
                WHERE AMOUNT IS NOT NULL
                GROUP BY CS_ID
            ) AS collections ON collections.CS_ID = c.CS_ID
            LEFT JOIN (
                SELECT CS_ID, MAX(SALES_DATE) AS last_sale_date
                FROM sales_details
                GROUP BY CS_ID
            ) AS sales_dates ON sales_dates.CS_ID = c.CS_ID
            LEFT JOIN (
                SELECT
                    CS_ID,
                    SUM(QTY * UNIT_PRICE - COALESCE(DISCOUNT, 0)) AS total_sales
                FROM sales_details
                WHERE SALES_DATE BETWEEN :start_date AND :end_date
                GROUP BY CS_ID
            ) AS period_sales ON period_sales.CS_ID = c.CS_ID
            """
        ),
        get_engine(),
        params={"start_date": start_date, "end_date": end_date},
    )


@st.cache_data(ttl=300, show_spinner="Loading customer profiles...")
def load_customer_profile_df() -> pd.DataFrame:
    return pd.read_sql_query(
        text(
            """
            SELECT DISTINCT
                c.CS_NAME AS customer,
                c.CS_ID AS customer_id,
                c.CUSTOMER_TYPE AS customer_type,
                g.GROUP_NAME AS customer_group,
                c.ADDRESS AS address,
                c.MOBILE AS mobile,
                c.PHONE AS phone,
                c.EMAIL AS email,
                c.CONTACT_PERSON AS contact_person,
                c.CREDIT_LIMIT AS credit_limit,
                c.BIN AS bin,
                c.BALANCE AS balance
            FROM cs AS c
            LEFT JOIN cs_group AS g ON g.CS_GROUP_ID = c.CS_GROUP_ID
            """
        ),
        get_engine(),
    )


@st.cache_data(ttl=300, show_spinner="Loading warranty customer data...")
def load_warranty_df() -> pd.DataFrame:
    raw = pd.read_sql_query(
        text(
            """
            SELECT DISTINCT
                c.CS_NAME AS customer,
                p.PRODUCT_NAME AS product_name,
                d.SALES_DATE AS sale_date,
                CASE
                    WHEN d.WARRANTY IS NOT NULL AND TRIM(d.WARRANTY) <> ''
                        THEN d.WARRANTY
                    ELSE p.WARRANTY
                END AS warranty_text
            FROM sales_details AS d
            LEFT JOIN cs AS c ON c.CS_ID = d.CS_ID
            LEFT JOIN product AS p ON p.PRODUCT_ID = d.PRODUCT_ID
            WHERE d.SALES_DATE >= DATE_SUB(CURRENT_DATE, INTERVAL 40 MONTH)
              AND d.SALES_DATE <= CURRENT_DATE
              AND (
                  (d.WARRANTY IS NOT NULL AND TRIM(d.WARRANTY) <> '')
                  OR (p.WARRANTY IS NOT NULL AND TRIM(p.WARRANTY) <> '')
              )
            """
        ),
        get_engine(),
    )
    if raw.empty:
        return pd.DataFrame()

    def warranty_months(value: object) -> int | None:
        text_value = str(value).strip().lower()
        match = re.fullmatch(r"(\d+)\s*month(?:s)?", text_value)
        if match:
            return int(match.group(1))
        match = re.fullmatch(r"(\d+)\s*year(?:s)?", text_value)
        if match:
            return int(match.group(1)) * 12
        if re.fullmatch(r"\d+", text_value):
            return int(text_value) * 12
        return None

    result = raw.drop_duplicates().copy()
    result["sale_date"] = pd.to_datetime(result["sale_date"], errors="coerce")
    result["warranty_months"] = result["warranty_text"].map(warranty_months)
    result = result.dropna(subset=["sale_date", "warranty_months"])
    if result.empty:
        return pd.DataFrame()
    result["warranty_end_date"] = result.apply(
        lambda row: row["sale_date"] + pd.DateOffset(months=int(row["warranty_months"])),
        axis=1,
    )
    result["days_left"] = (result["warranty_end_date"] - pd.Timestamp(date.today())).dt.days
    result["status"] = result["days_left"].map(
        lambda days: "Expired" if days < 0 else "Expiring soon" if days <= 30 else "Active"
    )
    return result[
        [
            "customer",
            "product_name",
            "sale_date",
            "warranty_end_date",
            "days_left",
            "status",
        ]
    ].reset_index(drop=True)
