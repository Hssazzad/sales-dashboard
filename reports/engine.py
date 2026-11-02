"""Shared report registry, cleaning helpers, and Streamlit renderers."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import re
from typing import Any, Callable

import numpy as np
import pandas as pd
import streamlit as st

STANDARD_FIELDS = (
    "product_name", "quantity", "sales_amount", "date", "product_group",
    "brand", "stock_quantity", "cost", "profit", "returns", "customer",
    "invoice", "due", "paid",
)


def is_mapped(mapping: dict[str, Any], field: str, df: pd.DataFrame) -> bool:
    value = mapping.get(field, field)
    return value is not None and str(value).strip() not in {"", "Not mapped"} and str(value) in df.columns


def to_number(series: pd.Series) -> pd.Series:
    digits = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
    values = series.astype("string").str.strip().str.translate(digits)
    values = values.mask(values.str.casefold().isin({"", "-", "nan", "none"}))
    values = values.str.replace(r"[,\s৳$]", "", regex=True)
    values = values.str.replace(r"(?i)tk|bdt", "", regex=True)
    values = values.str.replace(r"(?i)(?:pcs|units?)$", "", regex=True)
    return pd.to_numeric(values, errors="coerce")


@st.cache_data(ttl=300, show_spinner=False)
def build_equivalent_product_table(df: pd.DataFrame) -> pd.DataFrame:
    """Build one row per product without multiplying repeated stock values."""
    columns = ["product_name", "product_group", "stock_quantity", "sold"]
    if "product_name" not in df or df.empty:
        return pd.DataFrame(columns=columns)
    source = df.loc[:, ~df.columns.duplicated()].copy()
    source["product_name"] = source["product_name"].astype("string").str.strip()
    source = source[source["product_name"].notna() & source["product_name"].ne("")]
    if source.empty:
        return pd.DataFrame(columns=columns)
    source["product_group"] = (
        source["product_group"].astype("string").fillna("").str.strip()
        if "product_group" in source
        else ""
    )
    source["stock_quantity"] = (
        pd.to_numeric(source["stock_quantity"], errors="coerce").fillna(0)
        if "stock_quantity" in source
        else 0
    )
    source["sold"] = (
        pd.to_numeric(source["sold"], errors="coerce").fillna(0)
        if "sold" in source
        else pd.to_numeric(source["quantity"], errors="coerce").fillna(0)
        if "quantity" in source
        else 0
    )
    result = source.groupby("product_name", as_index=False).agg(
        product_group=("product_group", "first"),
        stock_quantity=("stock_quantity", "max"),
        sold=("sold", "sum"),
    )
    return result.loc[:, columns]


@st.cache_data(ttl=300, show_spinner=False)
def find_equivalent_products(df: pd.DataFrame) -> pd.DataFrame:
    """Return one directed row for each pair of products sharing model codes."""
    columns = [
        "product_name",
        "product_group",
        "stock_quantity",
        "sold",
        "shared_codes",
        "equivalent_product",
    ]
    if "product_name" not in df or df.empty:
        return pd.DataFrame(columns=columns)

    source = df.loc[:, ~df.columns.duplicated()].copy()
    if source.empty or "product_name" not in source:
        return pd.DataFrame(columns=columns)
    has_product_group = "product_group" in source
    if "sold" not in source:
        source["sold"] = (
            pd.to_numeric(source["quantity"], errors="coerce").fillna(0)
            if "quantity" in source
            else 0
        )
    summary = source.copy()

    def model_codes(name: str) -> set[str]:
        return {
            token.upper()
            for token in re.split(r"[/,\s]+", name)
            if token and any(character.isdigit() for character in token)
        }

    rows: list[dict[str, Any]] = []
    for left_index, left in summary.iterrows():
        for right_index, right in summary.iterrows():
            if left_index == right_index:
                continue
            shared = sorted(
                model_codes(str(left["product_name"]))
                & model_codes(str(right["product_name"]))
            )
            if not shared:
                continue
            if has_product_group and left["product_group"] != right["product_group"]:
                continue
            rows.append(
                {
                    "product_name": left["product_name"],
                    "product_group": left["product_group"],
                    "stock_quantity": left["stock_quantity"],
                    "sold": left["sold"],
                    "shared_codes": "  ".join(shared),
                    "equivalent_product": right["product_name"],
                    "equivalent_product_group": right["product_group"],
                    "equivalent_stock_quantity": right["stock_quantity"],
                    "equivalent_sold": right["sold"],
                }
            )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class ReportSpec:
    group: str
    label: str
    fields: tuple[str, ...]
    renderer: Callable[[pd.DataFrame, str], None]
    section: str


def _sales_field(df: pd.DataFrame) -> str | None:
    if "sales_amount" in df:
        return "sales_amount"
    if "quantity" in df:
        return "quantity"
    return None


def _table(df: pd.DataFrame, key: str) -> None:
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{key}.csv",
        mime="text/csv",
        key=f"{key}_download",
    )


def _admin(df: pd.DataFrame, key: str) -> None:
    if "product_name" in df and _sales_field(df):
        sales = _sales_field(df)
        totals = df.groupby("product_name", as_index=False)[sales].sum()
        st.subheader("Best-selling products")
        _table(totals.nlargest(10, sales), f"{key}_best_selling")
        st.subheader("Worst-selling products")
        _table(totals.nsmallest(10, sales), f"{key}_worst_selling")
        st.subheader("What to buy next month / What not to buy")
        _table(totals.nlargest(10, sales), f"{key}_buying")
        _table(totals.nsmallest(10, sales), f"{key}_do_not_buy")
    if "customer" in df and "due" in df:
        result = df.groupby("customer", as_index=False)["due"].sum().nlargest(10, "due")
        st.subheader("Customers with highest due")
        _table(result, f"{key}_highest_due")
    if "product_name" in df and "stock_quantity" in df:
        result = df.groupby("product_name", as_index=False)["stock_quantity"].max()
        result = result[result["stock_quantity"] > 0].nlargest(10, "stock_quantity")
        st.subheader("Products stuck in stock")
        _table(result, f"{key}_stuck_stock")


def _sales(df: pd.DataFrame, key: str, label: str) -> None:
    sales = _sales_field(df)
    if label in {"Top products", "Bottom products"}:
        result = df.groupby("product_name", as_index=False)[sales].sum()
        result = result.nlargest(10, sales) if label == "Top products" else result.nsmallest(10, sales)
        _table(result, f"{key}_{label.lower().replace(' ', '_')}")
        st.bar_chart(result.set_index("product_name")[sales], horizontal=True)
    elif label == "Monthly trend":
        result = df.assign(period=df["date"].dt.to_period("M").astype(str)).groupby("period", as_index=False)[sales].sum()
        _table(result, f"{key}_monthly_trend")
        st.line_chart(result, x="period", y=sales)
    elif label == "Peak period":
        for title, values in (
            ("Month", df["date"].dt.to_period("M").astype(str)),
            ("Weekday", df["date"].dt.day_name()),
            ("Day of month", df["date"].dt.day),
        ):
            result = df.assign(period=values).groupby("period", as_index=False)[sales].sum().sort_values(sales, ascending=False)
            result.insert(0, "highlight", ["Top period"] + [""] * (len(result) - 1))
            st.subheader(title)
            _table(result, f"{key}_peak_{title.lower().replace(' ', '_')}")
    else:
        column = "product_group" if label == "Group sales" else "brand"
        result = df.groupby(column, as_index=False)["sales_amount"].sum().sort_values("sales_amount", ascending=False)
        _table(result, f"{key}_{label.lower().replace(' ', '_')}")
        st.bar_chart(result.set_index(column)["sales_amount"], horizontal=True)


def _stock(df: pd.DataFrame, key: str, label: str) -> None:
    if label == "Long time in stock":
        days = st.number_input("No sales in the last days", min_value=1, value=60, step=1, key=f"{key}_long_days")
        cutoff = df["date"].max() - pd.Timedelta(days=days)
        rows = []
        for product, group in df.groupby("product_name"):
            latest = group["date"].max()
            stock = group.loc[group["date"] == latest, "stock_quantity"].max()
            if stock > 0 and group[group["date"] >= cutoff].get("quantity", pd.Series(dtype=float)).sum() <= 0:
                customers = ", ".join(sorted(group["customer"].dropna().unique())) if "customer" in group else ""
                rows.append({"product_name": product, "stock_quantity": stock, "last_date": latest, "customers_who_may_buy_it": customers})
        _table(pd.DataFrame(rows), f"{key}_long_time_stock")
        return
    if label == "Sales drop from stock-out":
        sales = _sales_field(df)
        rows = []
        for product, group in df.sort_values("date").groupby("product_name"):
            threshold = group["stock_quantity"].quantile(0.25)
            low = group[group["stock_quantity"] <= threshold]
            if low.empty:
                continue
            point = low["date"].min()
            before, after = group[group["date"] < point][sales].sum(), group[group["date"] >= point][sales].sum()
            if before > 0 and after < before:
                rows.append({"product_name": product, "stock_out_date": point, "sales_before": before, "sales_after": after})
        _table(pd.DataFrame(rows), f"{key}_stock_out_drop")
        return
    totals = df.groupby("product_name", as_index=False).agg(
        stock_quantity=("stock_quantity", "max"),
        sales=("quantity", "sum"),
    )
    totals["daily_sales"] = totals["sales"] / max(df["date"].dt.date.nunique(), 1)
    totals["reorder_quantity"] = np.maximum(0, np.ceil(totals["daily_sales"] * 30 - totals["stock_quantity"]))
    if label == "Low stock":
        result = totals[totals["stock_quantity"] <= 0]
    elif label == "Slow-moving":
        result = totals[(totals["stock_quantity"] > 0) & (totals["sales"] <= totals["sales"].median())]
    else:
        result = totals[totals["reorder_quantity"] > 0].sort_values("reorder_quantity", ascending=False)
    _table(result, f"{key}_{label.lower().replace(' ', '_')}")


def _customers(df: pd.DataFrame, key: str, label: str) -> None:
    sales = _sales_field(df)
    if label == "Customer profile":
        profile = df.attrs.get("customer_profile")
        if not isinstance(profile, pd.DataFrame) or profile.empty:
            return

        def meaningful(value: object) -> bool:
            return str(value).strip().upper() not in {"", "-", ".", "`", "MR..........."}

        options = [
            f"{row.get('customer', '')} — {row.get('mobile', '')}"
            for _, row in profile.iterrows()
        ]
        selected = st.selectbox("Search customer...", options, key=f"{key}_customer")
        selected_index = options.index(selected)
        selected_row = profile.iloc[selected_index]
        with st.container(border=True):
            st.subheader(str(selected_row.get("customer", "")))
            st.caption(str(selected_row.get("customer_type", "")))
            st.caption(str(selected_row.get("customer_group", "")))
            contact_fields = (
                ("Address", "address"),
                ("Mobile", "mobile"),
                ("Phone", "phone"),
                ("Email", "email"),
                ("Contact person", "contact_person"),
            )
            for title, field in contact_fields:
                value = selected_row.get(field, "")
                if meaningful(value):
                    st.write(f"**{title}:** {value}")
            credit_limit = pd.to_numeric(
                pd.Series([selected_row.get("credit_limit", 0)]), errors="coerce"
            ).fillna(0).iloc[0]
            if credit_limit > 0:
                st.write(f"**Credit limit:** {credit_limit:g}")
            bin_value = str(selected_row.get("bin", "")).strip()
            if len(bin_value) >= 5 and meaningful(bin_value):
                st.write(f"**BIN:** {bin_value}")
            balance = pd.to_numeric(
                pd.Series([selected_row.get("balance", 0)]), errors="coerce"
            ).fillna(0).iloc[0]
            st.write(f"**Balance:** {balance:g}")

        if (
            {"customer", "date", "sales_amount", "product_name"} <= set(df.columns)
        ):
            customer_name = selected_row.get("customer", "")
            customer_sales = df[df["customer"] == customer_name].copy()
            if not customer_sales.empty:
                customer_sales["sales_amount"] = to_number(customer_sales["sales_amount"]).fillna(0)
                customer_sales["date"] = pd.to_datetime(customer_sales["date"], errors="coerce")
                customer_sales = customer_sales.dropna(subset=["date"])
                if not customer_sales.empty:
                    last_purchase = customer_sales["date"].max()
                    st.write(f"**Total sales:** {customer_sales['sales_amount'].sum():g}")
                    st.write(f"**Last purchase date:** {last_purchase.date()}")
                    st.write(f"**Days since last purchase:** {(pd.Timestamp.today().normalize() - last_purchase.normalize()).days}")
                    top_products = (
                        customer_sales.groupby("product_name", as_index=False)["sales_amount"]
                        .sum()
                        .sort_values("sales_amount", ascending=False)
                        .head(10)
                    )
                    _table(top_products, f"{key}_top_products")

        completeness = []
        total = len(profile)
        for label_name, field in contact_fields:
            filled = profile[field].map(meaningful).sum()
            completeness.append(
                {"field": label_name, "filled": int(filled), "percent": round(filled / total * 100, 1)}
            )
        for label_name, field in (("Credit limit", "credit_limit"), ("BIN", "bin")):
            if field == "credit_limit":
                filled = pd.to_numeric(profile[field], errors="coerce").fillna(0).gt(0).sum()
            else:
                filled = profile[field].map(lambda value: len(str(value).strip()) >= 5 and meaningful(value)).sum()
            completeness.append(
                {"field": label_name, "filled": int(filled), "percent": round(filled / total * 100, 1)}
            )
        with st.expander("Profile completeness"):
            _table(pd.DataFrame(completeness), f"{key}_profile_completeness")
    elif label == "Warranty customers":
        result = df.attrs.get("warranty_customers")
        if not isinstance(result, pd.DataFrame) or result.empty:
            return
        status = st.selectbox(
            "Status",
            ["All", "Active", "Expiring soon", "Expired"],
            key=f"{key}_status",
        )
        if status != "All":
            result = result[result["status"] == status]
        _table(result, f"{key}_warranty_customers")
    elif label == "Customer vs product":
        products, customers = sorted(df["product_name"].unique()), sorted(df["customer"].unique())
        product = st.selectbox("Choose a product", products, key=f"{key}_product")
        customer = st.selectbox("Choose a customer", customers, key=f"{key}_customer")
        _table(df[df["product_name"] == product].groupby("customer", as_index=False)[sales].sum(), f"{key}_buyers")
        _table(df[df["customer"] == customer].groupby("product_name", as_index=False)[sales].sum(), f"{key}_products")
    elif label == "Inactive customers":
        days = st.number_input("Inactive for more than days", min_value=1, value=30, step=1, key=f"{key}_days")
        result = df.groupby("customer", as_index=False).agg(last_purchase=("date", "max"), total_spent=("sales_amount", "sum") if "sales_amount" in df else ("date", "count"))
        result["days_since"] = (df["date"].max() - result["last_purchase"]).dt.days
        _table(result[result["days_since"] > days], f"{key}_inactive")
    elif label == "Top customers":
        result = df.groupby("customer", as_index=False)["sales_amount"].sum().sort_values("sales_amount", ascending=False)
        _table(result, f"{key}_top")
        _table(result.head(max(1, int(np.ceil(len(result) * 0.1)))), f"{key}_gift_candidates")
    elif label == "Good vs bad customers":
        result = df.attrs.get("customer_due")
        if not isinstance(result, pd.DataFrame):
            result = df.groupby("customer", as_index=False).agg(
                due=("due", "sum"),
                last_collection_date=("date", "max"),
                last_sale_date=("date", "max"),
                total_sales=("sales_amount", "sum"),
            )
        else:
            result = result.copy()
        result["due"] = pd.to_numeric(result["due"], errors="coerce").clip(lower=0).fillna(0)
        result["total_sales"] = pd.to_numeric(result["total_sales"], errors="coerce").fillna(0)
        collection_dates = pd.to_datetime(result["last_collection_date"], errors="coerce")
        sale_dates = pd.to_datetime(result["last_sale_date"], errors="coerce")
        pending_from = collection_dates.fillna(sale_dates)
        result["days_pending"] = (pd.Timestamp.today().normalize() - pending_from).dt.days
        result["days_pending"] = result["days_pending"].clip(lower=0).fillna(0)
        result["due_ratio"] = result["due"].div(result["total_sales"].where(result["total_sales"] != 0))
        due_percentile = result["due"].rank(pct=True).mul(100)
        days_percentile = result["days_pending"].rank(pct=True).mul(100)
        result["bad_score"] = (due_percentile + days_percentile) * 0.5
        result["flag"] = np.where(result["due_ratio"] > 0.5, "Due > 50% of sales", "")
        result = result.sort_values("bad_score", ascending=False).reset_index(drop=True)
        st.metric("Total due", result["due"].sum())
        show = st.selectbox(
            "Show",
            ["Bad customers", "Good customers", "All customers"],
            key=f"{key}_show",
        )
        if show == "Bad customers":
            result = result.head(20)
        elif show == "Good customers":
            result = result.sort_values("bad_score", ascending=True).head(20)
        _table(
            result[
                [
                    "customer",
                    "due",
                    "days_pending",
                    "due_ratio",
                    "total_sales",
                    "bad_score",
                    "flag",
                ]
            ],
            f"{key}_{show.lower().replace(' ', '_')}",
        )
    else:
        per_unit = st.checkbox("Cost is per unit", value=False, key=f"{key}_per_unit")
        if "profit" in df:
            profit = df["profit"]
        else:
            profit = df["sales_amount"] - (df["cost"] * df["quantity"] if per_unit and "quantity" in df else df["cost"])
        result = df.assign(profit_value=profit).groupby("customer", as_index=False).agg(sales_amount=("sales_amount", "sum"), profit=("profit_value", "sum"))
        _table(result.sort_values("profit", ascending=False), f"{key}_profit")


def _basket(df: pd.DataFrame, key: str) -> None:
    counts = df.groupby("product_name")["invoice"].nunique()
    pairs: list[dict[str, Any]] = []
    for _, values in df.groupby("invoice")["product_name"]:
        for first, second in combinations(sorted(set(values)), 2):
            pairs.append({"product_a": first, "product_b": second})
    result = pd.DataFrame(pairs).value_counts(["product_a", "product_b"]).reset_index(name="count") if pairs else pd.DataFrame(columns=["product_a", "product_b", "count"])
    if not result.empty:
        result["confidence_a_to_b"] = result.apply(lambda r: r["count"] / counts.get(r["product_a"], 1), axis=1)
        result["confidence_b_to_a"] = result.apply(lambda r: r["count"] / counts.get(r["product_b"], 1), axis=1)
    _table(result.head(20), f"{key}_pairs")
    if not result.empty:
        product = st.selectbox("Choose a product", sorted(df["product_name"].unique()), key=f"{key}_product")
        related = result[(result["product_a"] == product) | (result["product_b"] == product)].copy()
        related["usually_bought_with"] = related.apply(lambda row: row["product_b"] if row["product_a"] == product else row["product_a"], axis=1)
        _table(related, f"{key}_related")


def _returns(df: pd.DataFrame, key: str) -> None:
    _table(df.groupby("product_name", as_index=False)["returns"].sum().sort_values("returns", ascending=False), f"{key}_returns")


def _profit(df: pd.DataFrame, key: str) -> None:
    per_unit = st.checkbox("Cost is per unit", value=False, key=f"{key}_per_unit")
    if "profit" in df:
        value = df["profit"]
    else:
        value = df["sales_amount"] - (df["cost"] * df["quantity"] if per_unit and "quantity" in df else df["cost"])
    result = df.assign(profit_value=value).groupby("product_name", as_index=False).agg(sales_amount=("sales_amount", "sum"), profit=("profit_value", "sum"))
    _table(result.sort_values("profit", ascending=False), f"{key}_profit")


def _forecast(df: pd.DataFrame, key: str) -> None:
    sales = _sales_field(df)
    totals = df.groupby("product_name", as_index=False)[sales].sum()
    daily = totals[sales] / max(df["date"].dt.date.nunique(), 1)
    totals["next_month"] = daily * 30
    st.subheader("Buy")
    _table(totals[totals["next_month"] > totals[sales]], f"{key}_buy")
    st.subheader("Do not buy")
    _table(totals[totals["next_month"] <= totals[sales]], f"{key}_do_not_buy")


def _new_and_rising(df: pd.DataFrame, key: str) -> None:
    try:
        sales_field = _sales_field(df)
        if sales_field is None or "product_name" not in df or "date" not in df:
            st.info("No new or rising products found")
            return
        days = st.number_input(
            "Look back days",
            min_value=1,
            value=90,
            step=1,
            key=f"{key}_days",
        )
        source = df.loc[:, ~df.columns.duplicated()].copy()
        source["date"] = pd.to_datetime(source["date"], errors="coerce")
        source = source.dropna(subset=["date", "product_name"]).copy()
        if source.empty:
            st.info("No new or rising products found")
            return
        source[sales_field] = to_number(source[sales_field]).fillna(0)
        if "sales_amount" in source:
            source["sales_amount"] = to_number(source["sales_amount"]).fillna(0)
        latest_date = source["date"].max().normalize()
        recent_start = latest_date - pd.Timedelta(days=int(days) - 1)
        previous_start = recent_start - pd.Timedelta(days=int(days))
        recent = source[source["date"] >= recent_start]
        previous = source[
            (source["date"] >= previous_start) & (source["date"] < recent_start)
        ]

        first_sales = source.groupby("product_name", as_index=False)["date"].min()
        new_names = set(first_sales.loc[first_sales["date"] >= recent_start, "product_name"])
        new_source = recent[recent["product_name"].isin(new_names)]
        new_grouped = new_source.groupby("product_name", as_index=False).agg(
            first_sale_date=("date", "min"),
            quantity_sold_since=(sales_field, "sum"),
        )
        if sales_field == "sales_amount":
            new_grouped["sales_amount"] = new_grouped["quantity_sold_since"]
            new_grouped = new_grouped.drop(columns=["quantity_sold_since"])
        elif "sales_amount" in source:
            amount = source[source["product_name"].isin(new_names)].groupby("product_name")["sales_amount"].sum()
            new_grouped["sales_amount"] = new_grouped["product_name"].map(amount)
        if "customer" in source:
            counts = new_source.groupby("product_name")["customer"].nunique()
            new_grouped["customers_count"] = new_grouped["product_name"].map(counts)
        new_grouped = new_grouped.sort_values(
            "sales_amount" if sales_field == "sales_amount" else "quantity_sold_since",
            ascending=False,
        )

        recent_totals = recent.groupby("product_name", as_index=False)[sales_field].sum()
        previous_totals = previous.groupby("product_name", as_index=False)[sales_field].sum()
        rising = recent_totals.merge(
            previous_totals,
            on="product_name",
            how="inner",
            suffixes=("_recent", "_previous"),
        )
        rising = rising[rising[f"{sales_field}_previous"] > 0].copy()
        rising["growth_percent"] = (
            (rising[f"{sales_field}_recent"] - rising[f"{sales_field}_previous"])
            / rising[f"{sales_field}_previous"]
            * 100
        )
        rising = rising[rising["growth_percent"] >= 50].rename(
            columns={
                f"{sales_field}_previous": "previous_period_qty",
                f"{sales_field}_recent": "recent_qty",
            }
        )
        rising = rising[
            ["product_name", "previous_period_qty", "recent_qty", "growth_percent"]
        ].sort_values("growth_percent", ascending=False)

        if new_grouped.empty and rising.empty:
            st.info("No new or rising products found")
            return
        st.subheader("New products")
        _table(new_grouped, f"{key}_new_products")
        st.subheader("Rising products")
        _table(rising, f"{key}_rising_products")
        st.caption(
            "This shows products new or growing in our own sales. "
            "It does not include market-wide data."
        )
    except Exception as exc:
        st.warning("This report could not be built")
        with st.expander("Error details"):
            st.write(str(exc))


REPORTS = (
    ReportSpec("Admin Summary", "Admin Summary", (), _admin, "reports"),
    ReportSpec("Sales", "Top products", ("product_name",), lambda d, k: _sales(d, k, "Top products"), "reports"),
    ReportSpec("Sales", "Bottom products", ("product_name",), lambda d, k: _sales(d, k, "Bottom products"), "reports"),
    ReportSpec("Sales", "Monthly trend", ("date",), lambda d, k: _sales(d, k, "Monthly trend"), "reports"),
    ReportSpec("Sales", "Peak period", ("date",), lambda d, k: _sales(d, k, "Peak period"), "reports"),
    ReportSpec("Sales", "New and rising products", ("product_name", "date"), _new_and_rising, "reports"),
    ReportSpec("Sales", "Group sales", ("product_group", "sales_amount"), lambda d, k: _sales(d, k, "Group sales"), "reports"),
    ReportSpec("Sales", "Brand sales", ("brand", "sales_amount"), lambda d, k: _sales(d, k, "Brand sales"), "reports"),
    ReportSpec("Stock and Buying", "Low stock", ("product_name", "stock_quantity"), lambda d, k: _stock(d, k, "Low stock"), "reports"),
    ReportSpec("Stock and Buying", "Slow-moving", ("product_name", "stock_quantity", "date"), lambda d, k: _stock(d, k, "Slow-moving"), "reports"),
    ReportSpec("Stock and Buying", "Reorder suggestions", ("product_name", "stock_quantity"), lambda d, k: _stock(d, k, "Reorder suggestions"), "reports"),
    ReportSpec("Stock and Buying", "Long time in stock", ("product_name", "stock_quantity", "date"), lambda d, k: _stock(d, k, "Long time in stock"), "reports"),
    ReportSpec("Stock and Buying", "Sales drop from stock-out", ("product_name", "date", "stock_quantity"), lambda d, k: _stock(d, k, "Sales drop from stock-out"), "reports"),
    ReportSpec("Stock and Buying", "Ink and printer together", ("invoice", "product_name"), _basket, "reports"),
    ReportSpec("Customers", "Customer vs product", ("customer", "product_name"), lambda d, k: _customers(d, k, "Customer vs product"), "customers"),
    ReportSpec("Customers", "Inactive customers", ("customer", "date"), lambda d, k: _customers(d, k, "Inactive customers"), "customers"),
    ReportSpec("Customers", "Top customers", ("customer", "sales_amount"), lambda d, k: _customers(d, k, "Top customers"), "customers"),
    ReportSpec("Customers", "Good vs bad customers", ("customer", "due", "sales_amount"), lambda d, k: _customers(d, k, "Good vs bad customers"), "customers"),
    ReportSpec("Customers", "Customer profit", ("customer", "sales_amount"), lambda d, k: _customers(d, k, "Customer profit"), "customers"),
    ReportSpec("Customers", "Warranty customers", (), lambda d, k: _customers(d, k, "Warranty customers"), "customers"),
    ReportSpec("Customers", "Customer profile", (), lambda d, k: _customers(d, k, "Customer profile"), "customers"),
    ReportSpec("Returns", "Returns report", ("returns",), _returns, "reports"),
    ReportSpec("Profit", "Profit", ("product_name", "sales_amount"), _profit, "reports"),
    ReportSpec("Forecast", "Next month forecast", ("product_name", "date"), _forecast, "reports"),
)


def _available(df: pd.DataFrame, section: str) -> list[ReportSpec]:
    result = []
    sales = _sales_field(df)
    for spec in REPORTS:
        if spec.section != section:
            continue
        if spec.label == "Admin Summary":
            result.append(spec)
            continue
        fields = spec.fields
        if any(
            field not in df.columns and not (field == "sales_amount" and _sales_field(df))
            and not (spec.label == "Good vs bad customers" and isinstance(df.attrs.get("customer_due"), pd.DataFrame) and field == "due")
            for field in fields
        ):
            continue
        if spec.group in {"Sales", "Forecast"} and sales is None:
            continue
        if spec.label == "New and rising products" and sales is None:
            continue
        if spec.label in {"Top products", "Bottom products"} and sales is None:
            continue
        if spec.label == "Customer profit" and not ({"profit", "cost"} & set(df.columns)):
            continue
        if spec.label == "Warranty customers":
            warranty = df.attrs.get("warranty_customers")
            if not isinstance(warranty, pd.DataFrame) or warranty.empty:
                continue
        if spec.label == "Customer profile":
            profile = df.attrs.get("customer_profile")
            if not isinstance(profile, pd.DataFrame) or profile.empty:
                continue
        if spec.label == "Profit" and not ({"profit", "cost"} & set(df.columns)):
            continue
        if spec.label == "Sales drop from stock-out" and sales is None:
            continue
        if spec.label == "Group sales" or spec.label == "Brand sales":
            if "sales_amount" not in df:
                continue
        result.append(spec)
    return result


@st.cache_data(ttl=300, show_spinner="Preparing report data...")
def _cached_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df.copy()


def render_reports(df: pd.DataFrame, key_prefix: str, section: str) -> None:
    """Render one selected report from the standard dataframe schema."""
    df = _cached_frame(df)
    if df.empty or not len(df.columns):
        st.error("No data in CSV file")
        return
    available = _available(df, section)
    if not available:
        st.error("No data in CSV file")
        return
    labels = {
        spec: spec.label if spec.group == "Admin Summary" else f"{spec.group} - {spec.label}"
        for spec in available
    }
    options = list(labels.values())
    selected = st.selectbox("Select report", options, index=0, key=f"{key_prefix}_report")
    spec = next(item for item in available if labels[item] == selected)
    try:
        spec.renderer(df, f"{key_prefix}_{selected.lower().replace(' ', '_')}")
    except Exception as exc:
        st.warning("This report could not be built from this file")
        with st.expander("Report error details"):
            st.write(str(exc))
