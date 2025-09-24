
import streamlit as st
import pandas as pd
import numpy as np
import io, re, requests
import plotly.graph_objects as go

st.set_page_config(page_title="Water Quality Trends — Monthly", layout="wide")

def get_url(section, key):
    try:
        return st.secrets[section][key]
    except Exception:
        st.error(f"Missing secret [{section}]['{key}'].")
        st.stop()

EXCEL_URL  = get_url("urls", "excel")
PARAMS_URL = get_url("urls", "parameters")

@st.cache_data
def load_params_from_url(url: str):
    r = requests.get(url, timeout=30); r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content))
    def to_target(x):
        if pd.isna(x): return np.nan
        if isinstance(x, (int, float)): return float(x)
        s = str(x).strip()
        if "," in s:
            vals = []
            for p in s.split(","):
                try: vals.append(float(str(p).strip()))
                except: pass
            return max(vals) if vals else np.nan
        try: return float(s)
        except: return np.nan
    if "MaxTarget" not in df.columns or "Parameter" not in df.columns:
        raise ValueError("parameters.csv must have columns: Parameter, MaxTarget")
    df["MaxTarget"] = df["MaxTarget"].apply(to_target)
    return df

@st.cache_data
def load_excel_from_url(url: str):
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
st.caption("Data and parameter targets load from Streamlit **secrets** (GitHub RAW URLs). Uploads & URL inputs are disabled.")

with st.sidebar:
    st.header("Data")
    st.text("URLs are stored in secrets.")
    refresh = st.button("Refresh data")

params = load_params_from_url(PARAMS_URL)

if "raw_data" not in st.session_state or refresh:
    try:
        st.session_state["raw_data"] = load_excel_from_url(EXCEL_URL)
    except Exception as e:
        st.error(f"Could not load Excel from URL: {e}")
        st.stop()

df = st.session_state["raw_data"].copy()
df.columns = df.columns.map(str).str.strip()

# ---- Standardize headers ----
colmap = {}
for c in df.columns:
    lc = str(c).strip().lower()
    if lc == "type": colmap[c] = "Type"
    elif "site" in lc and "id" in lc: colmap[c] = "Site ID"
    elif lc in {"site","siteid"}: colmap[c] = "Site ID"
    elif "param" in lc: colmap[c] = "Parameter"
    elif lc in {"result","results","result value","value","reading"} or "result" in lc: colmap[c] = "Result"
    elif "date" in lc or "sample" in lc: colmap[c] = "Date"
df = df.rename(columns=colmap)

required_base = {"Type","Site ID","Parameter","Result"}
missing_base = required_base - set(df.columns)
if missing_base:
    st.error(f"Missing required columns: {sorted(missing_base)}")
    st.stop()

# ---- Build a Date column robustly, even with duplicate-named columns ----
date_like_idx = [i for i, c in enumerate(df.columns) if ("date" in c.lower()) or ("sample" in c.lower())]
if not date_like_idx:
    st.error("Could not find any date-like column. Please ensure your data has a Date column.")
    st.stop()

parsed = []
for i in date_like_idx:
    s = pd.to_datetime(df.iloc[:, i], errors="coerce")
    parsed.append(s)
date_block = pd.concat(parsed, axis=1)
df["Date"] = date_block.bfill(axis=1).iloc[:, 0]

# ---- Clean + enrich ----
df["ResultNum"] = df["Result"].apply(coerce_numeric)
df["Month"] = df["Date"].apply(month_floor)
df = df.dropna(subset=["Month"])

# ---- Filters ----
left, right = st.columns([1,4], gap="large")
with left:
    type_options = sorted([x for x in df["Type"].dropna().unique() if str(x).strip() != ""])
    sel_type = st.selectbox("Type", type_options)
    min_m, max_m = df["Month"].min(), df["Month"].max()
    mrange = st.slider("Month range", min_value=min_m.to_pydatetime(), max_value=max_m.to_pydatetime(),
                       value=(min_m.to_pydatetime(), max_m.to_pydatetime()), format="YYYY/MM")
    param_options = sorted(df["Parameter"].dropna().unique().tolist())
    sel_param = st.selectbox("Parameter", param_options)

# ---- Filter & aggregate ----
mask = (df["Type"] == sel_type) & (df["Month"] >= pd.Timestamp(mrange[0])) & (df["Month"] <= pd.Timestamp(mrange[1])) & (df["Parameter"] == sel_param)
sub = df.loc[mask].copy().sort_values(["Site ID","Month","Date"])
idx = sub.groupby(["Site ID","Month"])["Date"].transform("idxmax")
try:
    last_rows = sub.loc[idx.dropna().astype(int)]
except Exception:
    last_rows = sub

pivot = last_rows.pivot_table(index="Month", columns="Site ID", values="ResultNum", aggfunc="last").sort_index()

# ---- Target line ----
row = params.loc[params["Parameter"].str.strip().str.lower() == str(sel_param).strip().lower()]
target = row["MaxTarget"].iloc[0] if len(row) else np.nan

with right:
    st.subheader(f"{sel_param} — {sel_type}")
    fig = go.Figure()
    for col in pivot.columns:
        fig.add_trace(go.Scatter(x=pivot.index, y=pivot[col], mode="lines+markers", name=str(col)))
    if pd.notna(target):
        fig.add_hline(y=float(target), line_color="red", line_width=2, annotation_text=f"Target {target}", annotation_position="top left")
    fig.update_layout(height=520, margin=dict(l=40,r=10,t=10,b=40),
                      legend=dict(orientation="v", y=0.5, x=1.02),
                      xaxis_title="Month (last test per month)", yaxis_title=str(sel_param))
    st.plotly_chart(fig, use_container_width=True)

    st.caption("Monthly trend (last test per month). Target line shows the max target and remains visible even when no data is present.")
