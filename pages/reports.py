"""Shared reports over the live MySQL sales source."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from reports.engine import render_reports
from reports.mysql_source import load_sales_df


def main() -> None:
    st.title("Reports")
    today = date.today()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(today - timedelta(days=89), today),
        key="db_reports_dates",
    )
    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        st.sidebar.warning("Select both a start and an end date.")
        return
    start_date, end_date = date_range
    try:
        frame = load_sales_df(start_date, end_date)
    except Exception as exc:
        st.error("Could not load sales data from MySQL.")
        with st.expander("Database error details"):
            st.write(str(exc))
        return
    render_reports(frame, "db", "reports")


main()
