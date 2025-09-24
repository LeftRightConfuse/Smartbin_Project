import streamlit as st
import pandas as pd
import altair as alt
from pymongo import MongoClient
from datetime import datetime
from urllib.parse import quote_plus

# -------------------- CONFIG --------------------
st.set_page_config(page_title="Smartbin Dashboard (MongoDB)", layout="wide")

st.markdown("""
    <style>
        body { background-color: #f0fdf4; }
        .main { background-color: #ffffff; border-radius: 10px; padding: 20px; }
        h1, h2, h3 { color: #1a7f4d; }
        .stDataFrame { background-color: #ffffff; }
    </style>
""", unsafe_allow_html=True)

# -------------------- MongoDB Connection --------------------
# -------------------- MongoDB Connection --------------------
# อ่านค่าจาก Secrets และประกอบ URI โดย encode รหัสผ่านให้อัตโนมัติ
user = st.secrets["MONGO_USER"]                 # ชื่อผู้ใช้ Atlas
pwd  = quote_plus(st.secrets["MONGO_PASS"])     # encode อักขระพิเศษอัตโนมัติ
host = st.secrets["MONGO_CLUSTER"]              # เช่น cluster0.kfioeaq.mongodb.net
dbnm = st.secrets.get("MONGO_DB", "smart_bin")  # ชื่อ DB

MONGO_URI = (
    f"mongodb+srv://{user}:{pwd}@{host}/{dbnm}"
    "?retryWrites=true&w=majority&appName=SmartbinApp&authSource=admin"
)

@st.cache_resource
def get_client():
    c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # เช็กว่าเชื่อมต่อและ auth ได้จริง (จะ throw ถ้า IP/รหัส/URI ผิด)
    c.admin.command("ping")
    return c

client = get_client()
db = client[dbnm]
users_col = db["users"]
waste_col = db["waste"]


st.title("♻️ Smartbin Dashboard (MongoDB Atlas)")

# -------------------- Helper --------------------
def cursor_to_df(cursor):
    df = pd.DataFrame(list(cursor))
    if not df.empty and "_id" in df.columns:
        df["_id"] = df["_id"].astype(str)
    return df

# -------------------- Users Leaderboard --------------------
st.subheader("🏆 Total Points by User")

users_df = cursor_to_df(users_col.find({}, {"_id": 0, "user_id": 1, "name": 1, "points": 1}))
if users_df.empty:
    users_df = pd.DataFrame(columns=["user_id", "name", "points"])

users_df["points"] = pd.to_numeric(users_df.get("points"), errors="coerce").fillna(0).astype(int)

chart_df = (users_df
            .rename(columns={"name": "User", "points": "Points"})
            .sort_values("Points", ascending=False)
            .reset_index(drop=True))

icons = {0: "👑", 1: "🥈", 2: "🥉"}
chart_df["Icon"] = chart_df.index.map(lambda i: icons.get(i, ""))

base_chart = alt.Chart(chart_df).mark_bar().encode(
    x=alt.X("User:N", sort=None, title="User"),
    y=alt.Y("Points:Q", title="Points"),
    color=alt.Color("User:N", scale=alt.Scale(scheme="greens"), legend=None)
)

icon_layer = alt.Chart(chart_df[chart_df["Icon"] != ""]).mark_text(size=50, dy=-10).encode(
    x="User:N", y="Points:Q", text="Icon:N"
)

st.altair_chart((base_chart + icon_layer).properties(width='container'), use_container_width=True)
st.subheader("👤 Users Table")
st.dataframe(chart_df[["User", "Points"]], use_container_width=True)

# -------------------- Aggregation Example --------------------
with st.expander("คำนวณแต้มจาก waste (Aggregation)"):
    pipe_points = [
        {"$group": {"_id": "$user_id", "total_points": {"$sum": "$points_earned"}}},
        {"$lookup": {
            "from": "users",
            "localField": "_id",
            "foreignField": "user_id",
            "as": "user"
        }},
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
        {"$project": {"user_id": "$_id", "_id": 0, "name": "$user.name", "total_points": 1}}
    ]
    agg_df = pd.DataFrame(list(waste_col.aggregate(pipe_points)))
    if not agg_df.empty:
        agg_df = agg_df.fillna({"name": "(unknown)"}).sort_values("total_points", ascending=False)
    st.dataframe(agg_df, use_container_width=True)

# -------------------- Waste Type Distribution --------------------
st.subheader("🗑️ Waste Type Distribution")

pipe_pie = [
    {"$group": {"_id": "$waste_type", "TotalAmount": {"$sum": "$weight"}}},
    {"$project": {"Waste": "$_id", "_id": 0, "TotalAmount": 1}}
]
pie_df = pd.DataFrame(list(waste_col.aggregate(pipe_pie)))
if pie_df.empty:
    pie_df = pd.DataFrame({"Waste": [], "TotalAmount": []})

total_sum = float(pie_df["TotalAmount"].sum()) if not pie_df.empty else 0.0
pie_df["PercentText"] = ("0.0%" if total_sum == 0
                         else (pie_df["TotalAmount"] / max(total_sum, 1e-9) * 100).round(1).astype(str) + "%")

col1, col2 = st.columns([2, 1])
with col1:
    pie = alt.Chart(pie_df).mark_arc().encode(
        theta=alt.Theta("TotalAmount:Q", stack=True),
        color=alt.Color("Waste:N", scale=alt.Scale(scheme="greens")),
        tooltip=[alt.Tooltip("Waste:N"), alt.Tooltip("TotalAmount:Q", format=",.2f")]
    ).properties(width='container')
    st.altair_chart(pie, use_container_width=True)
with col2:
    st.write("### 📊 % by Type")
    st.table(pie_df[["Waste", "PercentText"]])

# -------------------- Raw Waste Log --------------------
st.subheader("📋 Waste Log (latest first)")
raw_df = cursor_to_df(
    waste_col.find({}, {"_id": 1, "record_id": 1, "user_id": 1, "waste_type": 1, "weight": 1, "points_earned": 1, "timestamp": 1})
             .sort("timestamp", -1)
)
st.dataframe(raw_df, use_container_width=True)
