"""Shared configuration for the analytics dashboard."""

import streamlit as st
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

DB_HOST = "localhost"
DB_PORT = 5433
DB_USER = "postgres"
DB_PASSWORD = "postgres"  # nosec B105 - local dev only


@st.cache_resource
def get_engine(db_name: str):
    """Create a cached database connection."""
    return create_engine(
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{db_name}"
    )


def get_available_databases() -> list[str]:
    """List available dump databases."""
    engine = create_engine(
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/postgres"
    )
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT datname FROM pg_database WHERE datname LIKE 'dump_%' ORDER BY datname DESC"
            )
        )
        return [row[0] for row in result]


def setup_sidebar():
    """Set up common sidebar controls. Returns (engine, start_date, date_trunc, time_range)."""
    st.sidebar.header("Settings")

    databases = get_available_databases()
    if not databases:
        st.error(
            "No analytics databases found. Run ./scripts/analytics_restore.sh first."
        )
        st.stop()

    selected_db = st.sidebar.selectbox("Database", databases, index=0)
    engine = get_engine(selected_db)

    st.sidebar.subheader("Time Range")
    time_range = st.sidebar.radio(
        "Period",
        ["Last 7 days", "Last 30 days", "Last 90 days", "Last 12 months", "All time"],
        index=1,
    )

    now = datetime.now()
    if time_range == "Last 7 days":
        start_date = now - timedelta(days=7)
        date_trunc = "day"
    elif time_range == "Last 30 days":
        start_date = now - timedelta(days=30)
        date_trunc = "day"
    elif time_range == "Last 90 days":
        start_date = now - timedelta(days=90)
        date_trunc = "day"
    elif time_range == "Last 12 months":
        start_date = now - timedelta(days=365)
        date_trunc = "week"
    else:
        start_date = None
        date_trunc = "week"

    return engine, start_date, date_trunc, time_range
