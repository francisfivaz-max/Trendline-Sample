
# Water Quality Trends — Monthly (Secrets-only)

This build **only** reads URLs from Streamlit **secrets**. No uploads, no URL inputs.

## 1) Add secrets
Create `.streamlit/secrets.toml` locally (or set in Streamlit Cloud → *App settings → Secrets*):

```toml
[urls]
excel = "https://raw.githubusercontent.com/<you>/<repo>/main/data/Long%20Table%20Trendline.xlsx"
parameters = "https://raw.githubusercontent.com/<you>/<repo>/main/data/parameters.csv"
```

`parameters.csv` must contain at least two columns: `Parameter, MaxTarget`. If `MaxTarget` has two values like `0.1,0.5`, the larger is used.

## 2) Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes
- App aggregates **last test per month per site**.
- Robust parsing for `Result` handles `<1`, `>5`, thousand-separators, units (e.g., `cfu/100ml`), and `ND/BDL` → 0.
- Duplicate `Date` columns are auto-resolved by taking the first non-null across them.
- A red **Target** line stays permanently visible (if a target exists for the selected parameter).
