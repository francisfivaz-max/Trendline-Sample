
import streamlit as st
import pandas as pd
import numpy as np
import io, re, requests
import plotly.graph_objects as go

st.set_page_config(page_title="Water Quality Trends — Monthly", layout="wide", initial_sidebar_state="expanded")

def get_url(section, key):
    try:
        return st.secrets[section][key]
    except Exception:
        st.error(f"Missing secret [{section}]['{key}'].")
        st.stop()

EXCEL_URL  = get_url("urls", "excel")
PARAMS_URL = get_url("urls", "parameters")

SAFE_COLORWAY = ["#1f77b4", "#2ca02c", "#17becf", "#9467bd", "#7f7f7f",
                 "#8c564b", "#bcbd22", "#aec7e8", "#98df8a", "#9edae5"]

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

# ---------- UI (minimal) ----------
st.title("Water Quality Trends — Monthly Trends (Read-only)")

with st.sidebar:
    st.header("Data")
    refresh = st.button("Refresh data")

params = load_params_from_url(PARAMS_URL)

if "raw_data" not in st.session_state or refresh:
    try:
        st.session_state["raw_data"] = load_excel_from_url(EXCEL_URL)
    except Exception as e:
        st.error(f"Could not load Excel from URL: {e}")
        st.stop()

df = st.session_state["raw_data"].copy()

# --- Make column labels unique (Date, Date.1, ...) ---
def make_unique(cols):
    seen = {}
    out = []
    for c in cols:
        key = str(c)
        if key not in seen:
            seen[key] = 0; out.append(key)
        else:
            seen[key] += 1; out.append(f"{key}.{seen[key]}")
    return out
df.columns = make_unique(df.columns)

# ---- Standardize headers (first occurrence only) ----
standard = {}
for c in df.columns:
    lc = c.lower().strip()
    if lc == "type" and "Type" not in standard.values(): standard[c] = "Type"
    elif ("site" in lc and "id" in lc) and ("Site ID" not in standard.values()): standard[c] = "Site ID"
    elif lc in {"site","siteid"} and ("Site ID" not in standard.values()): standard[c] = "Site ID"
    elif "param" in lc and ("Parameter" not in standard.values()): standard[c] = "Parameter"
    elif (lc in {"result","results","result value","value","reading"} or "result" in lc) and ("Result" not in standard.values()): standard[c] = "Result"
df = df.rename(columns=standard)

required_base = {"Type","Site ID","Parameter","Result"}
missing_base = required_base - set(df.columns)
if missing_base:
    st.error(f"Missing required columns: {sorted(missing_base)}")
    st.stop()

# ---- Build Date purely by index from all date-like columns ----
date_like_idx = [i for i, c in enumerate(df.columns) if ("date" in c.lower()) or ("sample" in c.lower())]
if not date_like_idx:
    st.error("Could not find any date-like column. Please ensure your data has a Date column.")
    st.stop()
parsed = [pd.to_datetime(df.iloc[:, i], errors="coerce") for i in date_like_idx]
date_block = pd.concat(parsed, axis=1)
df["Date"] = date_block.bfill(axis=1).iloc[:, 0]

# Vectorized month floor
df["Month"] = df["Date"].dt.to_period("M").dt.to_timestamp()
if df["Month"].isna().all():
    st.error("All Month values are NaT. Please verify your date columns contain valid dates.")
    st.stop()

# ---- Clean + enrich ----
df["ResultNum"] = df["Result"].apply(coerce_numeric)
df = df.dropna(subset=["Month"])

# ---- Sidebar filters under Refresh (in collapsible expander) ----
with st.sidebar:
    with st.expander("Filters", expanded=True):
        type_options = sorted([x for x in df["Type"].dropna().unique() if str(x).strip() != ""])
        sel_type = st.selectbox("Type", type_options)

        # Calendar-style date range
        min_date, max_date = df["Date"].min().date(), df["Date"].max().date()
        date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

        # Allow both tuple and single-date cases gracefully
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        else:
            start_date = pd.to_datetime(date_range)
            end_date = pd.to_datetime(date_range)

        param_options = sorted(df["Parameter"].dropna().unique().tolist())
        sel_param = st.selectbox("Parameter", param_options)

# ---- Filter & aggregate ----
mask = (
    (df["Type"] == sel_type) &
    (df["Date"] >= start_date) & (df["Date"] <= end_date) &
    (df["Parameter"] == sel_param)
)
sub = df.loc[mask].copy()
sub_valid = sub.dropna(subset=["Date"]).copy()

if len(sub_valid):
    last_idx = sub_valid.groupby(["Site ID","Month"])["Date"].idxmax()
    last_rows = sub_valid.loc[last_idx].sort_values(["Site ID","Month","Date"])
else:
    last_rows = sub_valid

# ---- Pivot for chart ----
pivot = last_rows.pivot_table(index="Month", columns="Site ID", values="ResultNum", aggfunc="last").sort_index()

# ---- Target line ----
params = load_params_from_url(PARAMS_URL)
row = params.loc[params["Parameter"].str.strip().str.lower() == str(sel_param).strip().lower()]
target = row["MaxTarget"].iloc[0] if len(row) else np.nan

# ---- Chart (full-width, series non-red, red target line) ----
fig = go.Figure()
fig.update_layout(colorway=SAFE_COLORWAY)
for col in pivot.columns:
    fig.add_trace(go.Scatter(x=pivot.index, y=pivot[col], mode="lines+markers", name=str(col)))
if pd.notna(target):
    fig.add_hline(y=float(target), line_color="red", line_width=2, annotation_text=f"Target {target}", annotation_position="top left")
fig.update_layout(height=560, margin=dict(l=40,r=10,t=10,b=40),
                  legend=dict(orientation="v", y=0.5, x=1.02),
                  xaxis_title="Month (last test per month)", yaxis_title=str(sel_param))
st.plotly_chart(fig, use_container_width=True)
