import streamlit as st
import pandas as pd
from agent import process_item

# ---------------------------
# PAGE CONFIG
# ---------------------------
st.set_page_config(
    page_title="Eco-Arbitrage AI",
    layout="wide"
)

st.title("🌿 Eco-Arbitrage AI: Inventory Intelligence System")
st.caption("Autonomous AI system that detects overstock and generates automated liquidation strategies.")

# ---------------------------
# LOAD DATA
# ---------------------------
try:
    df = pd.read_csv("data.csv")
except FileNotFoundError:
    st.error("Dataset not found. Please ensure data.csv exists in the project root.")
    st.stop()

# ---------------------------
# SIDEBAR FILTERS (IMPORTANT UPGRADE)
# ---------------------------
st.sidebar.header("Control Panel")

min_days = st.sidebar.slider("Minimum Inventory Age (Days)", 0, 300, 90)
category_filter = st.sidebar.multiselect(
    "Filter by Category",
    options=df["category"].unique(),
    default=df["category"].unique()
)

filtered_df = df[
    (df["inventory_age_days"] >= min_days) &
    (df["category"].isin(category_filter))
]

# ---------------------------
# KPI DASHBOARD
# ---------------------------
overstock = filtered_df

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Inventory", len(df))
col2.metric("Filtered Items", len(filtered_df))
col3.metric("At-Risk Stock", len(overstock))
col4.metric("System Status", "ACTIVE")

st.divider()

# ---------------------------
# INVENTORY VIEW
# ---------------------------
st.subheader("Inventory Snapshot")
st.dataframe(filtered_df, use_container_width=True)

st.divider()

# ---------------------------
# AI ENGINE
# ---------------------------
st.subheader("AI Liquidation Engine")

if st.button("Run AI Optimization"):
    results = []

    progress = st.progress(0)

    if len(overstock) == 0:
        st.warning("No overstock items match current filters.")
        st.stop()

    for i, (_, row) in enumerate(overstock.iterrows()):
        ai = process_item(row)

        profit = ai["resale_price"] - row["original_cost_usd"]

        results.append({
            "SKU": row["product_id"],
            "Item": row["product_name"],
            "Category": row["category"],
            "Age (Days)": row["inventory_age_days"],
            "Urgency": ai["urgency"],
            "Resale Price": round(ai["resale_price"], 2),
            "Est. Profit": round(profit, 2),
            "CO2 Impact (kg)": row["waste_footprint_kg"],
            "AI Strategy": ai["description"]
        })

        progress.progress((i + 1) / len(overstock))

    result_df = pd.DataFrame(results)

    st.success("AI Analysis Complete")

    # ---------------------------
    # RESULTS DISPLAY (UPGRADED)
    # ---------------------------
    st.subheader("Optimization Results")
    st.dataframe(result_df, use_container_width=True)

    st.divider()

    # ---------------------------
    # BUSINESS IMPACT DASHBOARD
    # ---------------------------
    total_profit = result_df["Est. Profit"].sum()
    total_co2 = result_df["CO2 Impact (kg)"].sum()

    c1, c2 = st.columns(2)

    c1.metric(
        "Estimated Revenue Recovery",
        f"${total_profit:,.2f}"
    )

    c2.metric(
        "Estimated Environmental Impact",
        f"{total_co2:,.2f} kg CO2 prevented"
    )

    st.divider()

    # ---------------------------
    # URGENCY VISUALIZATION (HIGH IMPACT)
    # ---------------------------
    st.subheader("Decision Intelligence View")

    for _, row in result_df.iterrows():
        if row["Urgency"] == "high":
            st.error(f"URGENT: {row['Item']} → ${row['Resale Price']}")
        elif row["Urgency"] == "medium":
            st.warning(f"MEDIUM PRIORITY: {row['Item']} → ${row['Resale Price']}")
        else:
            st.info(f"LOW PRIORITY: {row['Item']} → ${row['Resale Price']}")

    st.divider()

    # ---------------------------
    # SIMULATED DEPLOYMENT LAYER
    # ---------------------------
    if st.button("Deploy to Marketplace (Simulation)"):
        st.balloons()
        st.success(f"Successfully deployed {len(result_df)} optimized listings to partner marketplaces.")
        st.info("Inventory liquidation automation pipeline activated.")