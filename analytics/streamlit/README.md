# Gyrinx Analytics Dashboard

Streamlit app for exploring production data.

## Setup

```bash
# Create venv (from repo root)
cd analytics/streamlit
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Ensure analytics database is running
docker compose --profile analytics up -d postgres-analytics

# Restore latest export (if not already done)
./scripts/analytics_restore.sh

# Run the dashboard
streamlit run analytics/streamlit/app.py
```

Opens at http://localhost:8501
