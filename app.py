import pandas as pd
import numpy as np
import altair as alt
import streamlit as st

st.set_page_config(page_title="Water Quality Trends", layout="wide")

# ------------------------------------------------------------------
# Data source URLs via Streamlit secrets (preferred). Falls back to defaults.
# ------------------------------------------------------------------
FINAL_CSV_URL = st.secrets.get(
    "FINAL_CSV_URL",
    "https://raw.githubusercontent.com/yourname/yourrepo/main/Final_Long.csv"
)
TARGETS_CSV_URL = st.secrets.get(
    "TARGETS_CSV_URL",
    "https://raw.githubusercontent.com/yourname/yourrepo/main/param_targets_max_only.csv"
)
# ------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_final():
    df = pd.read_csv(FINAL_CSV_URL)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
    df["MonthStart"] = pd.to_datetime(df["MonthStart"], errors="coerce").values.astype("datetime64[M]")
    df["Result"] = pd.to_numeric(df["Result"], errors="coerce")
    for c in ["Type", "Site ID", "Parameter", "Unit"]:
        df[c] = df[c].astype(str).str.strip()
    return df.dropna(subset=["Type","Site ID","Parameter","MonthStart"])

@st.cache_data(show_spinner=False)
def load_targets():
    try:
        t = pd.read_csv(TARGETS_CSV_URL)
    except Exception:
        return pd.DataFrame(columns=["Parameter","MaxTarget"])
    p_col = next((c for c in t.columns if "param" in c.lower()), None)
    m_col = next((c for c in t.columns if "max" in c.lower() or "target" in c.lower()), None)
    if not p_col or not m_col:
        return pd.DataFrame(columns=["Parameter","MaxTarget"])
    out = t[[p_col,m_col]].rename(columns={p_col:"Parameter", m_col:"MaxTarget"})
    out["Parameter"] = out["Parameter"].astype(str).str.strip()
    out["MaxTarget"] = pd.to_numeric(out["MaxTarget"], errors="coerce")
    return out

def last_test_per_month(df):
    dff = df.copy()
    dff["Date_fallback"] = dff["Date"].fillna(dff["MonthStart"])
    dff = dff.sort_values(["Site ID","MonthStart","Date_fallback"])
    idx = dff.groupby(["Site ID","MonthStart"], as_index=False)["Date_fallback"].idxmax()
    return dff.loc[idx].drop(columns=["Date_fallback"])

def draw_chart(df_plot, parameter, max_target, unit, type_label):
    ylab = f"{parameter}" + (f" ({unit})" if unit else "")
    base = alt.Chart(df_plot).encode(
        x=alt.X("MonthStart:T", title="Month"),
        y=alt.Y("Result:Q", title=ylab),
        color=alt.Color("Site ID:N", title="Site ID"),
        tooltip=["Site ID","MonthStart","Result"]
    )
    lines = base.mark_line(point=True)
    # red rule for target (default 0 if NaN)
    if pd.isna(max_target):
        max_target = 0
    rule = alt.Chart(pd.DataFrame({"y":[float(max_target)]})).mark_rule(color="red", strokeWidth=2).encode(y="y:Q")
    label = alt.Chart(pd.DataFrame({"y":[float(max_target)], "x":[df_plot["MonthStart"].min()]})).mark_text(
        align="left", dx=5, dy=-5, color="red"
    ).encode(x="x:T", y="y:Q", text=alt.value("Max target"))
    return (lines + rule + label).properties(title=f"{parameter} — {type_label}").interactive()

# ------------------------------------------------------------------
# APP
# ------------------------------------------------------------------
st.title("Water Quality Monthly Trends")

if st.button("Refresh data"):
    load_final.clear(); load_targets.clear()

df_long = load_final()
targets = load_targets()

with st.sidebar:
    st.header("Filters")
    type_choice = st.selectbox("Type", sorted(df_long["Type"].unique()))
    params = sorted(df_long.loc[df_long["Type"]==type_choice,"Parameter"].unique())
    parameter = st.selectbox("Parameter", params)
    df_tp = df_long[(df_long["Type"]==type_choice)&(df_long["Parameter"]==parameter)]
    if df_tp.empty:
        st.stop()
    min_m, max_m = df_tp["MonthStart"].min(), df_tp["MonthStart"].max()
    month_range = st.slider("Month range",
        min_value=pd.to_datetime(min_m).to_pydatetime().date(),
        max_value=pd.to_datetime(max_m).to_pydatetime().date(),
        value=(pd.to_datetime(min_m).to_pydatetime().date(), pd.to_datetime(max_m).to_pydatetime().date()),
        format="YYYY/MM/DD")

mask = ((df_long["Type"]==type_choice)&(df_long["Parameter"]==parameter)&
        (df_long["MonthStart"]>=pd.to_datetime(month_range[0]))&
        (df_long["MonthStart"]<=pd.to_datetime(month_range[1])))
df_sel = df_long.loc[mask]
df_monthly = last_test_per_month(df_sel)

unit = df_monthly["Unit"].dropna().iloc[0] if not df_monthly["Unit"].dropna().empty else None
row = targets.loc[targets["Parameter"].str.casefold()==parameter.casefold()]
max_target = row["MaxTarget"].iloc[0] if not row.empty else np.nan

st.subheader(f"{parameter} — {type_choice}")
chart = draw_chart(df_monthly, parameter, max_target, unit, type_choice)
st.altair_chart(chart, use_container_width=True)
st.caption("Monthly values = last test per month per Site ID.")
