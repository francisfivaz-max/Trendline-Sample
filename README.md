# Minimal Water Quality Trends App

This version uses **Altair** instead of Plotly to keep dependencies small and speed up Streamlit Cloud boots.

## Setup
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Secrets
Create `.streamlit/secrets.toml`:
```toml
FINAL_CSV_URL = "https://raw.githubusercontent.com/yourname/yourrepo/main/Final_Long.csv"
TARGETS_CSV_URL = "https://raw.githubusercontent.com/yourname/yourrepo/main/param_targets_max_only.csv"
```

The red Max target line is always shown (defaults to 0 if missing).
