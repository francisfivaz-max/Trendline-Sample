
# Water Quality Trends — Monthly (Secrets-only, v5)

- Never calls `to_datetime(df["Date"])` directly.
- Makes column labels unique (Date, Date.1, Date.2, ...), then builds Date by index.
- Vectorized Month derivation; permanent red target line.
