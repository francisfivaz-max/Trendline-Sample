
# Water Quality Trends — Monthly (Secrets-only, v6)

- Reads RAW URLs from Streamlit **secrets**.
- Selects **last test per month per site** using `groupby().idxmax()`.
- Includes an optional per-site **audit table** to verify values.
