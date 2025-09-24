
import streamlit as st
import pandas as pd
import numpy as np
import io, re
import requests
from datetime import datetime
import plotly.graph_objects as go

st.set_page_config(page_title="Water Quality Trends — Monthly", layout="wide")

@st.cache_data
def load_params_from_url(url: str):
    # Read CSV bytes then parse as DataFrame
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.BytesIO(resp.content))
    def to_target(x):
        if pd.isna(x): return np.nan
        if isinstance(x,(int,float)): return float(x)
        s = str(x).strip()
        if "," in s:
            nums = []
            for p in s.split(","):
                try: nums.append(float(str(p).strip()))
                except: pass
            return max(nums) if nums else np.nan
        try: return float(s)
        except: return np.nan
    df["MaxTarget"] = df["MaxTarget"].apply(to_target)
    return df

@st.cache_data
def load_excel_from_url(url: str):
    # Use pandas engine inference for Excel
    return pd.read_excel(url)

def coerce_numeric(val):
    if pd.isna(val): return np.nan
    s = str(val).strip()
    if s == "": return np.nan
    if s.upper() in {"ND","NOT DETECTED","BDL","BD","N/D"}: return 0.0
    s = re.sub(r"[A-Za-z%/µμ]+", " ", s)
    s = s.replace("\u00A0"," ")
    s = s.replace(",","")
    s = s.replace(" ","")
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    try: return float(m.group(0)) if m else np.nan
    except: return np.nan

def month_floor(d):
    d = pd.to_datetime(d, errors="coerce")
    if pd.isna(d): return pd.NaT
    return pd.Timestamp(d.year, d.month, 1)

st.title("Water Quality Trends — Monthly Trends (Read-only)")
st.caption("Data and parameter targets load from **GitHub RAW URLs**. Uploads are disabled.")

left, right = st.columns([1,4], gap="large")

with left:
    st.subheader("Data sources (URL only)")
    gh_url = st.text_input("GitHub RAW Excel URL", value="https://raw.githubusercontent.com/francisfivaz-max/Trendline-Sample/main/data/Long%20Table%20Trendline.xlsx")
    params_url = st.text_input("GitHub RAW Parameters CSV URL", value="https://raw.githubusercontent.com/francisfivaz-max/Trendline-Sample/main/data/parameters.csv")
    refresh = st.button("Load / Refresh")

# Load params first (fail early if wrong)
try:
    params = load_params_from_url(params_url)
except Exception as e:
    st.error(f"Failed to load parameters CSV: {e}")
    st.stop()

if "raw_data" not in st.session_state or refresh:
    if gh_url:
        try:
            st.session_state["raw_data"] = load_excel_from_url(gh_url)
        except Exception as e:
            st.error(f"Could not load Excel from URL: {e}")
            st.stop()
    else:
        st.warning("Please paste a GitHub RAW Excel URL.")
        st.stop()

df = st.session_state["raw_data"]

# Standardize headers
colmap = {}
for c in df.columns:
    lc = str(c).strip().lower()
    if lc == "type": colmap[c] = "Type"
    elif "site" in lc and "id" in lc: colmap[c] = "Site ID"
    elif lc in {"site","siteid"}: colmap[c] = "Site ID"
    elif "param" in lc: colmap[c] = "Parameter"
    elif lc in {"result","value","reading"}: colmap[c] = "Result"
    elif "date" in lc or "sample" in lc: colmap[c] = "Date"
df = df.rename(columns=colmap)

required = {"Type","Site ID","Parameter","Date","Result"}
missing = required - set(df.columns)
if missing:
    st.error(f"Missing required columns: {sorted(missing)}")
    st.stop()

# Clean + enrich
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df["ResultNum"] = df["Result"].apply(coerce_numeric)
df["Month"] = df["Date"].apply(month_floor)
df = df.dropna(subset=["Month"])

# Filters
with left:
    type_options = sorted([x for x in df["Type"].dropna().unique() if str(x).strip() != ""])
    sel_type = st.selectbox("Type", type_options)
    min_m, max_m = df["Month"].min(), df["Month"].max()
    mrange = st.slider("Month range", min_value=min_m.to_pydatetime(), max_value=max_m.to_pydatetime(),
                       value=(min_m.to_pydatetime(), max_m.to_pydatetime()), format="YYYY/MM")
    param_options = sorted(df["Parameter"].dropna().unique().tolist())
    sel_param = st.selectbox("Parameter", param_options)

# Filter & aggregate
mask = (df["Type"] == sel_type) & (df["Month"] >= pd.Timestamp(mrange[0])) & (df["Month"] <= pd.Timestamp(mrange[1])) & (df["Parameter"] == sel_param)
sub = df.loc[mask].copy().sort_values(["Site ID","Month","Date"])
idx = sub.groupby(["Site ID","Month"])["Date"].transform("idxmax")
try:
    last_rows = sub.loc[idx.dropna().astype(int)]
except Exception:
    last_rows = sub

pivot = last_rows.pivot_table(index="Month", columns="Site ID", values="ResultNum", aggfunc="last").sort_index()

# Target
row = params.loc[params["Parameter"].str.strip().str.lower() == str(sel_param).strip().lower()]
target = row["MaxTarget"].iloc[0] if len(row) else np.nan

with right:
    st.subheader(f"{sel_param} — {sel_type}")
    fig = go.Figure()
    for col in pivot.columns:
        fig.add_trace(go.Scatter(x=pivot.index, y=pivot[col], mode="lines+markers", name=str(col)))
    if pd.notna(target):
        fig.add_hline(y=float(target), line_color="red", line_width=2,
                      annotation_text=f"Target {target}", annotation_position="top left")
    fig.update_layout(height=520, margin=dict(l=40,r=10,t=10,b=40),
                      legend=dict(orientation="v", y=0.5, x=1.02),
                      xaxis_title="Month (last test per month)", yaxis_title=str(sel_param))
    st.plotly_chart(fig, use_container_width=True)

    st.caption("Monthly trend (last test per month). Target line shows the max target and remains visible even when no data is present.")
