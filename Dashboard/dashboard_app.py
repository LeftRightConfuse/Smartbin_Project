import streamlit as st
import pandas as pd
import altair as alt
from pymongo import MongoClient
from datetime import datetime
from urllib.parse import quote_plus

st.set_page_config(page_title="Smartbin Dashboard (MongoDB)", layout="wide")

st.markdown("""
    <style>
        body { background-color: #f0fdf4; }
        .main { background-color: #ffffff; border-radius: 10px; padding: 20px; }
        h1, h2, h3 { color: #1a7f4d; }
        .stDataFrame { background-color: #ffffff; }
    </style>
""", unsafe_allow_html=True)

user = st.secrets["MONGO_USER"]
pwd  = quote_plus(st.secrets["MONGO_PASS"])
host = st.secrets["MONGO_CLUSTER"]
dbnm = st.secrets.get("MONGO_DB", "smartbin")

MONGO_URI = (
    f"mongodb+srv://{user}:{pwd}@{host}/{dbnm}"
    "?retryWrites=true&w=majority&appName=SmartbinApp&authSource=admin"
)

@st.cache_resource
def get_client():
    c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    c.admin.command("ping")
    return c

client = get_client()
db = client[dbnm]

points_col = db["points"]
daily_col  = db["daily_waste"]

st.title("♻️ Smartbin Dashboard (MongoDB Atlas / smartbin)")

def load_points_df():
    docs = list(points_col.find({}))
    rows = []
    if not docs:
        return pd.DataFrame(columns=["user_id", "name", "points", "ts"])
    time_keys = ["timestamp", "updated_at", "updatedAt", "created_at", "createdAt", "ts", "time", "date"]
    doc0 = docs[0]
    looks_like_per_user = ("name" in doc0 and "points" in doc0) or ("user_id" in doc0)
    if looks_like_per_user:
        for d in docs:
            user_id = d.get("user_id") or d.get("_id")
            name    = d.get("name") or str(user_id)
            points  = d.get("points", 0)
            ts_val = None
            for k in time_keys:
                if d.get(k) is not None:
                    ts_val = d.get(k); break
            rows.append({"user_id": str(user_id), "name": name, "points": points, "ts": ts_val})
    else:
        for d in docs:
            parent_ts = None
            for k in time_keys:
                if d.get(k) is not None:
                    parent_ts = d.get(k); break
            candidates = d.get("data", d)
            if isinstance(candidates, dict):
                for k, v in candidates.items():
                    if k == "_id":
                        continue
                    if isinstance(v, dict) and ("points" in v or "name" in v):
                        ts_val = None
                        for tkey in time_keys:
                            if v.get(tkey) is not None:
                                ts_val = v.get(tkey); break
                        if ts_val is None:
                            ts_val = parent_ts
                        rows.append({
                            "user_id": str(k),
                            "name": v.get("name", str(k)),
                            "points": v.get("points", 0),
                            "ts": ts_val
                        })
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["user_id", "name", "points", "ts"])
    df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0).astype(int)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    return df

def load_daily_waste_flat():
    docs = list(daily_col.find({}).sort("timestamp", -1))
    rows = []
    for d in docs:
        data = d.get("data", {}) or {}
        for day_str, obj in data.items():
            rows.append({
                "date": day_str,
                "aluminium_can": float(obj.get("aluminium_can", 0) or 0),
                "plastic_bottle": float(obj.get("plastic_bottle", 0) or 0),
                "total": float(obj.get("total", 0) or 0),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        try:
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return df

st.subheader("🏆 Total Points by User (from smartbin.points)")

users_df = load_points_df()
if not users_df.empty:
    key_col = "user_id"
    if users_df["ts"].notna().any():
        users_df = (users_df
                    .sort_values([key_col, "ts"], ascending=[True, False])
                    .groupby(key_col, as_index=False)
                    .first())
    else:
        users_df = (users_df
                    .sort_values([key_col, "points"], ascending=[True, False])
                    .groupby(key_col, as_index=False)
                    .first())

users_df = users_df[~users_df["name"].fillna("").str.strip().str.lower().eq("alice")]

chart_df = (users_df
            .rename(columns={"name": "User", "points": "Points"})
            .sort_values("Points", ascending=False)
            .reset_index(drop=True))

def badge_for_rank(i: int) -> str:
    if i == 0: return "👑"
    if i == 1: return "🥈"
    if i == 2: return "🥉"
    return ""

chart_df["Rank"]  = chart_df.index + 1
chart_df["Badge"] = chart_df.index.map(badge_for_rank)

bars = alt.Chart(chart_df).mark_bar(
    cornerRadiusTopLeft=6, cornerRadiusTopRight=6
).encode(
    x=alt.X("User:N", sort=None, title="User"),
    y=alt.Y("Points:Q", title="Points"),
    color=alt.value("#16a34a"),
    tooltip=[alt.Tooltip("User:N"), alt.Tooltip("Points:Q", format=",.0f")]
).properties(height=420)

labels = alt.Chart(chart_df).mark_text(
    dy=-8,
    fontWeight=600
).encode(
    x="User:N",
    y="Points:Q",
    text=alt.Text("Points:Q", format=",.0f")
)

badges = alt.Chart(chart_df[chart_df["Badge"] != ""]).mark_text(
    size=44, dy=-28
).encode(
    x="User:N",
    y="Points:Q",
    text="Badge:N"
)

st.altair_chart((bars + labels + badges).properties(width='container'), use_container_width=True)

st.subheader("👤 Users latest points")
st.dataframe(chart_df[["User", "Points"]], use_container_width=True, hide_index=True)

st.subheader("🗑️ Waste Type Distribution (from smartbin.daily_waste)")
dw_df = load_daily_waste_flat()

if not dw_df.empty:
    pie_df = pd.DataFrame({
        "Waste": ["aluminium_can", "plastic_bottle"],
        "TotalAmount": [
            dw_df["aluminium_can"].sum(),
            dw_df["plastic_bottle"].sum()
        ]
    })
else:
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

st.subheader("📋 Daily Waste")
dw_view = dw_df.copy()
if not dw_view.empty and "date" in dw_view.columns:
    dw_view["date"] = pd.to_datetime(dw_view["date"], errors="coerce")
    dw_view = dw_view.sort_values("date", ascending=False)
    dw_view["date"] = dw_view["date"].dt.strftime("%Y-%m-%d")
st.dataframe(dw_view, use_container_width=True, hide_index=True)
