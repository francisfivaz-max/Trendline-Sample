
# Water Quality Trends — Monthly Trends (Read-only)
# v5: Wide→Long melt for parameter columns (e.g., "AL Aluminium (mg/l)" etc.).
#     Sheet selector + column mapper (Type/Site/Date), parameter column picker,
#     robust numeric parsing, Narwhals-safe plotting, and red Max Target line.
import io, os, re, requests
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Water Quality Trends", layout="wide")
st.title("Water Quality Trends — Monthly Trends (Read-only)")
st.caption("Load any lab sheet where parameters are COLUMNS. The app melts them into tidy rows.")

# -----------------------------
# Config (URLs via secrets or local fallbacks)
# -----------------------------
EXCEL_URL = st.secrets.get("EXCEL_URL", "")
LOCAL_XLSX = os.path.join("data", "Results Trendline Template.xlsx")
TARGETS_URL = st.secrets.get("TARGETS_URL", "")
LOCAL_TARGETS = os.path.join("data", "param_targets_max_only.csv")

# -----------------------------
# Utils
# -----------------------------
def _http_get(url: str) -> bytes:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content

_NUM_TXT_ZERO = {"nd", "n/d", "not detected", "bdl", "below detection", "na", "n/a"}

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
    if s.lower() in _NUM_TXT_ZERO or any(tok in s.lower() for tok in [" nd", " bdl"]):
        return 0.0
    # Remove thousands formatting: "10 000", "1,234"
    s = s.replace(" ", "")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    # Find first number
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None

def clean_header_name(s: str) -> str:
    # Strip leading '=' (Excel formula headers), extra spaces
    s = str(s or "").strip()
    if s.startswith("="):
        s = s[1:].strip()
    # Collapse multiple spaces
    s = re.sub(r"\s+", " ", s)
    return s

# -----------------------------
# Cached loaders
# -----------------------------
@st.cache_data(show_spinner=False)
def load_workbook(excel_url: str):
    if excel_url:
        content = _http_get(excel_url)
        wb = pd.read_excel(io.BytesIO(content), sheet_name=None)
    else:
        if not os.path.exists(LOCAL_XLSX):
            return {}
        wb = pd.read_excel(LOCAL_XLSX, sheet_name=None)
    out = {}
    for name, df in wb.items():
        df = pd.DataFrame(df)
        df.columns = [clean_header_name(c) for c in df.columns]
        df = df.loc[:, ~pd.Index(df.columns).duplicated()]
        out[str(name)] = df
    return out

@st.cache_data(show_spinner=False)
def load_targets(targets_url: str):
    try:
        if targets_url:
            content = _http_get(targets_url)
            tdf = pd.read_csv(io.BytesIO(content))
        elif os.path.exists(LOCAL_TARGETS):
            tdf = pd.read_csv(LOCAL_TARGETS)
        else:
            return None
    except Exception:
        return None
    tdf = pd.DataFrame(tdf)
    tdf.columns = [clean_header_name(c) for c in tdf.columns]
    # Normalize required columns
    if "Parameter" not in tdf.columns:
        for c in tdf.columns:
            if c.lower() == "parameter":
                tdf = tdf.rename(columns={c: "Parameter"})
                break
    if "MaxTarget" not in tdf.columns:
        for c in tdf.columns:
            if c.lower().replace(" ", "") in {"maxtarget", "max"}:
                tdf = tdf.rename(columns={c: "MaxTarget"})
                break
    # Clean parameter names the same way we clean headers
    if "Parameter" in tdf.columns:
        tdf["Parameter"] = tdf["Parameter"].map(clean_header_name)
    return tdf if set(["Parameter","MaxTarget"]).issubset(tdf.columns) else None

workbook = load_workbook(EXCEL_URL)
targets = load_targets(TARGETS_URL)

if not workbook:
    st.error("No workbook loaded. Set EXCEL_URL in Secrets or place a local file at data/Results Trendline Template.xlsx.")
    st.stop()

# -----------------------------
# Sheet + column mapping
# -----------------------------
st.subheader("Data source")
sheet_names = list(workbook.keys())
sheet_sel = st.selectbox("Worksheet", sheet_names, index=0)
raw = workbook[sheet_sel].copy()

with st.expander("Preview (first 20 rows)", expanded=False):
    st.dataframe(raw.head(20))

st.subheader("Map your core columns (id_vars)")
cols = ["(none)"] + list(raw.columns)
def pick(label, defaults):
    default_idx = 0
    for cand in defaults:
        if cand in raw.columns:
            default_idx = cols.index(cand)
            break
    return st.selectbox(label, cols, index=default_idx)

c1, c2, c3 = st.columns(3)
with c1:
    col_type = pick("Type", ["Type","TYPE"])
with c2:
    col_site = pick("Site ID", ["Site ID","SiteID","Site","Borehole","Site Id"])
with c3:
    col_date = pick("Date", ["Date","Sample Date","DateSampled","Date/Time","DATE"])

# Build a working df with only mapped id columns + parameter columns
id_map = {}
if col_type != "(none)": id_map[col_type] = "Type"
if col_site != "(none)": id_map[col_site] = "Site ID"
if col_date != "(none)": id_map[col_date] = "DateRaw"

work = raw.rename(columns=id_map).copy()

# Determine parameter columns automatically = everything not in id_vars
core = set([c for c in ["Type","Site ID","DateRaw"] if c in work.columns])
all_cols = list(work.columns)
auto_params = [c for c in all_cols if c not in core]

st.subheader("Pick parameter columns (to melt)")
param_cols = st.multiselect("Parameters (columns will become rows)", options=auto_params, default=auto_params)

if not param_cols:
    st.error("Select at least one parameter column to melt.")
    st.stop()

# Melt wide→long
long = pd.melt(
    work,
    id_vars=list(core) if core else None,
    value_vars=param_cols,
    var_name="Parameter",
    value_name="Result"
)

# Clean/parse
if "DateRaw" not in long.columns: long["DateRaw"] = None
long["Parameter"] = long["Parameter"].map(clean_header_name)
long["DateClean"] = long["DateRaw"].map(parse_date_any)
long["Result"] = long["Result"].map(parse_result_to_float)
long["MonthStart"] = long["DateClean"].dt.to_period("M").dt.to_timestamp()

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    type_vals = sorted([t for t in long.get("Type", pd.Series(dtype=object)).dropna().unique().tolist() if str(t).strip()!=""])
    type_sel = st.selectbox("Type", type_vals) if type_vals else None

subset0 = long.copy()
if type_sel is not None:
    subset0 = subset0[subset0["Type"] == type_sel]
if subset0.empty and len(long) > 0:
    st.warning("No rows for this Type. Showing all data so you can continue.")
    subset0 = long.copy()

params = sorted([p for p in subset0["Parameter"].dropna().unique().tolist() if str(p).strip()!=""])
sites_all = sorted([s for s in subset0.get("Site ID", pd.Series(dtype=object)).dropna().unique().tolist() if str(s).strip()!=""])

pcol, scol = st.columns([2,2])
with pcol:
    parameter_sel = st.selectbox("Parameter", params) if params else None
with scol:
    if parameter_sel:
        sub_for_sites = subset0[subset0["Parameter"] == parameter_sel]
    else:
        sub_for_sites = subset0
    sites = sorted([s for s in sub_for_sites.get("Site ID", pd.Series(dtype=object)).dropna().unique().tolist() if str(s).strip()!=""])
    sites_sel = st.multiselect("Site IDs", sites, default=sites)

# Date picker
if subset0["MonthStart"].notna().any():
    min_m = subset0["MonthStart"].min()
    max_m = subset0["MonthStart"].max()
else:
    min_m = pd.to_datetime("today") - pd.Timedelta(days=365)
    max_m = pd.to_datetime("today")
date_range = st.date_input("Month range", value=(min_m, max_m), min_value=min_m, max_value=max_m)

# Must have parameters
if not params:
    st.error("No Parameter values detected after unpivot. Double-check your parameter selection above.")
    st.stop()

# Filtered set
subset1 = subset0[subset0["Parameter"] == parameter_sel] if parameter_sel else subset0.copy()
subset2 = subset1.copy()
if sites_sel:
    subset2 = subset2[subset2["Site ID"].isin(sites_sel)]
start_d = pd.to_datetime(date_range[0])
end_d   = pd.to_datetime(date_range[1])
subset2 = subset2[(subset2["MonthStart"] >= start_d) & (subset2["MonthStart"] <= end_d)]

# Last test per month
if not subset2.empty:
    subset2 = subset2.sort_values(["Site ID","MonthStart","DateClean"])
    monthly = subset2.groupby(["Site ID","MonthStart"], as_index=False).last(numeric_only=False)
else:
    monthly = subset2.copy()

# Build plot df (Narwhals-safe)
if monthly.empty:
    base_df = pd.DataFrame({"MonthStart":[start_d,end_d], "Result":[None,None], "Site ID":[None,None]})
else:
    base_df = monthly.sort_values(["MonthStart","Site ID"]).copy()

base_df = pd.DataFrame(base_df).loc[:, ~pd.Index(base_df.columns).duplicated()]
rename_for_plot = {}
if "MonthStart" in base_df.columns: rename_for_plot["MonthStart"]="__x"
if "Result" in base_df.columns:     rename_for_plot["Result"]="__y"
if "Site ID" in base_df.columns:    rename_for_plot["Site ID"]="__color"
if "Type" in base_df.columns:       rename_for_plot["Type"]="__type"
if "DateClean" in base_df.columns:  rename_for_plot["DateClean"]="__date"
plot_df = base_df.rename(columns=rename_for_plot).copy()

# Ensure unique columns
new_cols=[]; seen=set()
for c in plot_df.columns:
    s=str(c); base=s; i=1
    while s in seen:
        i+=1; s=f"{base}__{i}"
    seen.add(s); new_cols.append(s)
plot_df.columns=new_cols
hover_cols=[c for c in ["__type","__date"] if c in plot_df.columns]

# Plot
fig = px.line(plot_df, x="__x", y="__y", color="__color", hover_data=hover_cols,
              title="Monthly trend (last test per month)")
fig.update_layout(legend_title_text="Site ID", xaxis_title="Month",
                  yaxis_title=parameter_sel or "Result", margin=dict(l=20,r=20,t=60,b=20))

# Target line (match parameter name after cleaning)
tdf = targets
if tdf is not None and parameter_sel:
    # clean both sides before compare
    key = clean_header_name(parameter_sel)
    trow = tdf[ tdf["Parameter"].map(clean_header_name).str.casefold() == key.casefold() ]
    if not trow.empty and "MaxTarget" in trow.columns:
        try:
            y = float(trow["MaxTarget"].values[0])
            fig.add_scatter(x=[start_d,end_d], y=[y,y], mode="lines", name="Max target",
                            line=dict(color="red", dash="solid", width=3),
                            hovertemplate="Max target: %{y}<extra></extra>", showlegend=True)
        except: pass

fig.update_xaxes(range=[start_d, end_d])
st.plotly_chart(fig, use_container_width=True)

# Footer hint
st.caption("Tip: If your headers start with '=' in Excel, this app strips it automatically.")
