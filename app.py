
# Water Quality Trends — Monthly Trends (Read‑only)
# v6 (simple UI): Area removed, Type kept. Filters: Type, Parameter, Month range.
# Auto-melts wide sheets (parameters as columns) into tidy rows.
import io, os, re, requests
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Water Quality Trends", layout="wide")
st.title("Water Quality Trends — Monthly Trends (Read‑only)")
st.caption("Data loads from a GitHub RAW URL. Viewers can only filter & explore.")

# -----------------------------
# Config
# -----------------------------
EXCEL_URL   = st.secrets.get("EXCEL_URL", "")
TARGETS_URL = st.secrets.get("TARGETS_URL", "")
LOCAL_XLSX  = os.path.join("data", "Results Trendline Template.xlsx")
LOCAL_TGT   = os.path.join("data", "param_targets_max_only.csv")

# -----------------------------
# Utilities
# -----------------------------
def _http_get(url: str) -> bytes:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    # Basic guard against HTML mistaken as Excel/CSV
    content = resp.content
    if content[:20].lstrip().startswith(b"<"):
        raise RuntimeError("EXCEL_URL returned HTML, not a binary Excel file (check RAW link).")
    return content

_NUM_TXT_ZERO = {"nd","n/d","not detected","bdl","below detection","na","n/a"}

def parse_date_any(x):
    if pd.isna(x):
        return pd.NaT
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        try:
            return pd.to_datetime("1899-12-30") + pd.to_timedelta(int(x), unit="D")
        except Exception:
            pass
    try:
        return pd.to_datetime(x, errors="coerce", dayfirst=True, utc=False)
    except Exception:
        return pd.NaT

def parse_result_to_float(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = str(x).strip()
    if not s:
        return None
    if s.lower() in _NUM_TXT_ZERO or any(tok in s.lower() for tok in [" nd"," bdl"]):
        return 0.0
    s = s.replace(" ", "")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None

def clean_header(s):
    s = str(s or "").strip()
    if s.startswith("="):
        s = s[1:].strip()
    s = re.sub(r"\s+", " ", s)
    return s

# -----------------------------
# Data loaders
# -----------------------------
@st.cache_data(show_spinner=False)
def load_excel() -> pd.DataFrame:
    # Load sheet named "Final" (like your style) or first sheet as fallback
    if EXCEL_URL:
        content = _http_get(EXCEL_URL)
        try:
            df = pd.read_excel(io.BytesIO(content), sheet_name="Final", engine="openpyxl")
        except Exception:
            df = pd.read_excel(io.BytesIO(content), sheet_name=0, engine="openpyxl")
    elif os.path.exists(LOCAL_XLSX):
        try:
            df = pd.read_excel(LOCAL_XLSX, sheet_name="Final", engine="openpyxl")
        except Exception:
            df = pd.read_excel(LOCAL_XLSX, sheet_name=0, engine="openpyxl")
    else:
        raise RuntimeError("No Excel available. Set EXCEL_URL or provide a local file in data/.")
    df = pd.DataFrame(df)
    df.columns = [clean_header(c) for c in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]
    # Construct MonthStart from Date/Sample date if present
    date_col = "Date" if "Date" in df.columns else ("Sample date" if "Sample date" in df.columns else None)
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df["MonthStart"] = df[date_col].values.astype("datetime64[M]")
    # Melt: treat everything except id columns as parameters
    id_cols = [c for c in ["Date","MonthStart","Type","Area","Site ID","Sample date"] if c in df.columns]
    value_cols = [c for c in df.columns if c not in id_cols]
    long = df.melt(id_vars=id_cols, value_vars=value_cols, var_name="Parameter", value_name="Result")
    long["Result"] = long["Result"].map(parse_result_to_float)
    # Canonicalize dtypes
    if "MonthStart" not in long.columns:
        long["MonthStart"] = pd.NaT
    return long.dropna(subset=["MonthStart","Site ID","Parameter"]).copy()

@st.cache_data(show_spinner=False)
def load_targets() -> pd.DataFrame:
    if TARGETS_URL:
        content = _http_get(TARGETS_URL)
        t = pd.read_csv(io.BytesIO(content))
    elif os.path.exists(LOCAL_TGT):
        t = pd.read_csv(LOCAL_TGT)
    else:
        return pd.DataFrame(columns=["Parameter","MaxTarget"])
    t.columns = [clean_header(c) for c in t.columns]
    # Normalize column names
    if "Parameter" not in t.columns:
        for c in t.columns:
            if c.lower() == "parameter":
                t = t.rename(columns={c:"Parameter"})
                break
    if "MaxTarget" not in t.columns:
        for c in t.columns:
            if c.lower().replace(" ","") in {"maxtarget","max"}:
                t = t.rename(columns={c:"MaxTarget"})
                break
    return t[["Parameter","MaxTarget"]]

# -----------------------------
# UI: Refresh button
# -----------------------------
if st.button("Refresh data"):
    load_excel.clear()
    load_targets.clear()
    st.experimental_rerun()

# Load data
data = load_excel()
targets = load_targets()

# -----------------------------
# Sidebar — minimal filters
# -----------------------------
with st.sidebar:
    st.header("Filters")
    # Keep Type (single select). If absent, skip.
    type_vals = sorted(data["Type"].dropna().unique().tolist()) if "Type" in data.columns else []
    type_sel = st.selectbox("Type", type_vals) if type_vals else None

# Apply Type filter
subset0 = data.copy()
if type_sel is not None:
    subset0 = subset0[subset0["Type"] == type_sel]
if subset0.empty and len(data) > 0:
    st.warning("No rows for this Type. Showing all data so you can choose a Parameter.")
    subset0 = data.copy()

# Parameter (single select)
params = sorted(subset0["Parameter"].dropna().astype(str).unique().tolist())
parameter_sel = st.selectbox("Parameter", params) if params else None

if parameter_sel is None:
    st.error("No Parameter values found. Check that your Excel sheet has parameter columns.")
    st.stop()

subset1 = subset0[subset0["Parameter"] == parameter_sel]

# Month range
min_m = subset1["MonthStart"].min()
max_m = subset1["MonthStart"].max()
date_range = st.sidebar.date_input("Month range", value=(min_m, max_m), min_value=min_m, max_value=max_m)
if isinstance(date_range, tuple):
    start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
else:
    start_d, end_d = min_m, max_m

# Apply date filter
f = subset1[(subset1["MonthStart"] >= start_d) & (subset1["MonthStart"] <= end_d)].copy()

# Monthly = last reading per month per site (use Date if available, else MonthStart)
if "Date" in f.columns:
    f = f.sort_values(["Site ID","MonthStart","Date"])
    monthly = f.groupby(["Site ID","MonthStart"], as_index=False).last(numeric_only=False)
else:
    monthly = f.drop_duplicates(["Site ID","MonthStart"], keep="last")

# ---------- Chart ----------
st.subheader(f"{parameter_sel}" + (f" — {type_sel}" if type_sel else ""))

# Base frame so chart renders even with no data
if monthly.empty:
    base_df = pd.DataFrame({"MonthStart":[start_d,end_d], "Result":[None,None], "Site ID":[None,None]})
else:
    base_df = monthly.sort_values(["MonthStart","Site ID"])

# Narwhals-safe: ensure unique columns & rename plotting keys
base_df = pd.DataFrame(base_df).loc[:, ~pd.Index(base_df.columns).duplicated()]
rename_for_plot = {"MonthStart":"__x","Result":"__y","Site ID":"__color"}
plot_df = base_df.rename(columns={k:v for k,v in rename_for_plot.items() if k in base_df.columns}).copy()

# Ensure unique column names
new_cols, seen = [], set()
for c in plot_df.columns:
    s=str(c); base=s; i=1
    while s in seen:
        i+=1; s=f"{base}__{i}"
    seen.add(s); new_cols.append(s)
plot_df.columns = new_cols

# Non‑red palette for site lines (style match)
site_palette = ["#1f77b4","#2ca02c","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf"]

fig = px.line(
    plot_df, x="__x", y="__y", color="__color",
    color_discrete_sequence=site_palette,
    title="Monthly trend (last test per month)"
)
fig.update_layout(
    legend_title_text="Site ID",
    xaxis_title="Month",
    yaxis_title=parameter_sel or "Result",
    margin=dict(l=20, r=20, t=60, b=20),
)

# Add solid red Max target line (if match in targets)
if not targets.empty and parameter_sel:
    key = clean_header(parameter_sel)
    row = targets[targets["Parameter"].map(clean_header).str.casefold() == key.casefold()]
    if not row.empty and "MaxTarget" in row.columns:
        try:
            y = float(row["MaxTarget"].values[0])
            fig.add_scatter(
                x=[start_d, end_d], y=[y, y], mode="lines", name="Max target",
                line=dict(color="red", dash="solid", width=3),
                hovertemplate="Max target: %{y}<extra></extra>", showlegend=True
            )
        except Exception:
            pass

# Keep target visible even with no data
fig.update_xaxes(range=[start_d, end_d])

st.plotly_chart(fig, use_container_width=True)
st.caption("Monthly values = last test per month per Site ID. Max target shown as solid red line. (Area removed; Type kept.)")
