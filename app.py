
# Water Quality Trends — Monthly Trends (Read‑only)
# v6.3 (simple UI + hard‑wired for Results Trendline Template.xlsx)
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
    if pd.isna(x):
        return None
    if isinstance(x,(int,float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return None
    if s.lower() in {"nd","n/d","not detected","bdl"}:
        return 0.0
    s = s.replace(" ", "")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return None
    return float(m.group(0))

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
# Data loaders
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
    site_col = coalesce_col(df, ["Site ID","Site","Plant","Location","Borehole"])
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
    return long

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
if "Site ID" not in data.columns or "MonthStart" not in data.columns:
    st.error("No Site or Date detected"); st.stop()
data = data.dropna(subset=["MonthStart","Site ID"]).copy()

with st.sidebar:
    st.header("Filters")
    type_vals = sorted(data["Type"].dropna().astype(str).unique().tolist())
    type_sel = st.selectbox("Type", type_vals)
    min_m,max_m=data["MonthStart"].min(),data["MonthStart"].max()
    date_range=st.date_input("Month range",(min_m,max_m),min_value=min_m,max_value=max_m)
params = sorted(data[data["Type"]==type_sel]["Parameter"].dropna().unique().tolist())
param_sel = st.selectbox("Parameter",params) if params else None

if not param_sel: st.stop()
start_d,end_d=pd.to_datetime(date_range[0]),pd.to_datetime(date_range[1])
f=data[(data["Type"]==type_sel)&(data["Parameter"]==param_sel)&(data["MonthStart"].between(start_d,end_d))]
f=f.sort_values(["Site ID","MonthStart","Date"] if "Date" in f.columns else ["Site ID","MonthStart"])
monthly=f.groupby(["Site ID","MonthStart"],as_index=False).last(numeric_only=False)

st.subheader(f"{param_sel} — {type_sel}")
plot_df=monthly.rename(columns={"MonthStart":"__x","Result":"__y","Site ID":"__color"})
fig=px.line(plot_df,x="__x",y="__y",color="__color",title="Monthly trend (last test per month)")
fig.update_layout(yaxis_title=param_sel,xaxis_title="Month",legend_title_text="Site ID")
row=targets[targets["Parameter"].str.casefold()==param_sel.casefold()]
if not row.empty:
    try:
        y=float(row["MaxTarget"].values[0])
        fig.add_scatter(x=[start_d,end_d],y=[y,y],mode="lines",name="Max target",
            line=dict(color="red",width=3))
    except: pass
st.plotly_chart(fig,use_container_width=True)
