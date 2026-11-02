"""Customer reports over the live MySQL sales source."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from reports.engine import render_reports
from reports.mysql_source import (
    load_customer_due_df,
    load_customer_profile_df,
    load_customer_sales_df,
    load_warranty_df,
)


def main() -> None:
    st.title("Customers")
    today = date.today()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(today - timedelta(days=364), today),
        key="customer_reports_dates",
    )
    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        st.sidebar.warning("Select both a start and an end date.")
        return
    start_date, end_date = date_range
    try:
        frame = load_customer_sales_df(start_date, end_date)
        due = load_customer_due_df(start_date, end_date)
        profile = load_customer_profile_df()
        warranty = load_warranty_df()
    except Exception as exc:
        st.error("Could not load customer data from MySQL.")
        with st.expander("Database error details"):
            st.write(str(exc))
        return
    st.metric("Total due", due["due"].sum() if "due" in due else 0)
    frame.attrs["customer_due"] = due
    frame.attrs["customer_profile"] = profile
    frame.attrs["warranty_customers"] = warranty
    render_reports(frame, "customers", "customers")


main()
