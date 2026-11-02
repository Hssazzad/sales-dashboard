"""Database-managed navigation for the dashboard pages."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import text

from src.db import get_engine


_PAGE_PATHS = {
    "admin_summary": "pages/admin_summary.py",
    "stock_buying": "pages/stock_buying.py",
    "return_report": "pages/return_report.py",
    "dashboard": "pages/dashboard.py",
    "sales": "pages/sales.py",
    "sales_report": "pages/sales_report.py",
    "profit_report": "pages/profit_report.py",
    "csv_analysis": "pages/csv_analysis.py",
}
_DEFAULT_MENUS = (
    {"page_key": "admin_summary", "title": "Admin Summary", "menu_order": 1},
    {"page_key": "stock_buying", "title": "Stock and Buying", "menu_order": 2},
    {"page_key": "return_report", "title": "Return Report", "menu_order": 3},
    {"page_key": "dashboard", "title": "Dashboard", "menu_order": 4},
    {"page_key": "sales", "title": "Sales", "menu_order": 5},
    {"page_key": "sales_report", "title": "Sales Report", "menu_order": 6},
    {"page_key": "profit_report", "title": "Profit Report", "menu_order": 7},
)


def _ensure_menu_table() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dashboard_menu (
                    page_key VARCHAR(32) NOT NULL PRIMARY KEY,
                    title VARCHAR(50) NOT NULL,
                    menu_order SMALLINT UNSIGNED NOT NULL,
                    is_enabled TINYINT(1) NOT NULL DEFAULT 1
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT IGNORE INTO dashboard_menu (page_key, title, menu_order)
                VALUES (:page_key, :title, :menu_order)
                """
            ),
            list(_DEFAULT_MENUS),
        )


def load_navigation_pages() -> list[st.Page]:
    """Load enabled, known pages in their database-defined order."""
    _ensure_menu_table()
    with get_engine().connect() as connection:
        menus = connection.execute(
            text(
                """
                SELECT page_key, title
                FROM dashboard_menu
                WHERE is_enabled = 1
                ORDER BY menu_order, page_key
                """
            )
        ).mappings().all()

    unknown_pages = {menu["page_key"] for menu in menus} - _PAGE_PATHS.keys()
    if unknown_pages:
        raise RuntimeError("dashboard_menu contains an unknown page key.")
    if not menus:
        raise RuntimeError("No navigation menus are enabled.")

    pages = [
        st.Page(
            _PAGE_PATHS[menu["page_key"]],
            title=menu["title"],
            default=index == 0,
        )
        for index, menu in enumerate(menus)
    ]
    # CSV Analysis is additive and is intentionally not inserted into the
    # database-managed menu table, keeping existing application tables read-only.
    if "csv_analysis" not in {menu["page_key"] for menu in menus}:
        pages.append(st.Page(_PAGE_PATHS["csv_analysis"], title="CSV Analysis"))
    return pages
