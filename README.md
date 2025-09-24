# Water Quality Trends App (with secrets)

This Streamlit app loads `Final_Long.csv` and optional targets from **GitHub RAW URLs** provided via **Streamlit secrets**.

## 1) Local run

1. Install deps
```bash
pip install -r requirements.txt
```
2. Create `.streamlit/secrets.toml` next to `app.py`:
```toml
FINAL_CSV_URL = "https://raw.githubusercontent.com/yourname/yourrepo/main/Final_Long.csv"
TARGETS_CSV_URL = "https://raw.githubusercontent.com/yourname/yourrepo/main/param_targets_max_only.csv"
```
3. Run
```bash
streamlit run app.py
```

## 2) Streamlit Cloud

- App settings → **Secrets** → paste the same TOML keys/values as above.
- No need to edit `app.py` when your data URL changes; just update the secrets.

## Notes
- The app shows monthly trends (last test per month per site).
- The red **Max target** line is **always** drawn (defaults to 0 if target not found).
