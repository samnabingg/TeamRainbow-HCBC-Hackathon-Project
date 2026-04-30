import streamlit as st
import pandas as pd
from agent import process_item

st.title("Eco-Arbitrage Dashboard")

df = pd.read_csv("src/data.csv")

st.subheader("Inventory")
st.dataframe(df)

overstock = df[df["Days in Warehouse"] > 90]

if st.button("Run AI Analysis"):
    results = []

    for _, row in overstock.iterrows():
        ai_result = process_item(row)

        profit = ai_result["resale_price"] - row["Original Price"]

        results.append({
            "Item": row["Item Name"],
            "Urgency": ai_result["urgency"],
            "Resale Price": ai_result["resale_price"],
            "Recovered Value": profit,
            "Description": ai_result["description"]
        })

    result_df = pd.DataFrame(results)

    st.subheader("AI Results")
    st.dataframe(result_df)

    st.success("Processing complete")

    if st.button("Auto-Post Listings"):
        st.success("Listings pushed to marketplace (simulated)")