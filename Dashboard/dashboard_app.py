import streamlit as st
import pandas as pd
import altair as alt
from pymongo import MongoClient
from datetime import datetime, timezone
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
    time_keys = ["timestamp", "updated_at", "updatedAt", "created_at", "createdAt", "ts", "time", "date"]
    for d in docs:
        parent_ts = None
        for k in time_keys:
            if d.get(k) is not None:
                parent_ts = d.get(k)
                break
        data = d.get("data", {}) or {}
        for day_str, obj in data.items():
            rows.append({
                "date": day_str,
                "aluminium_can": float(obj.get("aluminium_can", 0) or 0),
                "plastic_bottle": float(obj.get("plastic_bottle", 0) or 0),
                "total": float(obj.get("total", 0) or 0),
                "ts": parent_ts,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    if df["ts"].notna().any():
        idx = df.groupby("date")["ts"].idxmax()
        df = df.loc[idx]
    else:
        df = df.drop_duplicates(subset=["date"], keep="first")
    df = df.sort_values("date", ascending=False).reset_index(drop=True)
    df["date"] = df["date"].astype(str)
    return df.drop(columns=["ts"], errors="ignore")

@st.cache_data(ttl=30)
def get_users_df_cached():
    return load_points_df()

@st.cache_data(ttl=30)
def get_daily_df_cached():
    return load_daily_waste_flat()

left, mid, right = st.columns([1,1,1])
with left:
    dark = st.toggle("Dark mode", value=False)
with mid:
    if st.button("🔄 Refresh data"):
        st.rerun()
with right:
    pass

users_df = get_users_df_cached()
if not users_df.empty:
    key_col = "user_id"
    if users_df["ts"].notna().any():
        users_df = (users_df.sort_values([key_col, "ts"], ascending=[True, False]).groupby(key_col, as_index=False).first())
    else:
        users_df = (users_df.sort_values([key_col, "points"], ascending=[True, False]).groupby(key_col, as_index=False).first())

users_df = users_df[~users_df["name"].fillna("").str.strip().str.lower().eq("alice")]

chart_df = (users_df.rename(columns={"name": "User", "points": "Points"}).sort_values("Points", ascending=False).reset_index(drop=True))

last_ts = users_df["ts"].max() if ("ts" in users_df and not users_df.empty) else None
c1, c2, c3 = st.columns(3)
with c1: st.metric("Total Users", len(users_df))
with c2: st.metric("Total Points", int(chart_df["Points"].sum()) if not chart_df.empty else 0)
with c3: st.metric("Last Update", last_ts.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(last_ts) else "-")

chart_color = "#14b8a6" if dark else "#16a34a"
scheme_name = "tealblues" if dark else "greens"

st.subheader("🏅 Leaderboard")
top_n = st.slider("Top N users", 3, max(3, len(chart_df)) if len(chart_df) >= 3 else 3, min(5, len(chart_df)) if len(chart_df) >= 5 else len(chart_df))
orient = st.radio("Chart orientation", ["Vertical", "Horizontal"], horizontal=True, index=0)

def badge_for_rank(i: int) -> str:
    if i == 0: return "👑"
    if i == 1: return "🥈"
    if i == 2: return "🥉"
    return ""

chart_df["Rank"]  = chart_df.index + 1
chart_df["Badge"] = chart_df.index.map(badge_for_rank)
chart_df_top = chart_df.head(top_n)

if orient == "Vertical":
    bars = alt.Chart(chart_df_top).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
        x=alt.X("User:N", sort=None, title="User"),
        y=alt.Y("Points:Q", title="Points"),
        color=alt.value(chart_color),
        tooltip=[alt.Tooltip("User:N"), alt.Tooltip("Points:Q", format=",.0f")]
    ).properties(height=420)
    badges = alt.Chart(chart_df_top[chart_df_top["Badge"] != ""]).mark_text(size=44, dy=-28).encode(
        x="User:N", y="Points:Q", text="Badge:N"
    )
else:
    bars = alt.Chart(chart_df_top).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
        y=alt.Y("User:N", sort="-x", title="User"),
        x=alt.X("Points:Q", title="Points"),
        color=alt.value(chart_color),
        tooltip=[alt.Tooltip("User:N"), alt.Tooltip("Points:Q", format=",.0f")]
    ).properties(height=420)
    badges = alt.Chart(chart_df_top[chart_df_top["Badge"] != ""]).mark_text(size=44, dx=18).encode(
        y="User:N", x="Points:Q", text="Badge:N"
    )

st.altair_chart((bars + badges).properties(width='container'), use_container_width=True)

st.subheader("👤 Users latest points")
st.dataframe(chart_df[["User", "Points"]], use_container_width=True, hide_index=True)

st.download_button("⬇️ Download Users CSV",
                   data=users_df.to_csv(index=False).encode("utf-8"),
                   file_name="users_points.csv",
                   mime="text/csv")

st.subheader("🗑️ Waste Type Distribution (from smartbin.daily_waste)")
dw_all = get_daily_df_cached()
if not dw_all.empty:
    min_d, max_d = pd.to_datetime(dw_all["date"]).min(), pd.to_datetime(dw_all["date"]).max()
    d1, d2 = st.date_input("เลือกช่วงวันที่", (min_d.date(), max_d.date()))
    if isinstance(d1, tuple):
        d1, d2 = d1
    mask = (pd.to_datetime(dw_all["date"]) >= pd.to_datetime(d1)) & (pd.to_datetime(dw_all["date"]) <= pd.to_datetime(d2))
    dw_df = dw_all.loc[mask].reset_index(drop=True)
else:
    dw_df = dw_all

if not dw_df.empty:
    pie_df = pd.DataFrame({
        "Waste": ["aluminium_can", "plastic_bottle"],
        "TotalAmount": [dw_df["aluminium_can"].sum(), dw_df["plastic_bottle"].sum()]
    })
else:
    pie_df = pd.DataFrame({"Waste": [], "TotalAmount": []})

total_sum = float(pie_df["TotalAmount"].sum()) if not pie_df.empty else 0.0
pie_df["Percent"] = 0.0 if total_sum == 0 else (pie_df["TotalAmount"] / max(total_sum, 1e-9) * 100)
pie_df["PercentText"] = pie_df["Percent"].round(1).astype(str) + "%"
pie_df["Label"] = pie_df.apply(lambda r: f'{int(r["TotalAmount"]):,} ({r["Percent"]:.1f}%)', axis=1)

col1, col2 = st.columns([2, 1])
with col1:
    base = alt.Chart(pie_df).encode(
        theta=alt.Theta("TotalAmount:Q", stack=True),
        color=alt.Color("Waste:N", scale=alt.Scale(scheme=scheme_name))
    )
    pie = base.mark_arc(innerRadius=60)
    text = base.mark_text(radius=135, size=13).encode(text="Label:N")
    st.altair_chart((pie + text).properties(width='container'), use_container_width=True)

with col2:
    st.write("### 📊 % by Type")
    table_df = pie_df.copy()
    table_df["Total"] = table_df["TotalAmount"].astype(int).map(lambda x: f"{x:,}")
    st.table(table_df[["Waste", "Total", "PercentText"]])

st.subheader("📈 Daily Trend")
if not dw_df.empty:
    trend_df = dw_df.melt(id_vars=["date"], value_vars=["aluminium_can","plastic_bottle"], var_name="Type", value_name="Amount")
    line = alt.Chart(trend_df).mark_line(point=True).encode(
        x=alt.X("date:T", title="Date"),
        y=alt.Y("Amount:Q"),
        color=alt.Color("Type:N", title="Waste Type"),
        tooltip=["date:T","Type:N","Amount:Q"]
    ).properties(height=360)
    st.altair_chart(line.properties(width='container'), use_container_width=True)

st.subheader("📋 Daily Waste")
dw_view = dw_df.copy()
st.dataframe(dw_view, use_container_width=True, hide_index=True)

if not dw_view.empty:
    st.download_button("⬇️ Download Daily Waste CSV",
                       data=dw_view.to_csv(index=False).encode("utf-8"),
                       file_name="daily_waste.csv",
                       mime="text/csv")
