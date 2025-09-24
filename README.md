
# Water Quality Trends — Monthly (URL Only)

This build **only** loads data from a **GitHub RAW Excel URL** (uploads are disabled).

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Use
- Paste the RAW URL in the sidebar and click **Load / Refresh**.
- Choose **Type**, **Month range**, and **Parameter**.
- The chart shows **last test per month per site** with an **always-on red target line** (from `parameters.csv`).

