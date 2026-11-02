"""Admin Summary landing page."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.report_helpers import fmt_taka
from pages.stock_buying import _load_analysis, _settings, buy_now, do_not_buy

_SALES_EPSILON = 0.000001


def _csv_button(df: pd.DataFrame, key: str) -> None:
    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{key}.csv",
        mime="text/csv",
        key=f"{key}_download",
    )


def _format_cover(value: object, daily_sales: object = None) -> str:
    cover = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    daily = pd.to_numeric(pd.Series([daily_sales]), errors="coerce").iloc[0]
    if pd.isna(daily) or daily <= _SALES_EPSILON or pd.isna(cover):
        return "Not selling"
    if cover > 365:
        return "1 year+"
    return f"{cover:,.0f}"


def _format_report_table(
    df: pd.DataFrame, columns: list[tuple[str, str]]
) -> pd.DataFrame:
    display = df[[source for source, _ in columns]].rename(
        columns=dict(columns)
    ).copy()
    for source, label in columns:
        if source == "daily_sales":
            display[label] = pd.to_numeric(display[label], errors="coerce").map(
                lambda value: "—" if pd.isna(value) else f"{value:,.1f}"
            )
        elif source in {"stock_qty", "reorder_qty"}:
            display[label] = pd.to_numeric(display[label], errors="coerce").map(
                lambda value: "—" if pd.isna(value) else f"{value:,.0f}"
            )
        elif source == "cover_days":
            daily = df["daily_sales"]
            display[label] = [
                _format_cover(value, daily.iloc[index])
                for index, value in enumerate(display[label])
            ]
        elif source == "margin_pct":
            display[label] = pd.to_numeric(display[label], errors="coerce").map(
                lambda value: "—" if pd.isna(value) else f"{value:,.1f}%"
            )
        elif source == "stock_value":
            display[label] = pd.to_numeric(display[label], errors="coerce").map(
                lambda value: fmt_taka(value, decimals=0)
            )
    return display


def _buy_reason(row: pd.Series) -> str:
    seller = "Top seller: " if row.get("top_seller", False) else ""
    return (
        f"{seller}only {_format_cover(row['cover_days'], row['daily_sales'])} "
        f"of stock, selling {row['daily_sales']:,.1f}/day, "
        f"margin {row['margin_pct']:,.1f}%"
    )


def _do_not_buy_reason(
    row: pd.Series, target: int, margin: float, multiplier: int
) -> str:
    reasons: list[str] = []
    overstock = row["cover_days"] > target * multiplier
    if overstock:
        reasons.append(
            f"Stock for {_format_cover(row['cover_days'], row['daily_sales'])} days, "
            f"target {target}"
        )
    if row["margin_pct"] < margin:
        reasons.append(f"Margin only {row['margin_pct']:,.1f}%")
    if row["high_return"]:
        reasons.append(f"Returns are {row['return_rate_pct']:,.1f}%")
    if row.get("top_seller", False) and overstock:
        return (
            f"Top seller ({row['daily_sales']:,.1f}/day) but "
            + ", ".join(reasons)
            + ", wait before buying"
        )
    return "; ".join(reasons)


def main() -> None:
    st.title("Admin Summary")
    st.caption("A quick buying signal: start with Buy Now, then review the reasons before placing an order.")
    (
        window,
        target,
        dead,
        margin,
        return_rate,
        minimum_sold,
        overstock_multiple,
    ) = _settings()
    try:
        df, _, _ = _load_analysis(
            window, target, dead, margin, return_rate, minimum_sold
        )
    except Exception as exc:
        st.error(f"Could not load the admin summary: {exc}")
        st.stop()
    if df.empty:
        st.info("No stock data is available yet.")
        st.stop()

    buy = buy_now(df, target, margin)
    avoid = do_not_buy(df, target, margin, overstock_multiple)
    risk = df[(df["daily_sales"] > 0) & ((df["stock_qty"] <= 0) | (df["stock_qty"] < df["RED_LEVEL"]))]
    dead_stock = df[(df["stock_qty"] > 0) & (df["dead_sales_qty"] <= 0)]
    cards = st.columns(4)
    cards[0].metric("Products to buy now", f"{len(buy):,}")
    cards[1].metric("Products not to buy", f"{len(avoid):,}")
    dead_value = fmt_taka(dead_stock["stock_value"].sum())
    cards[2].markdown(
        "<div style='font-size:0.85rem;color:#666'>Money stuck in dead stock</div>"
        f"<div style='font-size:1.55rem;font-weight:600;white-space:nowrap'>{dead_value}</div>",
        unsafe_allow_html=True,
    )
    cards[3].metric("Products at stockout risk", f"{len(risk):,}")

    st.subheader("Buy Now, top 10")
    table = buy.head(10).copy()
    if table.empty:
        st.info("No products need buying under the current rules.")
    else:
        table["Reason"] = table.apply(_buy_reason, axis=1)
        display = _format_report_table(
            table,
            [
                ("PRODUCT_NAME", "Product"),
                ("daily_sales", "Daily sales"),
                ("stock_qty", "Stock qty"),
                ("cover_days", "Cover days"),
                ("margin_pct", "Margin %"),
                ("reorder_qty", "Suggested reorder qty"),
                ("Reason", "Reason"),
            ],
        )
        st.dataframe(display, hide_index=True, width="stretch")
        _csv_button(display, "admin_buy_now")

    st.subheader("Do Not Buy, top 10")
    table = avoid.head(10).copy()
    if table.empty:
        st.info("No products are currently flagged not to buy.")
    else:
        table["Reason"] = table.apply(
            lambda row: _do_not_buy_reason(
                row, target, margin, overstock_multiple
            ),
            axis=1,
        )
        display = _format_report_table(
            table,
            [
                ("PRODUCT_NAME", "Product"),
                ("daily_sales", "Daily sales"),
                ("stock_qty", "Stock qty"),
                ("cover_days", "Cover days"),
                ("margin_pct", "Margin %"),
                ("stock_value", "Money tied up in stock"),
                ("Reason", "Reason"),
            ],
        )
        st.dataframe(display, hide_index=True, width="stretch")
        _csv_button(display, "admin_do_not_buy")
    st.caption(
        "Buy Now means sales are brisk, stock cover is below target, and margin clears the threshold. "
        "All rules can be changed with the sidebar sliders."
    )
    with st.expander("Why the old Do Not Buy count was high"):
        old_overstock = df["cover_days"] > target * overstock_multiple
        old_low_margin = df["margin_pct"] < margin
        old_very_low_sales = df["daily_sales"] <= 0
        old_flags = pd.DataFrame(
            {
                "Overstock": old_overstock,
                "Low margin": old_low_margin,
                "Very low sales": old_very_low_sales,
            }
        )
        old_count = old_flags.any(axis=1)
        breakdown = pd.DataFrame(
            {
                "Legacy 439 reason": [
                    "Overstock only",
                    "Low margin only",
                    "Very low sales only",
                    "More than one reason",
                ],
                "Products": [
                    int((old_overstock & ~old_low_margin & ~old_very_low_sales).sum()),
                    int((old_low_margin & ~old_overstock & ~old_very_low_sales).sum()),
                    int((old_very_low_sales & ~old_overstock & ~old_low_margin).sum()),
                    int((old_flags.sum(axis=1) > 1).sum()),
                ],
            }
        )
        st.dataframe(breakdown, hide_index=True, width="stretch")
        st.caption(
            f"The old total was {int(old_count.sum())}: overstock > "
            f"{target * overstock_multiple} cover days, low margin < {margin:.1f}%, "
            "or very low sales (daily sales <= 0). High return rate was not part "
            "of that old total."
        )
        st.write(
            f"New high-return candidates: {int(df['high_return'].sum())} "
            f"(return rate > {return_rate:.1f}% and at least {minimum_sold} sold). "
            "They are now included in the tightened Do Not Buy list."
        )


main()
