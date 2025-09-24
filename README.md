
# Water Quality Trends — Monthly (Secrets-only, v3)

Stronger Date detection:
- Finds every column whose header contains "date" or "sample"
- Parses EACH by position (iloc) to avoid duplicate-name issues
- Coalesces left→right to a single `Date`
