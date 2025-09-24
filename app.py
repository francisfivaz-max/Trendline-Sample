
# Water Quality Trends — Monthly Trends (Read-only)
# Area removed, Type kept. Robust date parsing & robust numeric parsing for Result.
import io, os, re, requests
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Water Quality Trends", layout="wide")
st.title("Water Quality Trends — Monthly Trends (Read-only)")
st.caption("Data loads from a GitHub RAW URL. Viewers can only filter & explore.")

# -----------------------------
# Configuration (URLs via secrets or local fallbacks)
# -----------------------------
EXCEL_URL = st.secrets.get("EXCEL_URL", "")
TARGETS_URL = st.secrets.get("TARGETS_URL", "")  # optional

LOCAL_XLSX = os.path.join("data", "Results Trendline Template.xlsx")
LOCAL_TARGETS = os.path.join("data", "param_targets_max_only.csv")

# -----------------------------
# Utilities
# -----------------------------
def _http_get(url: str) -> bytes:
    """Download a file and return bytes; raises for non-200."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content

def _coalesce_cols(df: pd.DataFrame, candidates) -> str | None:
    """Return the first existing column from candidates, else None."""
    for c in candidates:
        if c in df.columns:
            return c
    return None

def parse_date_any(x):
    """Robust date parser that tolerates Excel serials, strings, NaT."""
    if pd.isna(x):
        return pd.NaT
    # Try Excel serials (ints/floats)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        try:
            # Excel epoch: 1899-12-30 in pandas
            return pd.to_datetime("1899-12-30") + pd.to_timedelta(int(x), unit="D")
        except Exception:
            pass
    # Try string/other
    try:
        return pd.to_datetime(x, errors="coerce", dayfirst=True, utc=False)
    except Exception:
        return pd.NaT

_NUM_TXT_ZERO = {"nd", "n/d", "not detected", "bdl", "below detection", "na", "n/a"}

def parse_result_to_float(x):
    """Extract a float from messy lab result strings (handles '<1', '10 000', '1,234', units, ND/BDL)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    # Already numeric
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)

    s = str(x).strip()
    if not s:
        return None

    # Common ND/BDL tokens → 0
    if s.lower() in _NUM_TXT_ZERO or any(tok in s.lower() for tok in [" nd", " bdl"]):
        return 0.0

    # Remove thousands formatting: "10 000", "1,234"
    s = s.replace(" ", "")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)  # keep decimal commas elsewhere if any

    # Find first number
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def load_excel() -> pd.DataFrame:
    # --- Load ---
    if EXCEL_URL:
        content = _http_get(EXCEL_URL)
        df = pd.read_excel(io.BytesIO(content), sheet_name=None)
        # Prefer a sheet named like "Results" or similar, else first
        for name in ["Results", "Sheet1", "Data", "Final", "Monthly", "Trends"]:
            if name in df:
                data = df[name].copy()
                break
        else:
            data = next(iter(df.values())).copy()
    else:
        # Local fallback
        data = pd.read_excel(LOCAL_XLSX, sheet_name=None)
        # Pick the most likely sheet
        for name in ["Results", "Final", "Monthly", "Trends", "Sheet1"]:
            if name in data:
                data = data[name].copy()
                break
        if isinstance(data, dict):
            data = next(iter(data.values())).copy()

    # Drop exact duplicate-named columns early (belt & braces)
    data = pd.DataFrame(data)
    data = data.loc[:, ~pd.Index(data.columns).duplicated()]

    # Standardize expected columns
    type_col     = _coalesce_cols(data, ["Type", "TYPE"])
    site_col     = _coalesce_cols(data, ["Site ID", "SiteID", "Site", "Borehole", "Site Id"])
    param_col    = _coalesce_cols(data, ["Parameter", "PARAMETER"])
    unit_col     = _coalesce_cols(data, ["Unit", "Units"])
    result_col   = _coalesce_cols(data, ["Result", "Value", "RESULT"])
    date_col_any = _coalesce_cols(data, ["Date", "Sample Date", "DateSampled", "DateClean", "DATE"])

    # Keep only the columns we need (if present)
    keep = [c for c in [type_col, site_col, param_col, unit_col, result_col, date_col_any] if c]
    data = data[keep].copy()

    # Rename to canonical names
    rename_map = {}
    if type_col:   rename_map[type_col]   = "Type"
    if site_col:   rename_map[site_col]   = "Site ID"
    if param_col:  rename_map[param_col]  = "Parameter"
    if unit_col:   rename_map[unit_col]   = "Unit"
    if result_col: rename_map[result_col] = "Result"
    if date_col_any: rename_map[date_col_any] = "DateRaw"
    data = data.rename(columns=rename_map)

    # Parse date + numeric
    data["DateClean"] = data["DateRaw"].map(parse_date_any) if "DateRaw" in data else pd.NaT
    data["Result"] = data["Result"].map(parse_result_to_float) if "Result" in data else None

    # MonthStart for grouping (floor to month)
    data["MonthStart"] = data["DateClean"].dt.to_period("M").dt.to_timestamp()

    # Basic cleanup
    if "Type" not in data.columns:
        data["Type"] = None
    if "Parameter" not in data.columns:
        data["Parameter"] = None
    if "Site ID" not in data.columns:
        data["Site ID"] = None

    return data

@st.cache_data(show_spinner=False)
def load_targets() -> pd.DataFrame | None:
    try:
        if TARGETS_URL:
            content = _http_get(TARGETS_URL)
            tdf = pd.read_csv(io.BytesIO(content))
        else:
            tdf = pd.read_csv(LOCAL_TARGETS)
    except Exception:
        return None

    # Expect columns: Parameter, MaxTarget (others ignored)
    tdf = pd.DataFrame(tdf)
    tdf.columns = [c.strip() for c in tdf.columns]
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
    return tdf if "Parameter" in tdf.columns and "MaxTarget" in tdf.columns else None

# -----------------------------
# Load data
# -----------------------------
data = load_excel()
targets = load_targets()

# Global duplicate-column safety net (especially for Narwhals)
data = pd.DataFrame(data).loc[:, ~pd.Index(data.columns).duplicated()]

# -----------------------------
# Sidebar filters
# -----------------------------
with st.sidebar:
    st.header("Filters")

    # Type
    type_vals = sorted([t for t in data["Type"].dropna().unique().tolist() if str(t).strip() != ""]) if "Type" in data.columns else []
    type_sel = st.selectbox("Type", type_vals) if type_vals else None

    # Apply Type filter (with graceful fallback if empty)
    subset0 = data.copy()
    if type_sel is not None:
        subset0 = subset0[subset0["Type"] == type_sel]
    if subset0.empty:
        st.warning("No rows for this Type. Showing all data so you can continue to choose Parameter/Site.")
        subset0 = data.copy()

    # Parameter
    params = sorted([p for p in subset0["Parameter"].dropna().unique().tolist() if str(p).strip() != ""]) if "Parameter" in subset0.columns else []
    parameter_sel = st.selectbox("Parameter", params) if params else None

    if parameter_sel is None:
        st.stop()

    subset1 = subset0[subset0["Parameter"] == parameter_sel]

    # Site IDs
    sites = sorted([s for s in subset1["Site ID"].dropna().unique().tolist() if str(s).strip() != ""]) if "Site ID" in subset1.columns else []
    default_sites = sites
    sites_sel = st.multiselect("Site IDs", sites, default=default_sites)

    # Month range widget (robust when subset is empty)
    if subset1["MonthStart"].notna().any():
        min_m = subset1["MonthStart"].min()
        max_m = subset1["MonthStart"].max()
    else:
        min_m = data["MonthStart"].min()
        max_m = data["MonthStart"].max()

    date_range = st.date_input(
        "Month range",
        value=(min_m, max_m),
        min_value=min_m,
        max_value=max_m,
    )

# -----------------------------
# Filter by sites + date range and compute "last test per month"
# -----------------------------
subset2 = subset1.copy()
if sites_sel:
    subset2 = subset2[subset2["Site ID"].isin(sites_sel)]

# Date filter
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_d = pd.to_datetime(date_range[0])
    end_d   = pd.to_datetime(date_range[1])
else:
    start_d = subset2["MonthStart"].min()
    end_d   = subset2["MonthStart"].max()

subset2 = subset2[(subset2["MonthStart"] >= start_d) & (subset2["MonthStart"] <= end_d)]

# Keep last test per month per Site ID (by DateClean)
if not subset2.empty:
    subset2 = subset2.sort_values(["Site ID", "MonthStart", "DateClean"])
    monthly = subset2.groupby(["Site ID", "MonthStart"], as_index=False).last(numeric_only=False)
else:
    monthly = subset2.copy()

# -----------------------------
# Build plot_df with guaranteed-unique column names
# -----------------------------
if monthly.empty:
    base_df = pd.DataFrame(
        {"MonthStart": [start_d, end_d], "Result": [None, None], "Site ID": [None, None]}
    )
else:
    base_df = monthly.sort_values(["MonthStart", "Site ID"]).copy()

# Force pandas and drop duplicate-named columns
base_df = pd.DataFrame(base_df).loc[:, ~pd.Index(base_df.columns).duplicated()]

# Map required columns to safe internal names used for plotting
rename_for_plot = {}
if "MonthStart" in base_df.columns: rename_for_plot["MonthStart"] = "__x"
if "Result" in base_df.columns:     rename_for_plot["Result"]     = "__y"
if "Site ID" in base_df.columns:    rename_for_plot["Site ID"]    = "__color"
if "Unit" in base_df.columns:       rename_for_plot["Unit"]       = "__unit"
if "Type" in base_df.columns:       rename_for_plot["Type"]       = "__type"
if "DateClean" in base_df.columns:  rename_for_plot["DateClean"]  = "__date"

plot_df = base_df.rename(columns=rename_for_plot).copy()

# Ensure *all* columns are unique strings (belt & braces)
new_cols = []
seen = set()
for c in plot_df.columns:
    c_str = str(c)
    base = c_str
    i = 1
    while c_str in seen:
        i += 1
        c_str = f"{base}__{i}"
    seen.add(c_str)
    new_cols.append(c_str)
plot_df.columns = new_cols

# Hover fields that are different from the core axes/color
hover_cols = [c for c in ["__type", "__date", "__unit"] if c in plot_df.columns]

# -----------------------------
# Plot
# -----------------------------
fig = px.line(
    plot_df,
    x="__x",
    y="__y",
    color="__color",
    hover_data=hover_cols,
    title="Monthly trend (last test per month)"
)

# Titles & layout
ytitle = parameter_sel
if "__unit" in plot_df.columns and plot_df["__unit"].notna().any():
    try:
        ytitle = f"{parameter_sel} ({plot_df['__unit'].dropna().iloc[0]})"
    except Exception:
        pass

fig.update_layout(
    legend_title_text="Site ID",
    xaxis_title="Month",
    yaxis_title=ytitle or "Result",
    margin=dict(l=20, r=20, t=60, b=20),
)

# Add solid red Max target line for this Parameter (if available)
if targets is not None and parameter_sel is not None and not pd.isna(parameter_sel):
    trow = targets.loc[targets["Parameter"].astype(str) == str(parameter_sel)]
    if not trow.empty and "MaxTarget" in trow.columns:
        try:
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
        except Exception:
            pass

fig.update_xaxes(range=[start_d, end_d])

st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Monthly values = last test per month per Site ID (robust date & numeric parsing). "
    "Narwhals DuplicateError is avoided by renaming columns to unique internal names for plotting. "
    "Max target is a solid red line. Area removed; Type kept."
)
