import streamlit as st
import pandas as pd
import psycopg2
import altair as alt

DB_HOST     = "10.183.236.52"
DB_PORT     = 5432
DB_NAME     = "smartbin"
DB_USER     = "postgres"
DB_PASSWORD = "dG8tclqynj"

st.set_page_config(page_title="Smartbin Dashboard", layout="wide")

st.markdown("""
    <style>
        body { background-color: #f0fdf4; }
        .main { background-color: #ffffff; border-radius: 10px; padding: 20px; }
        h1, h2, h3 { color: #1a7f4d; }
        .stDataFrame { background-color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data(query):
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

st.title("♻️ Smartbin Dashboard")

st.subheader("🏆 Total Points by User")
chart_df = load_data("SELECT * FROM users")
chart_df = chart_df.rename(columns={"name": "User","total_points": "Points"})
chart_df = chart_df.sort_values(by="Points", ascending=False).reset_index(drop=True)
icons = {0: "👑", 1: "🥈", 2: "🥉"}
chart_df["Icon"] = chart_df.index.map(lambda i: icons.get(i, ""))

base_chart = alt.Chart(chart_df).mark_bar(color="#7fc97f").encode(
    x=alt.X("User", sort=None),
    y="Points"
)

icon_layer = alt.Chart(chart_df[chart_df["Icon"] != ""]).mark_text(
    size=50,
    dy=-10
).encode(
    x="User",
    y="Points",
    text="Icon"
)

st.altair_chart(base_chart + icon_layer, use_container_width=True)

st.subheader("👤 Users Table")
st.dataframe(chart_df[["User","Points"]])

st.subheader("🗑️ Waste Type Distribution")
df_log = load_data("SELECT * FROM waste_log ORDER BY timestamp DESC")
pie_df = df_log.groupby("waste_type")["amount"].sum().reset_index()
pie_df = pie_df.rename(columns={"amount": "TotalAmount", "waste_type": "Waste"})
total_sum = pie_df["TotalAmount"].sum()
pie_df["PercentText"] = (pie_df["TotalAmount"] / total_sum * 100).round(1).astype(str) + "%"

col1, col2 = st.columns([2,1])

with col1:
    pie = alt.Chart(pie_df).mark_arc().encode(
        theta="TotalAmount",
        color=alt.Color("Waste", scale=alt.Scale(scheme="greens")),
        tooltip=["Waste", "TotalAmount"]
    )
    st.altair_chart(pie, use_container_width=True)

with col2:
    st.write("### 📊 % by Type")
    st.table(pie_df[["Waste","PercentText"]])

st.subheader("📋 Waste Log")
st.dataframe(df_log)
