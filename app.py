# Water Quality Trends — Monthly Trends (Read‑only)
# Area removed, Type kept. Robust date parsing & robust numeric parsing for Result.
import io, os, re, requests
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

def _to_datetime(s):
    return pd.to_datetime(s, errors="coerce", dayfirst=True, infer_datetime_format=True)

def _coerce_number(val):
    # Convert a messy cell to a float.
    # - Handles commas and spaces as thousand separators
    # - Handles '<1' or '>5' by using the numeric part
    # - Strips units like 'cfu/100ml'
    # - Maps ND/Not detected/BDL to 0
    # Returns float or None.
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s == "":
        return None
    low = s.lower()
    if low in {"nd", "not detected", "bdl", "n/d", "na"}:
        return 0.0
    # Replace commas
    s = s.replace(",", "")
    # Remove spaces inside numbers like "10 000"
    s = s.replace(" ", "")
    # Remove inequality symbols, keep numeric
    s = s.replace("<", "").replace(">", "")
    # Find first number
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except:
        return None

@st.cache_data(show_spinner=False)
def load_excel() -> pd.DataFrame:
    # --- Load ---
    if EXCEL_URL:
        content = _http_get(EXCEL_URL)
        if content[:20].lstrip().startswith(b"<"):
            raise RuntimeError("EXCEL_URL did not return binary Excel. Use a RAW link (raw.githubusercontent.com).")
        df = pd.read_excel(io.BytesIO(content), sheet_name="Final", engine="openpyxl")
    elif os.path.exists(LOCAL_XLSX):
        df = pd.read_excel(LOCAL_XLSX, sheet_name="Final", engine="openpyxl")
    else:
        raise RuntimeError("No Excel available. Set EXCEL_URL or provide a local file in data/.")

    # --- Clean strings ---
    for c in ["Type", "Area", "Site ID"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    # --- Dates (robust) ---
    has_date = "Date" in df.columns
    has_sample = "Sample date" in df.columns

    if has_date:
        df["Date"] = _to_datetime(df["Date"])
    if has_sample:
        df["Sample date"] = _to_datetime(df["Sample date"])

    if has_date and has_sample:
        df["DateClean"] = df["Date"].combine_first(df["Sample date"])
    elif has_date:
        df["DateClean"] = df["Date"]
    elif has_sample:
        df["DateClean"] = df["Sample date"]
    else:
        df["DateClean"] = pd.NaT

    # MonthStart from cleaned date
    df["MonthStart"] = df["DateClean"].dt.to_period("M").dt.to_timestamp()

    # --- Unpivot ---
    id_cols = [c for c in ["Date","Sample date","DateClean","MonthStart","Type","Site ID","Area"] if c in df.columns]
    value_cols = [c for c in df.columns if c not in id_cols]

    long = df.melt(id_vars=id_cols, value_vars=value_cols, var_name="Parameter", value_name="Result")
    long["Parameter"] = long["Parameter"].astype(str).str.strip()

    # Robust numeric parsing for Result
    long["ResultNum"] = long["Result"].apply(_coerce_number)

    # Drop rows without month/site/parameter or non-numeric results
    long = long.dropna(subset=["MonthStart","Site ID","Parameter","ResultNum"])

    # Rename for plotting
    long = long.rename(columns={"ResultNum": "Result"})

    return long

@st.cache_data(show_spinner=False)
def load_targets() -> pd.DataFrame:
    if TARGETS_URL:
        t = pd.read_csv(io.BytesIO(_http_get(TARGETS_URL)))
    elif os.path.exists(LOCAL_TARGETS):
        t = pd.read_csv(LOCAL_TARGETS)
    else:
        return pd.DataFrame(columns=["Parameter","MaxTarget"])
    t.columns = [c.strip() for c in t.columns]
    t["Parameter"] = t["Parameter"].astype(str).str.strip()
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
    types = sorted(data["Type"].dropna().unique()) if "Type" in data.columns else []
    type_sel = st.selectbox("Type", types) if types else None

subset0 = data.copy()
if type_sel is not None:
    subset0 = subset0[subset0["Type"] == type_sel]

params = sorted(subset0["Parameter"].dropna().unique())
parameter_sel = st.sidebar.selectbox("Parameter", params)

subset1 = subset0[subset0["Parameter"] == parameter_sel]

sites = sorted(subset1["Site ID"].dropna().unique())
sites_sel = st.sidebar.multiselect("Site IDs", sites, default=sites)

min_m = subset1["MonthStart"].min()
max_m = subset1["MonthStart"].max()
date_range = st.sidebar.date_input("Month range", value=(min_m, max_m), min_value=min_m, max_value=max_m)
if isinstance(date_range, tuple):
    start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
else:
    start_d, end_d = min_m, max_m

# Apply filters
f = subset1[(subset1["Site ID"].isin(sites_sel)) & (subset1["MonthStart"] >= start_d) & (subset1["MonthStart"] <= end_d)].copy()

# Diagnostics
with st.expander("Data diagnostics (for current selection)"):
    st.write({
        "rows_before_group": int(f.shape[0]),
        "unique_sites": int(f["Site ID"].nunique() if "Site ID" in f.columns else 0),
        "months": f["MonthStart"].min(),
        "months_to": f["MonthStart"].max(),
    })

# Monthly = last reading per month per site (use DateClean)
if not f.empty:
    if "DateClean" in f.columns:
        f["_rank"] = f.groupby(["Site ID","MonthStart"])["DateClean"].rank(method="first", ascending=False)
        monthly = f[f["_rank"] == 1.0].copy()
    else:
        monthly = f.groupby(["Site ID","MonthStart"], as_index=False)["Result"].mean()
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
    hover_data=[c for c in ["Type","Site ID","DateClean","Result"] if c in base_df.columns],
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

fig.update_xaxes(range=[start_d, end_d])
st.plotly_chart(fig, use_container_width=True)
st.caption("Monthly values = last test per month per Site ID (robust numeric & date parsing). Max target is solid red. Area removed, Type kept.")
