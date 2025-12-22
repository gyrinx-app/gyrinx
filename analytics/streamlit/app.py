"""
Gyrinx Analytics Dashboard

Run with: streamlit run analytics/streamlit/app.py
"""

import streamlit as st
import pandas as pd
from config import setup_sidebar

st.set_page_config(
    page_title="Gyrinx Analytics",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Gyrinx Analytics")

engine, start_date, date_trunc, time_range = setup_sidebar()


@st.cache_data(ttl=300)
def get_overview_stats(_engine):
    """Get high-level stats."""
    queries = {
        "users": "SELECT count(*) FROM auth_user",
        "lists": "SELECT count(*) FROM core_list WHERE archived = false",
        "fighters": "SELECT count(*) FROM core_listfighter WHERE archived = false",
        "campaigns": "SELECT count(*) FROM core_campaign WHERE archived = false",
    }
    stats = {}
    for name, query in queries.items():
        df = pd.read_sql(query, _engine)
        stats[name] = df.iloc[0, 0]
    return stats


stats = get_overview_stats(engine)

st.header("Overview")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Users", f"{stats['users']:,}")
with col2:
    st.metric("Active Lists", f"{stats['lists']:,}")
with col3:
    st.metric("Active Fighters", f"{stats['fighters']:,}")
with col4:
    st.metric("Active Campaigns", f"{stats['campaigns']:,}")

st.divider()

st.markdown("""
### Pages

- **Events** - Track user activity events over time
- **User Signups** - Monitor user registration trends

Use the sidebar to select a database snapshot and time range.
""")
