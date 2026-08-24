# IM Platform

Institutional Investment Management System for G42 Corporate.
Start date: 13 Aug.

## Local portfolio snapshot app

The local Streamlit app provides a browser login, month/year selector, KPI
summary, portfolio snapshot table, and latest month-over-month diff view
backed by `data/source_of_truth/Portfolio_Snapshot_History.xlsx` and
`data/outputs/Portfolio_Monthly_Diff.xlsx`.

Configure local credentials using either environment variables:

```powershell
$env:IM_PLATFORM_APP_USER="your-user"
$env:IM_PLATFORM_APP_PASSWORD="your-password"
```

or copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` and
fill in local values. Do not commit `.streamlit/secrets.toml`.

Run the app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run src\frontend\streamlit_app.py
```

Then open the URL printed by Streamlit, normally `http://localhost:8501`.

Backfill a historical tracker month into the snapshot history:

```powershell
.\.venv\Scripts\python.exe -m im_platform.cli backfill-monthly-snapshot --tracker-file "C:\path\to\Portfolio Summary Jun'26.xlsx"
```
