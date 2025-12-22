"""Most active lists and campaigns."""

import streamlit as st
import pandas as pd
import plotly.express as px
from config import setup_sidebar

st.set_page_config(page_title="Active Lists & Campaigns", page_icon="🔥", layout="wide")
st.title("🔥 Most Active Lists & Campaigns")

engine, start_date, date_trunc, time_range = setup_sidebar()


@st.cache_data(ttl=300)
def get_active_lists(_engine, start_date, limit=20):
    """Get most active lists by event count."""
    where_clause = ""
    if start_date:
        where_clause = f"AND e.created >= '{start_date.isoformat()}'"

    query = f"""
        SELECT
            l.id,
            l.name as list_name,
            h.name as house,
            u.username as owner,
            count(*) as event_count
        FROM core_event e
        JOIN core_list l ON e.object_id = l.id
        JOIN content_contenthouse h ON l.content_house_id = h.id
        LEFT JOIN auth_user u ON l.owner_id = u.id
        WHERE e.noun IN ('list', 'list_fighter', 'equipment_assignment')
        {where_clause}
        GROUP BY l.id, l.name, h.name, u.username
        ORDER BY count(*) DESC
        LIMIT {limit}
    """  # nosec B608 - values from controlled UI, not user text input
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_active_campaigns(_engine, start_date, limit=20):
    """Get most active campaigns by event count."""
    where_clause = ""
    if start_date:
        where_clause = f"AND e.created >= '{start_date.isoformat()}'"

    query = f"""
        SELECT
            c.id,
            c.name as campaign_name,
            u.username as owner,
            count(*) as event_count
        FROM core_event e
        JOIN core_campaign c ON e.object_id = c.id
        LEFT JOIN auth_user u ON c.owner_id = u.id
        WHERE e.noun IN ('campaign', 'campaign_asset', 'campaign_action', 'campaign_resource', 'campaign_invitation', 'battle')
        {where_clause}
        GROUP BY c.id, c.name, u.username
        ORDER BY count(*) DESC
        LIMIT {limit}
    """  # nosec B608 - values from controlled UI, not user text input
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_list_activity_over_time(_engine, list_ids, start_date, date_trunc):
    """Get activity over time for specific lists."""
    if not list_ids:
        return pd.DataFrame()

    ids_str = ",".join([f"'{id}'" for id in list_ids])
    where_clause = f"WHERE e.object_id IN ({ids_str})"
    if start_date:
        where_clause += f" AND e.created >= '{start_date.isoformat()}'"

    query = f"""
        SELECT
            date_trunc('{date_trunc}', e.created) as period,
            l.name as list_name,
            count(*) as events
        FROM core_event e
        JOIN core_list l ON e.object_id = l.id
        {where_clause}
        GROUP BY 1, l.name
        ORDER BY 1
    """  # nosec B608 - values from controlled UI/DB, not user text input
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_campaign_activity_over_time(_engine, campaign_ids, start_date, date_trunc):
    """Get activity over time for specific campaigns."""
    if not campaign_ids:
        return pd.DataFrame()

    ids_str = ",".join([f"'{id}'" for id in campaign_ids])
    where_clause = f"WHERE e.object_id IN ({ids_str})"
    if start_date:
        where_clause += f" AND e.created >= '{start_date.isoformat()}'"

    query = f"""
        SELECT
            date_trunc('{date_trunc}', e.created) as period,
            c.name as campaign_name,
            count(*) as events
        FROM core_event e
        JOIN core_campaign c ON e.object_id = c.id
        {where_clause}
        GROUP BY 1, c.name
        ORDER BY 1
    """  # nosec B608 - values from controlled UI/DB, not user text input
    return pd.read_sql(query, _engine)


# Lists section
st.header("Most Active Lists")

df_lists = get_active_lists(engine, start_date)

if df_lists.empty:
    st.info("No list activity found for the selected time range.")
else:
    col1, col2 = st.columns([1, 2])

    with col1:
        # Add URL column
        df_lists_display = df_lists.copy()
        df_lists_display["url"] = df_lists_display["id"].apply(
            lambda x: f"https://gyrinx.app/list/{x}"
        )
        st.dataframe(
            df_lists_display[["list_name", "house", "owner", "event_count", "url"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "list_name": "List",
                "url": st.column_config.LinkColumn("Link", display_text="Open"),
            },
        )

    with col2:
        # Get top 5 for chart
        top_list_ids = df_lists.head(5)["id"].tolist()
        df_list_time = get_list_activity_over_time(
            engine, top_list_ids, start_date, date_trunc
        )

        if not df_list_time.empty:
            fig = px.bar(
                df_list_time,
                x="period",
                y="events",
                color="list_name",
                title="Top 5 lists activity over time",
                labels={"period": "Date", "events": "Events", "list_name": "List"},
                barmode="stack",
            )
            fig.update_layout(
                height=400, legend=dict(orientation="h", yanchor="bottom", y=-0.3)
            )
            st.plotly_chart(fig, use_container_width=True)


st.divider()


# Campaigns section
st.header("Most Active Campaigns")

df_campaigns = get_active_campaigns(engine, start_date)

if df_campaigns.empty:
    st.info("No campaign activity found for the selected time range.")
else:
    col1, col2 = st.columns([1, 2])

    with col1:
        # Add URL column
        df_campaigns_display = df_campaigns.copy()
        df_campaigns_display["url"] = df_campaigns_display["id"].apply(
            lambda x: f"https://gyrinx.app/campaign/{x}"
        )
        st.dataframe(
            df_campaigns_display[["campaign_name", "owner", "event_count", "url"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "campaign_name": "Campaign",
                "url": st.column_config.LinkColumn("Link", display_text="Open"),
            },
        )

    with col2:
        # Get top 5 for chart
        top_campaign_ids = df_campaigns.head(5)["id"].tolist()
        df_campaign_time = get_campaign_activity_over_time(
            engine, top_campaign_ids, start_date, date_trunc
        )

        if not df_campaign_time.empty:
            fig = px.bar(
                df_campaign_time,
                x="period",
                y="events",
                color="campaign_name",
                title="Top 5 campaigns activity over time",
                labels={
                    "period": "Date",
                    "events": "Events",
                    "campaign_name": "Campaign",
                },
                barmode="stack",
            )
            fig.update_layout(
                height=400, legend=dict(orientation="h", yanchor="bottom", y=-0.3)
            )
            st.plotly_chart(fig, use_container_width=True)
