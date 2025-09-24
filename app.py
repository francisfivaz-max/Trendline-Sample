# Water Quality Trends — Monthly Trends (Read‑only) — GitHub RAW source
import io, os, requests
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Water Quality Trends", layout="wide")
st.title("Water Quality Trends — Monthly Trends (Read‑only)")
st.caption("Data loads from a GitHub RAW URL. Viewers can only filter & explore.")

EXCEL_URL = st.secrets.get("EXCEL_URL", "")
TARGETS_URL = st.secrets.get("TARGETS_URL", "")

LOCAL_XLSX = os.path.join("data", "Results Trendline Template.xlsx")
LOCAL_TARGETS = os.path.join("data", "param_targets_max_only.csv")

def _http_get(url: str) -> bytes:
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content
    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else ""
        raise RuntimeError(f"HTTP {e.response.status_code if e.response else '?'} for {url}\n{body}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e

@st.cache_data(show_spinner=False)
def load_excel() -> pd.DataFrame:
    if EXCEL_URL:
        content = _http_get(EXCEL_URL)
        bio = io.BytesIO(content)
        df = pd.read_excel(bio, sheet_name="Final", engine="openpyxl")
    elif os.path.exists(LOCAL_XLSX):
        df = pd.read_excel(LOCAL_XLSX, sheet_name="Final", engine="openpyxl")
    else:
        raise RuntimeError("No EXCEL_URL secret set and no local Excel found at data/Results Trendline Template.xlsx")
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["MonthStart"] = df["Date"].values.astype("datetime64[M]")
    id_cols = [c for c in ["Date","MonthStart","Type","Area","Site ID","Sample date"] if c in df.columns]
    value_cols = [c for c in df.columns if c not in id_cols]
    long = df.melt(id_vars=id_cols, value_vars=value_cols, var_name="Parameter", value_name="Result")
    long["Result"] = pd.to_numeric(long["Result"], errors="coerce")
    long = long.dropna(subset=["MonthStart","Site ID","Parameter","Result"])
    return long

@st.cache_data(show_spinner=False)
def load_targets() -> pd.DataFrame:
    if TARGETS_URL:
        content = _http_get(TARGETS_URL)
        t = pd.read_csv(io.BytesIO(content))
        t.columns = [c.strip() for c in t.columns]
        if "Parameter" in t.columns and "MaxTarget" in t.columns:
            return t[["Parameter","MaxTarget"]]
        else:
            st.warning("Targets URL loaded but missing required columns Parameter, MaxTarget. Using local fallback if present.")
    if os.path.exists(LOCAL_TARGETS):
        t = pd.read_csv(LOCAL_TARGETS)
        t.columns = [c.strip() for c in t.columns]
        return t[["Parameter","MaxTarget"]]
    return pd.DataFrame(columns=["Parameter","MaxTarget"])

col1, col2 = st.columns(2)
with col1:
    if st.button("Refresh data"):
        load_excel.clear()
with col2:
    if st.button("Refresh targets"):
        load_targets.clear()

try:
    data = load_excel()
except Exception as e:
    st.error(f"Failed to load Excel: {e}")
    st.stop()

targets = load_targets()

st.sidebar.header("Filters")
types = sorted(data["Type"].dropna().unique()) if "Type" in data.columns else []
type_sel = st.sidebar.selectbox("Type", types) if types else None

areas = sorted(data["Area"].dropna().unique())
area_sel = st.sidebar.selectbox("Area", areas)

subset0 = data.copy()
if type_sel is not None:
    subset0 = subset0[subset0["Type"] == type_sel]
subset0 = subset0[subset0["Area"] == area_sel]

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

f = subset1[(subset1["Site ID"].isin(sites_sel)) & (subset1["MonthStart"] >= start_d) & (subset1["MonthStart"] <= end_d)].copy()

if not f.empty:
    f["_rank"] = f.groupby(["Site ID","MonthStart"])["Date"].rank(method="first", ascending=False)
    monthly = f[f["_rank"] == 1.0].copy()
    monthly.drop(columns=["_rank"], inplace=True, errors="ignore")
else:
    monthly = f

st.subheader(f"{parameter_sel} — {area_sel}" + (f" — {type_sel}" if type_sel else ""))

if monthly.empty:
    st.warning("No data for the current filters/month range.")
else:
    fig = px.line(
        monthly.sort_values(["MonthStart","Site ID"]),
        x="MonthStart", y="Result",
        color="Site ID",
        hover_data=["Area","Type","Parameter","Site ID","Date","Result"],
        title="Monthly trend (last test per month)"
    )
    trow = targets[targets["Parameter"]==parameter_sel].head(1)
    if not trow.empty and pd.notna(trow["MaxTarget"].values[0]):
        y = float(trow["MaxTarget"].values[0])
        x0, x1 = monthly["MonthStart"].min(), monthly["MonthStart"].max()
        fig.update_layout(shapes=[dict(type="line", x0=x0, x1=x1, y0=y, y1=y, line=dict(dash="dot", width=2))])
    st.plotly_chart(fig, use_container_width=True)

st.caption("Monthly values = last test in each month per Site ID. Use a GitHub RAW link in the EXCEL_URL secret.")
