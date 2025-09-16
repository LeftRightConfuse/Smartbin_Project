import streamlit as st
import pandas as pd
import psycopg2
import altair as alt

DB_HOST     = "192.168.11.154"
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

@st.cache_data(ttl=30)
def load_data(query: str) -> pd.DataFrame:
    with psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    ) as conn:
        df = pd.read_sql_query(query, conn)
    return df

st.title("♻️ Smartbin Dashboard")

# -------------------- Users (Bar + Icons) --------------------
st.subheader("🏆 Total Points by User")
chart_df = load_data("SELECT * FROM users")

# บังคับชนิดข้อมูลป้องกันกรณีอ่านมาเป็น object/string
chart_df["total_points"] = pd.to_numeric(chart_df.get("total_points"), errors="coerce").fillna(0).astype(int)
chart_df["name"] = chart_df.get("name").astype(str)

chart_df = chart_df.rename(columns={"name": "User", "total_points": "Points"})
chart_df = chart_df.sort_values(by="Points", ascending=False).reset_index(drop=True)

icons = {0: "👑", 1: "🥈", 2: "🥉"}
chart_df["Icon"] = chart_df.index.map(lambda i: icons.get(i, ""))

base_chart = alt.Chart(chart_df).mark_bar(color="#7fc97f").encode(
    x=alt.X("User:N", sort=None, title="User"),
    y=alt.Y("Points:Q", title="Points")
)

icon_layer = alt.Chart(chart_df[chart_df["Icon"] != ""]).mark_text(
    size=50, dy=-10
).encode(
    x="User:N",
    y="Points:Q",
    text="Icon:N"
)

st.altair_chart(base_chart + icon_layer, use_container_width=True)

st.subheader("👤 Users Table")
st.dataframe(chart_df[["User", "Points"]], use_container_width=True)

# -------------------- Waste Type Distribution (Pie) --------------------
st.subheader("🗑️ Waste Type Distribution")

df_log = load_data("SELECT * FROM waste_log ORDER BY timestamp DESC")

# บังคับ amount เป็นตัวเลขก่อน
df_log["amount"] = pd.to_numeric(df_log.get("amount"), errors="coerce").fillna(0)
df_log["waste_type"] = df_log.get("waste_type").astype(str)

pie_df = (
    df_log.groupby("waste_type", as_index=False)["amount"].sum()
          .rename(columns={"amount": "TotalAmount", "waste_type": "Waste"})
)

# กันหารศูนย์ (กรณีไม่มีข้อมูล)
total_sum = float(pie_df["TotalAmount"].sum())
if total_sum == 0:
    pie_df["PercentText"] = "0.0%"
else:
    pie_df["PercentText"] = (pie_df["TotalAmount"] / total_sum * 100).round(1).astype(str) + "%"

col1, col2 = st.columns([2, 1])

with col1:
    pie = alt.Chart(pie_df).mark_arc().encode(
        theta=alt.Theta("TotalAmount:Q", stack=True),
        color=alt.Color("Waste:N", scale=alt.Scale(scheme="greens")),
        tooltip=[alt.Tooltip("Waste:N"), alt.Tooltip("TotalAmount:Q", format=",.2f")]
    )
    st.altair_chart(pie, use_container_width=True)

with col2:
    st.write("### 📊 % by Type")
    st.table(pie_df[["Waste", "PercentText"]])

# -------------------- Raw Log Table --------------------
st.subheader("📋 Waste Log")
st.dataframe(df_log, use_container_width=True)
