# Water Quality Trends — Monthly Trends (Read‑only)
# Area filter removed, Type filter kept
import io, os, requests
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Water Quality Trends", layout="wide")
st.title("Water Quality Trends — Monthly Trends (Read‑only)")
st.caption("Data loads from a GitHub RAW URL. Viewers can only filter & explore.")

EXCEL_URL = st.secrets.get("EXCEL_URL", "")
TARGETS_URL = st.secrets.get("TARGETS_URL", "")  # optional

LOCAL_XLSX = os.path.join("data", "Results Trendline Template.xlsx")
LOCAL_TARGETS = os.path.join("data", "param_targets_max_only.csv")

def _http_get(url: str) -> bytes:
    r = requests.get(url, timeout=60, headers={"User-Agent": "streamlit-app"})
    r.raise_for_status()
    return r.content

@st.cache_data(show_spinner=False)
def load_excel() -> pd.DataFrame:
    if EXCEL_URL:
        content = _http_get(EXCEL_URL)
        if content[:20].lstrip().startswith(b"<"):
            raise RuntimeError("EXCEL_URL did not return binary Excel. Use a RAW link (raw.githubusercontent.com).")
        df = pd.read_excel(io.BytesIO(content), sheet_name="Final", engine="openpyxl")
    elif os.path.exists(LOCAL_XLSX):
        df = pd.read_excel(LOCAL_XLSX, sheet_name="Final", engine="openpyxl")
    else:
        raise RuntimeError("No Excel available. Set EXCEL_URL or provide a local file in data/.")
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["MonthStart"] = df["Date"].values.astype("datetime64[M]")
    id_cols = [c for c in ["Date","MonthStart","Type","Area","Site ID","Sample date"] if c in df.columns]
    value_cols = [c for c in df.columns if c not in id_cols]
    long = df.melt(id_vars=id_cols, value_vars=value_cols, var_name="Parameter", value_name="Result")
    long["Result"] = pd.to_numeric(long["Result"], errors="coerce")
    return long.dropna(subset=["MonthStart","Site ID","Parameter","Result"])

@st.cache_data(show_spinner=False)
def load_targets() -> pd.DataFrame:
    if TARGETS_URL:
        content = _http_get(TARGETS_URL)
        t = pd.read_csv(io.BytesIO(content))
    elif os.path.exists(LOCAL_TARGETS):
        t = pd.read_csv(LOCAL_TARGETS)
    else:
        return pd.DataFrame(columns=["Parameter","MaxTarget"])
    t.columns = [c.strip() for c in t.columns]
    return t[["Parameter","MaxTarget"]]

# Refresh button
if st.button("Refresh data"):
    load_excel.clear()

# Load
try:
    data = load_excel()
except Exception as e:
    st.error(f"Failed to load Excel: {e}")
    st.stop()

targets = load_targets()

# --- Sidebar: Type, Parameter, Sites, Month range ---
with st.sidebar:
    st.header("Filters")
    # Type kept
    types = sorted(data["Type"].dropna().unique()) if "Type" in data.columns else []
    type_sel = st.selectbox("Type", types) if types else None

# Apply Type filter first (Area removed completely)
subset0 = data.copy()
if type_sel is not None:
    subset0 = subset0[subset0["Type"] == type_sel]

# Parameter selector
params = sorted(subset0["Parameter"].dropna().unique())
parameter_sel = st.sidebar.selectbox("Parameter", params)

subset1 = subset0[subset0["Parameter"] == parameter_sel]

# Site selector
sites = sorted(subset1["Site ID"].dropna().unique())
sites_sel = st.sidebar.multiselect("Site IDs", sites, default=sites)

# Month range
min_m = subset1["MonthStart"].min()
max_m = subset1["MonthStart"].max()
date_range = st.sidebar.date_input("Month range", value=(min_m, max_m), min_value=min_m, max_value=max_m)
if isinstance(date_range, tuple):
    start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
else:
    start_d, end_d = min_m, max_m

# Apply filters
f = subset1[(subset1["Site ID"].isin(sites_sel)) & (subset1["MonthStart"] >= start_d) & (subset1["MonthStart"] <= end_d)].copy()

# Monthly = last reading per month per site
if not f.empty:
    f["_rank"] = f.groupby(["Site ID","MonthStart"])["Date"].rank(method="first", ascending=False)
    monthly = f[f["_rank"] == 1.0].copy()
else:
    monthly = f

st.subheader(f"{parameter_sel}" + (f" — {type_sel}" if type_sel else ""))

# Base frame so chart renders even with no data
if monthly.empty:
    base_df = pd.DataFrame({"MonthStart":[start_d,end_d], "Result":[None,None], "Site ID":[None,None]})
else:
    base_df = monthly.sort_values(["MonthStart","Site ID"])

# Non‑red palette for site lines
site_palette = ["#1f77b4", "#2ca02c", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

fig = px.line(
    base_df,
    x="MonthStart", y="Result",
    color="Site ID",
    color_discrete_sequence=site_palette,
    hover_data=["Site ID","Date","Result"],
    title="Monthly trend (last test per month)"
)

# Always add solid red Max target
trow = targets[targets["Parameter"] == parameter_sel].head(1)
if not trow.empty and pd.notna(trow["MaxTarget"].values[0]):
    y = float(trow["MaxTarget"].values[0])
    fig.add_scatter(
        x=[start_d, end_d],
        y=[y, y],
        mode="lines",
        name="Max target",
        line=dict(color="red", dash="solid", width=3),
        hovertemplate="Max target: %{y}<extra></extra>",
        showlegend=True
    )

# Keep the target visible even with no data
fig.update_xaxes(range=[start_d, end_d])

st.plotly_chart(fig, use_container_width=True)
st.caption("Monthly values = last test per month per Site ID. Max target shown as solid red line. (Area removed; Type kept.)")
