# Water Quality Trends — Option C (GitHub RAW)

## Use a GitHub RAW link
1. Put the Excel in your repo at `data/Results Trendline Template.xlsx`.
2. Open it on GitHub → click **Raw** → copy the URL.
   Example:
   https://raw.githubusercontent.com/<user>/<repo>/main/data/Results%20Trendline%20Template.xlsx
3. In Streamlit **Secrets**, set:
```
EXCEL_URL="https://raw.githubusercontent.com/<user>/<repo>/main/data/Results%20Trendline%20Template.xlsx"
# Optional:
# TARGETS_URL="https://raw.githubusercontent.com/<user>/<repo>/main/data/param_targets_max_only.csv"
```
4. Deploy and click **Refresh data** when you push an updated Excel.

## Local fallback
If EXCEL_URL is not set, the app looks for `data/Results Trendline Template.xlsx` locally.
