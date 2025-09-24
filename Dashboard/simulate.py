from pymongo import MongoClient
import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

MONGO_URI = st.secrets["MONGO_URI"]

# สร้าง client
client = MongoClient(MONGO_URI)

db = client["smart_bin"]
users_col = db["users"]
waste_col = db["waste"]

# ทดสอบอ่าน users
users = list(users_col.find())
st.write(users)
