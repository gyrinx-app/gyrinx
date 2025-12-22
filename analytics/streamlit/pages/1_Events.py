"""Events analytics page."""

import streamlit as st
import pandas as pd
import plotly.express as px
from config import setup_sidebar

st.set_page_config(page_title="Events", page_icon="📊", layout="wide")
st.title("📊 Events by Type")

engine, start_date, date_trunc, time_range = setup_sidebar()


@st.cache_data(ttl=300)
def get_events_by_type(_engine, start_date, date_trunc):
    """Get event counts grouped by type and time period."""
    where_clause = ""
    if start_date:
        where_clause = f"WHERE created >= '{start_date.isoformat()}'"

    query = f"""
        SELECT
            date_trunc('{date_trunc}', created) as period,
            noun || '.' || verb as event_type,
            count(*) as count
        FROM core_event
        {where_clause}
        GROUP BY 1, 2
        ORDER BY 1, 2
    """  # nosec B608 - values from controlled UI, not user text input
    return pd.read_sql(query, _engine)


df_events = get_events_by_type(engine, start_date, date_trunc)

if df_events.empty:
    st.info("No events found for the selected time range.")
else:
    # Get all event types
    all_types = sorted(df_events["event_type"].unique())

    # Default to top 5 by count
    top_by_count = (
        df_events.groupby("event_type")["count"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .index.tolist()
    )

    selected_types = st.multiselect(
        "Event Types",
        options=all_types,
        default=top_by_count,
        help="Select which event types to display",
    )

    if selected_types:
        df_filtered = df_events[df_events["event_type"].isin(selected_types)]

        fig = px.line(
            df_filtered,
            x="period",
            y="count",
            color="event_type",
            title=f"Events over time ({time_range.lower()})",
            labels={"period": "Date", "count": "Count", "event_type": "Event Type"},
        )
        fig.update_layout(
            height=500, legend=dict(orientation="h", yanchor="bottom", y=-0.3)
        )
        st.plotly_chart(fig, use_container_width=True)

        # Summary stats
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Events", f"{df_filtered['count'].sum():,}")
        with col2:
            st.metric("Event Types", len(selected_types))
        with col3:
            avg_per_period = df_filtered.groupby("period")["count"].sum().mean()
            st.metric(f"Avg per {date_trunc}", f"{avg_per_period:,.0f}")

        # Data table
        with st.expander("View raw data"):
            pivot = df_filtered.pivot(
                index="period", columns="event_type", values="count"
            ).fillna(0)
            st.dataframe(pivot, use_container_width=True)
