
# Water Quality Trends — Monthly Trends (Read‑only)
# v6.4: smart per‑Type month range + auto‑expand if empty
import io, os, re, requests
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Water Quality Trends", layout="wide")
st.title("Water Quality Trends — Monthly Trends (Read‑only)")
st.caption("Data loads from GitHub RAW URL. Viewers can only filter & explore.")

# -----------------------------
# Config
# -----------------------------
EXCEL_URL   = st.secrets.get("EXCEL_URL", "https://raw.githubusercontent.com/francisfivaz-max/Trendline-Sample/refs/heads/main/data/Results%20Trendline%20Template.xlsx")
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
        raise RuntimeError("EXCEL_URL returned HTML, not Excel. Check RAW link.")
    return content

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

def parse_result(x):
    if pd.isna(x): return None
    if isinstance(x,(int,float)) and not isinstance(x,bool): return float(x)
    s = str(x).strip()
    if not s: return None
    if s.lower() in {"nd","n/d","not detected","bdl","bdl.","tntc"}: return 0.0
    s = s.replace(" ", "")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    m = re.search(r"[-+]?\d*\.?\d+", s)
    return float(m.group(0)) if m else None

PARAM_HEADERS = [
    "Colour, True (PtCo)","EC Electrical Conductivity @25°c (mS/m)",
    "TDS Total Dissolved Solids (mg/l)","SS","BSV","VSS","pH Value @ 25°C (pH)",
    "TURB Turbidity (NTU)","NH4 Nitrogen, Ammonia Nessler Method (mg/l as N)",
    "CA Calcium (mg/l Ca)","CL Chloride (mg/l Cl)","F- Fluoride (mg/l F)",
    "MG Magnesium (mg/l Mg)","THARD Total Hardness (mg/l CaCo3)",
    "N03 Nitrate as N (mg/l as N)","NO2 Nitrite (mg/l NO2-N)","TKN",
    "K Potassium (mg/l K)","NA Sodium (mg/l Na)","SO4 Sulphate (mg/l SO4)",
    "ZN Zinc (mg/l)","AL Aluminium (mg/l)","SB Acid Solube Antimony",
    "AS Acid Solube Arsenic","CD Cadmium (mg/l)","TCR Total chromium(mg/l)",
    "CR Hexavalent Chromium","CO Cobalt (mg/l)","CU Copper(mg/l)",
    "CN Total Cyanide","FE Iron (mg/l Fe)","PB Lead  (mg/l)",
    "MN Manganese (mg/l Mn)","HG Soluble Mercury","NI Nickel (mg/l)",
    "PHENOL (mg/l)","OIL","ST+Ba","PO4 Phosphates","TP04",
    "TALK Total alkalinity  (mg/l CaCO3)","HCO3","COD","CODF","OA","DO",
    "ECOLI Escherichia coli (cfu/100m)","FC Faecal coliform bacteria (cfu/100ml)",
    "TC Total Coliforms Bateria in Water (cfu/100ml)","THPC Total Heterotrophic Plate Count (cfu/ml)",
    "RCL (mg/l)","TCL","SIO2","SURF","B"
]
PARAM_SET = {clean_header(h).casefold() for h in PARAM_HEADERS}

# -----------------------------
# Data loading
# -----------------------------
@st.cache_data(show_spinner=False)
def load_excel() -> pd.DataFrame:
    if EXCEL_URL:
        content = _http_get(EXCEL_URL)
        try:
            df = pd.read_excel(io.BytesIO(content), sheet_name="Final", engine="openpyxl")
        except Exception:
            df = pd.read_excel(io.BytesIO(content), sheet_name=0, engine="openpyxl")
    elif os.path.exists(LOCAL_XLSX):
        df = pd.read_excel(LOCAL_XLSX, sheet_name="Final", engine="openpyxl")
    else:
        raise RuntimeError("No Excel available.")
    df.columns = [clean_header(c) for c in df.columns]

    site_col = coalesce_col(df, ["Site ID","Site","Plant","Location","Borehole","Sampling Point","Sample Point","Point","Site Name"])
    type_col = coalesce_col(df, ["Type","TYPE"])
    date_col = coalesce_col(df, ["Date","Date/Time","Sample Date","Sample date"], fallback_contains="date")

    if date_col:
        df["__Date__"] = pd.to_datetime(df[date_col], errors="coerce")
        df["MonthStart"] = df["__Date__"].values.astype("datetime64[M]")
    else:
        df["MonthStart"] = pd.NaT

    id_cols = [c for c in [site_col,type_col,date_col,"MonthStart"] if c]
    param_cols = [c for c in df.columns if c not in id_cols and clean_header(c).casefold() in PARAM_SET]

    long = df.melt(id_vars=id_cols, value_vars=param_cols, var_name="Parameter", value_name="Result")

    if site_col and site_col!="Site ID": long=long.rename(columns={site_col:"Site ID"})
    if type_col and type_col!="Type": long=long.rename(columns={type_col:"Type"})
    if date_col and date_col!="Date": long=long.rename(columns={date_col:"Date"})

    long["Parameter"]=long["Parameter"].map(clean_header)
    long["Result"]=long["Result"].map(parse_result)
    return long.dropna(subset=["Site ID"]).copy()

@st.cache_data(show_spinner=False)
def load_targets() -> pd.DataFrame:
    if TARGETS_URL:
        t = pd.read_csv(io.BytesIO(_http_get(TARGETS_URL)))
    elif os.path.exists(LOCAL_TGT):
        t = pd.read_csv(LOCAL_TGT)
    else:
        return pd.DataFrame(columns=["Parameter","MaxTarget"])
    t.columns = [clean_header(c) for c in t.columns]
    return t[["Parameter","MaxTarget"]]

# -----------------------------
# UI
# -----------------------------
if st.button("Refresh data"):
    load_excel.clear(); load_targets.clear(); st.experimental_rerun()

data = load_excel(); targets = load_targets()

if "MonthStart" not in data.columns:
    st.error("No dates detected in the sheet."); st.stop()

# Sidebar: Type -> compute date range AFTER type filter
with st.sidebar:
    st.header("Filters")
    type_vals = sorted(data.get("Type", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
    type_sel = st.selectbox("Type", type_vals) if type_vals else None

subset_type = data[data["Type"]==type_sel] if type_sel else data
if subset_type["MonthStart"].notna().any():
    min_m = subset_type["MonthStart"].min()
    max_m = subset_type["MonthStart"].max()
else:
    min_m = data["MonthStart"].min()
    max_m = data["MonthStart"].max()

with st.sidebar:
    date_range = st.date_input("Month range", value=(min_m, max_m), min_value=min_m, max_value=max_m)

# Parameter
params = sorted(subset_type["Parameter"].dropna().astype(str).unique().tolist())
parameter_sel = st.selectbox("Parameter", params) if params else None
if not parameter_sel: st.stop()

start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

# Filter & auto-expand if empty
f = subset_type[(subset_type["Parameter"]==parameter_sel) & (subset_type["MonthStart"].between(start_d, end_d))].copy()
if f.empty:
    # auto expand to available range for this parameter + type
    sub_param = subset_type[subset_type["Parameter"]==parameter_sel]
    if sub_param["MonthStart"].notna().any():
        start_d = sub_param["MonthStart"].min()
        end_d   = sub_param["MonthStart"].max()
        f = sub_param[(sub_param["MonthStart"]>=start_d)&(sub_param["MonthStart"]<=end_d)].copy()
        st.info(f"No data in the selected range. Showing available data for this Type/Parameter: {start_d.date()} → {end_d.date()}.")

# Monthly last value per site
if "Date" in f.columns:
    f = f.sort_values(["Site ID","MonthStart","Date"])
    monthly = f.groupby(["Site ID","MonthStart"], as_index=False).last(numeric_only=False)
else:
    monthly = f.drop_duplicates(["Site ID","MonthStart"], keep="last")

st.subheader(f"{parameter_sel}" + (f" — {type_sel}" if type_sel else ""))

# Chart
if monthly.empty:
    base_df = pd.DataFrame({"MonthStart":[start_d,end_d], "Result":[None,None], "Site ID":[None,None]})
else:
    base_df = monthly.sort_values(["MonthStart","Site ID"])

plot_df = base_df.rename(columns={"MonthStart":"__x","Result":"__y","Site ID":"__color"}).copy()

# Ensure unique columns
new_cols, seen = [], set()
for c in plot_df.columns:
    s=str(c); base=s; i=1
    while s in seen:
        i+=1; s=f"{base}__{i}"
    seen.add(s); new_cols.append(s)
plot_df.columns = new_cols

fig = px.line(plot_df, x="__x", y="__y", color="__color",
              title="Monthly trend (last test per month)")
fig.update_layout(legend_title_text="Site ID", xaxis_title="Month",
                  yaxis_title=parameter_sel or "Result",
                  margin=dict(l=20, r=20, t=60, b=20))

# Target line
row = targets[targets["Parameter"].str.casefold()==parameter_sel.casefold()] if not targets.empty else pd.DataFrame()
if not row.empty:
    try:
        y=float(row["MaxTarget"].values[0])
        fig.add_scatter(x=[start_d,end_d],y=[y,y],mode="lines",name="Max target",
                        line=dict(color="red",width=3))
    except: pass

fig.update_xaxes(range=[start_d, end_d])
st.plotly_chart(fig, use_container_width=True)
