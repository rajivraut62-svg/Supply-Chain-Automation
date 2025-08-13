import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="AI + Human Supply Chain", layout="wide")
st.title("AI + Human Supply Chain — Fashion Retail")

# ---- project-relative paths (work both locally & in the cloud) ----
ROOT = Path(__file__).parent
DEFAULT_CLEAN = ROOT / "data" / "clean.csv"
DEFAULT_FORE  = ROOT / "data" / "forecast.csv"

def compute_recommendations(
    sales_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    promo_lift: float,
    safety_days: int,
    max_order: int,
    sku_filter=None,
    store_filter=None,
):
    # optional filters
    if sku_filter:
        sales_df = sales_df[sales_df["sku"].isin(sku_filter)]
        forecast_df = forecast_df[forecast_df["sku"].isin(sku_filter)]
    if store_filter:
        sales_df = sales_df[sales_df["location"].isin(store_filter)]
        forecast_df = forecast_df[forecast_df["location"].isin(store_filter)]

    # human promo override
    adj = forecast_df.copy()
    adj["forecast_units"] = (adj["forecast_units"] * (1 + promo_lift)).round().astype(int)

    # latest inventory per sku-location
    latest = (
        sales_df.sort_values("date")
                .groupby(["sku","location"])
                .tail(1)[["sku","location","inv_bop"]]
    )

    # mean daily forecast for safety + horizon math
    mean_daily = (
        adj.groupby(["sku","location"])["forecast_units"]
           .mean().reset_index().rename(columns={"forecast_units":"mean_daily"})
    )

    merged = latest.merge(mean_daily, on=["sku","location"], how="left").fillna(0)

    out_rows = []
    for _, r in merged.iterrows():
        demand_horizon = r["mean_daily"] * 14          # 14-day planning window
        safety         = r["mean_daily"] * safety_days # buffer units
        order_qty      = max(0, int(demand_horizon + safety - r["inv_bop"]))
        if max_order and max_order > 0:
            order_qty = min(order_qty, int(max_order))
        out_rows.append({
            "sku": r["sku"],
            "location": r["location"],
            "mean_daily_fcst": round(r["mean_daily"], 2),
            "inv_bop": int(r["inv_bop"]),
            "safety_days": int(safety_days),
            "order_qty": int(order_qty),
        })
    reco = pd.DataFrame(out_rows).sort_values(["sku","location"]).reset_index(drop=True)
    return adj, reco

st.markdown("Upload **clean.csv** and **forecast.csv** or tick the box to auto-load small demo files from `/data`.")

# choose default files if present
use_defaults = False
if DEFAULT_CLEAN.exists() and DEFAULT_FORE.exists():
    use_defaults = st.checkbox("Use default /data files (skip upload)", value=True)

sales_df = forecast_df = None
if use_defaults:
    sales_df = pd.read_csv(DEFAULT_CLEAN, parse_dates=["date"])
    forecast_df = pd.read_csv(DEFAULT_FORE, parse_dates=["date"])
else:
    c1, c2 = st.columns(2)
    with c1:
        clean_file = st.file_uploader("Upload clean.csv", type="csv")
    with c2:
        forecast_file = st.file_uploader("Upload forecast.csv", type="csv")
    if clean_file is not None and forecast_file is not None:
        sales_df    = pd.read_csv(clean_file, parse_dates=["date"])
        forecast_df = pd.read_csv(forecast_file, parse_dates=["date"])

# human overrides + filters
st.subheader("Human overrides & filters")
c1, c2, c3 = st.columns(3)
with c1:
    promo_lift = st.slider("Promo lift (%)", 0, 300, 10, step=5) / 100.0
with c2:
    unit = st.radio("Safety stock units", ["Days", "Months"], horizontal=True)
    safety_days = st.slider("Safety days", 0, 180, 7, step=1) if unit == "Days" else st.slider("Safety months", 0, 6, 3, step=1) * 30
with c3:
    max_order = st.number_input("Max order per SKU-Store (cap)", min_value=0, value=10000, step=100)

sku_filter = store_filter = None
if sales_df is not None:
    with st.expander("Filters (optional)"):
        sku_filter   = st.multiselect("SKUs",    sorted(sales_df["sku"].unique()))
        store_filter = st.multiselect("Stores",  sorted(sales_df["location"].unique()))

# compute & show
if sales_df is not None and forecast_df is not None:
    adj_fcst, reco = compute_recommendations(
        sales_df, forecast_df, promo_lift, safety_days, max_order, sku_filter, store_filter
    )
    st.subheader("Adjusted forecast (preview)")
    st.dataframe(adj_fcst.head(50), use_container_width=True)

    st.subheader("AI Recommendation (with human overrides)")
    st.dataframe(reco, use_container_width=True)

    st.download_button(
        "Download recommendations CSV",
        data=reco.to_csv(index=False).encode("utf-8"),
        file_name="recommendations.csv",
        mime="text/csv"
    )
else:
    st.info("Upload both files, or tick the checkbox to use defaults.")
