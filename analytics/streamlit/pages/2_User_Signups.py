"""User signups analytics page."""

import streamlit as st
import pandas as pd
import plotly.express as px
from config import setup_sidebar

st.set_page_config(page_title="User Signups", page_icon="👥", layout="wide")
st.title("👥 User Signups")

engine, start_date, date_trunc, time_range = setup_sidebar()


@st.cache_data(ttl=300)
def get_user_signups(_engine, start_date, date_trunc):
    """Get user signup counts over time."""
    where_clause = ""
    if start_date:
        where_clause = f"WHERE date_joined >= '{start_date.isoformat()}'"

    query = f"""
        SELECT
            date_trunc('{date_trunc}', date_joined) as period,
            count(*) as signups
        FROM auth_user
        {where_clause}
        GROUP BY 1
        ORDER BY 1
    """  # nosec B608 - values from controlled UI, not user text input
    return pd.read_sql(query, _engine)


df_signups = get_user_signups(engine, start_date, date_trunc)

if df_signups.empty:
    st.info("No signups found for the selected time range.")
else:
    fig = px.bar(
        df_signups,
        x="period",
        y="signups",
        title=f"User signups ({time_range.lower()})",
        labels={"period": "Date", "signups": "Signups"},
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # Summary stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Signups", f"{df_signups['signups'].sum():,}")
    with col2:
        avg_per_period = df_signups["signups"].mean()
        st.metric(f"Avg per {date_trunc}", f"{avg_per_period:,.1f}")
    with col3:
        max_signups = df_signups["signups"].max()
        st.metric(f"Peak {date_trunc}", f"{max_signups:,}")

    # Data table
    with st.expander("View raw data"):
        st.dataframe(df_signups, use_container_width=True)
