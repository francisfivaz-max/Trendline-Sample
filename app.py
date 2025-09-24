
# Water Quality Trends — Monthly Trends (Read‑only)
# v6.2 (simple UI + smart detection + PARAMETER WHITELIST):
# - Minimal filters (Type, Parameter, Month range)
# - Auto-detects Site and Date columns (as in v6.1)
# - Melts ONLY known parameter columns (your 55 headers), so "Year"/"Month"/other fields never get melted
# - Same style + solid red MaxTarget line
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

def coalesce_col(df, candidates, fallback_contains=None):
    for c in candidates:
        if c in df.columns:
            return c
    if fallback_contains:
        needle = fallback_contains.casefold()
        for c in df.columns:
            if needle in str(c).casefold():
                return c
    return None

# Build the 55‑parameter whitelist (cleaned & lowercased for matching)
PARAM_HEADERS_RAW = [
    "Colour, True (PtCo)",
    "EC Electrical Conductivity @25°c (mS/m)",
    "TDS Total Dissolved Solids (mg/l)",
    "SS",
    "BSV",
    "VSS",
    "pH Value @ 25°C (pH)",
    "TURB Turbidity (NTU)",
    "NH4 Nitrogen, Ammonia Nessler Method (mg/l as N)",
    "CA Calcium (mg/l Ca)",
    "CL Chloride (mg/l Cl)",
    "F- Fluoride (mg/l F)",
    "MG Magnesium (mg/l Mg)",
    "THARD Total Hardness (mg/l CaCo3)",
    "N03 Nitrate as N (mg/l as N)",
    "NO2 Nitrite (mg/l NO2-N)",
    "TKN",
    "K Potassium (mg/l K)",
    "NA Sodium (mg/l Na)",
    "SO4 Sulphate (mg/l SO4)",
    "ZN Zinc (mg/l)",
    "AL Aluminium (mg/l)",
    "SB Acid Solube Antimony",
    "AS Acid Solube Arsenic",
    "CD Cadmium (mg/l)",
    "TCR Total chromium(mg/l)",
    "CR Hexavalent Chromium",
    "CO Cobalt (mg/l)",
    "CU Copper(mg/l)",
    "CN Total Cyanide",
    "FE Iron (mg/l Fe)",
    "PB Lead  (mg/l)",
    "MN Manganese (mg/l Mn)",
    "HG Soluble Mercury",
    "NI Nickel (mg/l)",
    "PHENOL (mg/l)",
    "OIL",
    "ST+Ba",
    "PO4 Phosphates",
    "TP04",
    "TALK Total alkalinity  (mg/l CaCO3)",
    "HCO3",
    "COD",
    "CODF",
    "OA",
    "DO",
    "ECOLI Escherichia coli (cfu/100m)",
    "FC Faecal coliform bacteria (cfu/100ml)",
    "TC Total Coliforms Bateria in Water (cfu/100ml)",
    "THPC Total Heterotrophic Plate Count (cfu/ml)",
    "RCL (mg/l)",
    "TCL",
    "SIO2",
    "SURF",
    "B",
]
# Add a couple of common variants to be safe
PARAM_HEADERS_RAW += [
    "EC Electrical Conductivity @25°C (mS/m)",
    "ECOLI Escherichia coli (cfu/100ml)",
    "NO3 Nitrate as N (mg/l as N)",
    "PB Lead (mg/l)",
]

def normalized(s: str) -> str:
    return clean_header(s).casefold()

PARAM_SET = {normalized(h) for h in PARAM_HEADERS_RAW}

# -----------------------------
# Data loaders
# -----------------------------
@st.cache_data(show_spinner=False)
def load_excel() -> pd.DataFrame:
    # Load "Final" or first sheet
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

    # Detect core columns
    site_col = coalesce_col(df, ["Site ID","Site","Plant","Location","Borehole"])
    type_col = coalesce_col(df, ["Type","TYPE"])
    date_col = coalesce_col(df, ["Date","Sample date","Sample Date"], fallback_contains="date")

    # Build MonthStart
    if date_col:
        df["__Date__"] = pd.to_datetime(df[date_col], errors="coerce")
        df["MonthStart"] = df["__Date__"].values.astype("datetime64[M]")
    else:
        df["MonthStart"] = pd.NaT

    # Keep only parameter columns that match the whitelist
    id_cols = [c for c in [site_col, type_col, date_col, "MonthStart"] if c]
    # exact/normalized match
    param_cols = [c for c in df.columns if c not in id_cols and normalized(c) in PARAM_SET]

    # Melt
    long = df.melt(id_vars=[c for c in id_cols if c], value_vars=param_cols,
                   var_name="Parameter", value_name="Result")

    # Standardize names used downstream
    if site_col and site_col != "Site ID":
        long = long.rename(columns={site_col: "Site ID"})
    if type_col and type_col != "Type":
        long = long.rename(columns={type_col: "Type"})
    if date_col and date_col != "Date":
        long = long.rename(columns={date_col: "Date"})

    long["Parameter"] = long["Parameter"].map(clean_header)
    long["Result"] = long["Result"].map(parse_result_to_float)

    return long, param_cols, id_cols

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
# UI: Refresh
# -----------------------------
if st.button("Refresh data"):
    load_excel.clear(); load_targets.clear()
    st.experimental_rerun()

# Load
(data, melted_params, id_cols) = load_excel()
targets = load_targets()

# Guard
if "Site ID" not in data.columns or "MonthStart" not in data.columns:
    st.error("Couldn't detect **Site** or **Date** columns. Make sure your sheet has a site column (e.g., 'Site'/'Site ID'/'Plant') and a date column (anything containing 'Date').")
    st.stop()

# Drop missing essentials
data = data.dropna(subset=["MonthStart","Site ID"]).copy()

# Sidebar — minimal filters
with st.sidebar:
    st.header("Filters")
    type_vals = sorted(data.get("Type", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
    type_sel = st.selectbox("Type", type_vals) if type_vals else None
    min_m = data["MonthStart"].min()
    max_m = data["MonthStart"].max()
    date_range = st.date_input("Month range", value=(min_m, max_m), min_value=min_m, max_value=max_m)

# Filter by Type
subset0 = data.copy()
if type_sel is not None:
    subset0 = subset0[subset0["Type"] == type_sel]
if subset0.empty and len(data) > 0:
    st.warning("No rows for this Type. Showing all data so you can choose a Parameter.")
    subset0 = data.copy()

# Parameter selector
params = sorted(subset0["Parameter"].dropna().astype(str).unique().tolist())
parameter_sel = st.selectbox("Parameter", params) if params else None

if parameter_sel is None:
    st.error("No Parameter values found after loading. Please verify your sheet headers.")
    st.stop()

# Apply date filter
start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
f = subset0[(subset0["MonthStart"] >= start_d) & (subset0["MonthStart"] <= end_d)].copy()

# Keep last reading per month per site
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

# Narwhals-safe rename
base_df = pd.DataFrame(base_df).loc[:, ~pd.Index(base_df.columns).duplicated()]
plot_df = base_df.rename(columns={"MonthStart":"__x","Result":"__y","Site ID":"__color"}).copy()

# Ensure unique column names
new_cols, seen = [], set()
for c in plot_df.columns:
    s=str(c); base=s; i=1
    while s in seen:
        i+=1; s=f"{base}__{i}"
    seen.add(s); new_cols.append(s)
plot_df.columns = new_cols

# Palette
site_palette = ["#1f77b4","#2ca02c","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf"]

fig = px.line(plot_df, x="__x", y="__y", color="__color",
              color_discrete_sequence=site_palette,
              title="Monthly trend (last test per month)")

fig.update_layout(legend_title_text="Site ID", xaxis_title="Month",
                  yaxis_title=parameter_sel or "Result",
                  margin=dict(l=20, r=20, t=60, b=20))

# Target line
if not targets.empty and parameter_sel:
    key = clean_header(parameter_sel)
    row = targets[targets["Parameter"].map(clean_header).str.casefold() == key.casefold()]
    if not row.empty and "MaxTarget" in row.columns:
        try:
            y = float(row["MaxTarget"].values[0])
            fig.add_scatter(x=[start_d, end_d], y=[y, y], mode="lines", name="Max target",
                            line=dict(color="red", dash="solid", width=3),
                            hovertemplate="Max target: %{y}<extra></extra>", showlegend=True)
        except Exception:
            pass

fig.update_xaxes(range=[start_d, end_d])
st.plotly_chart(fig, use_container_width=True)

# Diagnostics (collapsible)
with st.expander("Diagnostics"):
    st.write("ID columns used:", id_cols)
    st.write("Melted parameter columns (matched whitelist):", melted_params)
    # Show a sample of filtered rows for selected parameter
    st.dataframe(subset0[subset0["Parameter"] == parameter_sel].head(20))
