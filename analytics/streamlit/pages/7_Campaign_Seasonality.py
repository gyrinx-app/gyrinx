"""
Campaign Seasonality & Community Activity Analysis

Investigates two hypotheses:
1. The community goes quiet between campaign seasons
2. Campaigns run end-to-end in around 6 weeks
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import setup_sidebar
from sqlalchemy import text

st.set_page_config(page_title="Campaign Seasonality", page_icon="📅", layout="wide")
st.title("📅 Campaign Seasonality & Community Activity")

engine, start_date, date_trunc, time_range = setup_sidebar()


# --- Data Loading ---


@st.cache_data(ttl=300)
def load_campaign_data(_engine):
    """Load campaign lifecycle data."""
    query = text("""
        SELECT
            c.id,
            c.name,
            c.created,
            c.status,
            c.archived,
            count(DISTINCT cl.list_id) as list_count,
            count(DISTINCT l.owner_id) as player_count,
            min(b.date) as first_battle,
            max(b.date) as last_battle,
            count(DISTINCT b.id) as battle_count
        FROM core_campaign c
        LEFT JOIN core_campaign_lists cl ON c.id = cl.campaign_id
        LEFT JOIN core_list l ON cl.list_id = l.id
        LEFT JOIN core_battle b ON b.campaign_id = c.id AND b.archived = false
        GROUP BY c.id, c.name, c.created, c.status, c.archived
        ORDER BY c.created
    """)
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def load_weekly_active_users(_engine):
    """Load weekly active user counts from events."""
    query = text("""
        SELECT
            date_trunc('week', created) as week,
            count(DISTINCT owner_id) as active_users,
            count(*) as total_events
        FROM core_event
        WHERE owner_id IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def load_user_weekly_activity(_engine):
    """Load per-user weekly activity for gap analysis."""
    query = text("""
        SELECT
            owner_id as user_id,
            date_trunc('week', created) as week,
            count(*) as events
        FROM core_event
        WHERE owner_id IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def load_campaign_activity(_engine):
    """Load weekly activity broken down by campaign vs non-campaign context."""
    query = text("""
        SELECT
            date_trunc('week', e.created) as week,
            CASE
                WHEN e.noun = 'campaign' THEN 'campaign_mgmt'
                WHEN e.noun IN ('list', 'list_fighter', 'equipment_assignment', 'skill_assignment')
                    AND e.verb IN ('create', 'update', 'clone') THEN 'list_building'
                WHEN e.noun = 'battle' THEN 'battle'
                WHEN e.noun IN ('campaign_action', 'campaign_resource', 'campaign_asset')
                    THEN 'campaign_play'
                ELSE 'other'
            END as activity_type,
            count(*) as events,
            count(DISTINCT e.owner_id) as users
        FROM core_event e
        WHERE e.owner_id IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)
    return pd.read_sql(query, _engine)


# --- Load Data ---

campaigns_df = load_campaign_data(engine)
wau_df = load_weekly_active_users(engine)
user_weekly_df = load_user_weekly_activity(engine)
campaign_activity_df = load_campaign_activity(engine)

# --- Analysis ---

st.header("Headline Findings")

# Campaign duration analysis
campaigns_with_battles = campaigns_df[campaigns_df["battle_count"] > 0].copy()
campaigns_with_battles["first_battle"] = pd.to_datetime(
    campaigns_with_battles["first_battle"]
)
campaigns_with_battles["last_battle"] = pd.to_datetime(
    campaigns_with_battles["last_battle"]
)
campaigns_with_battles["duration_days"] = (
    campaigns_with_battles["last_battle"] - campaigns_with_battles["first_battle"]
).dt.days
campaigns_with_battles["duration_weeks"] = campaigns_with_battles["duration_days"] / 7

# Filter to campaigns with at least 2 battles and reasonable duration (<2 years)
multi_battle = campaigns_with_battles[
    (campaigns_with_battles["battle_count"] >= 2)
    & (campaigns_with_battles["duration_days"] <= 730)
    & (campaigns_with_battles["duration_days"] >= 0)
]

# User gap analysis
user_weekly_df["week"] = pd.to_datetime(user_weekly_df["week"])
user_gaps = []
for user_id, group in user_weekly_df.groupby("user_id"):
    weeks = group["week"].sort_values()
    if len(weeks) < 2:
        continue
    diffs = weeks.diff().dropna().dt.days / 7  # gaps in weeks
    max_gap = diffs.max()
    mean_gap = diffs.mean()
    active_weeks = len(weeks)
    total_span = (weeks.max() - weeks.min()).days / 7
    user_gaps.append(
        {
            "user_id": user_id,
            "active_weeks": active_weeks,
            "total_span_weeks": total_span,
            "max_gap_weeks": max_gap,
            "mean_gap_weeks": mean_gap,
        }
    )
user_gaps_df = pd.DataFrame(user_gaps)

# --- Display Headlines ---

col1, col2 = st.columns(2)

with col1:
    st.subheader("Do campaigns run ~6 weeks?")
    if len(multi_battle) > 0:
        median_weeks = multi_battle["duration_weeks"].median()
        mean_weeks = multi_battle["duration_weeks"].mean()
        p25 = multi_battle["duration_weeks"].quantile(0.25)
        p75 = multi_battle["duration_weeks"].quantile(0.75)

        if median_weeks < 8:
            st.success(
                f"**Partially validated.** Median campaign duration is **{median_weeks:.1f} weeks** "
                f"(mean {mean_weeks:.1f} weeks). Middle 50% run {p25:.0f}–{p75:.0f} weeks."
            )
        else:
            st.warning(
                f"**Not validated.** Median campaign duration is **{median_weeks:.1f} weeks** — "
                f"longer than the 6-week hypothesis."
            )

        st.metric("Median duration", f"{median_weeks:.1f} weeks")
        st.metric("Campaigns with battles", f"{len(multi_battle)}")
        st.metric("Range (25th–75th percentile)", f"{p25:.0f}–{p75:.0f} weeks")
    else:
        st.warning("Not enough campaigns with multiple battles to analyze.")

with col2:
    st.subheader("Do users go quiet between seasons?")
    if len(user_gaps_df) > 0:
        # Users with long gaps (>4 weeks)
        long_gap_users = user_gaps_df[user_gaps_df["max_gap_weeks"] > 4]
        pct_with_long_gaps = len(long_gap_users) / len(user_gaps_df) * 100

        # Users who return after a gap
        returners = user_gaps_df[
            (user_gaps_df["max_gap_weeks"] > 4) & (user_gaps_df["active_weeks"] > 3)
        ]
        pct_returners = (
            len(returners) / len(long_gap_users) * 100 if len(long_gap_users) > 0 else 0
        )

        median_max_gap = user_gaps_df["max_gap_weeks"].median()

        st.info(
            f"**{pct_with_long_gaps:.0f}%** of users have a gap of 4+ weeks in their activity. "
            f"Of those, **{pct_returners:.0f}%** return and are active for 3+ weeks total. "
            f"Median longest gap: **{median_max_gap:.0f} weeks**. "
            f"This is consistent with seasonal play, but could also be natural churn."
        )

        st.metric("Users with 4+ week gaps", f"{pct_with_long_gaps:.0f}%")
        st.metric("Returners (3+ active weeks)", f"{pct_returners:.0f}%")
        st.metric("Median max gap", f"{median_max_gap:.0f} weeks")
    else:
        st.warning("Not enough user activity data to analyze gaps.")

# --- Charts ---

st.divider()
st.header("Campaign Duration Distribution")

if len(multi_battle) > 0:
    fig = px.histogram(
        multi_battle,
        x="duration_weeks",
        nbins=30,
        title="Campaign Duration (first battle to last battle)",
        labels={"duration_weeks": "Duration (weeks)", "count": "Campaigns"},
    )
    fig.add_vline(
        x=6,
        line_dash="dash",
        line_color="red",
        annotation_text="6 week hypothesis",
    )
    fig.add_vline(
        x=multi_battle["duration_weeks"].median(),
        line_dash="dash",
        line_color="green",
        annotation_text=f"Median: {multi_battle['duration_weeks'].median():.1f}w",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Show the actual campaigns
    with st.expander("Campaign details"):
        display_cols = [
            "name",
            "status",
            "player_count",
            "battle_count",
            "duration_weeks",
            "first_battle",
            "last_battle",
        ]
        st.dataframe(
            multi_battle[display_cols]
            .sort_values("duration_weeks", ascending=False)
            .reset_index(drop=True),
            use_container_width=True,
        )

st.divider()
st.header("Weekly Active Users Over Time")

if len(wau_df) > 0:
    wau_df["week"] = pd.to_datetime(wau_df["week"])
    fig = px.line(
        wau_df,
        x="week",
        y="active_users",
        title="Weekly Active Users (users with at least one event)",
        labels={"week": "Week", "active_users": "Active Users"},
    )
    fig.update_traces(mode="lines+markers")
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.header("Activity by Type Over Time")

if len(campaign_activity_df) > 0:
    campaign_activity_df["week"] = pd.to_datetime(campaign_activity_df["week"])

    # Pivot for stacked area
    pivoted = campaign_activity_df.pivot_table(
        index="week", columns="activity_type", values="events", aggfunc="sum"
    ).fillna(0)

    fig = px.area(
        pivoted.reset_index(),
        x="week",
        y=[c for c in pivoted.columns],
        title="Weekly Events by Activity Type",
        labels={"value": "Events", "week": "Week"},
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.header("User Gap Analysis")

if len(user_gaps_df) > 0:
    fig = px.histogram(
        user_gaps_df,
        x="max_gap_weeks",
        nbins=40,
        title="Distribution of Longest Inactive Gap Per User",
        labels={"max_gap_weeks": "Longest Gap (weeks)", "count": "Users"},
    )
    fig.add_vline(
        x=4,
        line_dash="dash",
        line_color="orange",
        annotation_text="4 weeks (1 month)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Scatter: active weeks vs max gap
    fig2 = px.scatter(
        user_gaps_df,
        x="total_span_weeks",
        y="max_gap_weeks",
        size="active_weeks",
        title="User Engagement: Total Span vs Longest Gap",
        labels={
            "total_span_weeks": "Total Span (weeks)",
            "max_gap_weeks": "Longest Gap (weeks)",
            "active_weeks": "Active Weeks",
        },
        opacity=0.5,
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.header("Battle Activity Over Time")

if len(campaigns_df) > 0:
    # Battles per week with campaign overlay
    query = text("""
        SELECT
            date_trunc('week', b.date) as week,
            count(*) as battles,
            count(DISTINCT b.campaign_id) as campaigns_with_battles
        FROM core_battle b
        WHERE b.archived = false
          AND b.date >= '2024-01-01'
          AND b.date <= now()
        GROUP BY 1
        ORDER BY 1
    """)
    battle_weekly = pd.read_sql(query, engine)
    if len(battle_weekly) > 0:
        battle_weekly["week"] = pd.to_datetime(battle_weekly["week"])
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=battle_weekly["week"],
                y=battle_weekly["battles"],
                name="Battles",
                opacity=0.7,
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=battle_weekly["week"],
                y=battle_weekly["campaigns_with_battles"],
                name="Active Campaigns",
                mode="lines+markers",
            ),
            secondary_y=True,
        )
        fig.update_layout(title="Weekly Battles and Active Campaigns")
        fig.update_yaxes(title_text="Battles", secondary_y=False)
        fig.update_yaxes(title_text="Active Campaigns", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption(
    "**Methodology:** Campaign duration = first battle date to last battle date. "
    "Only campaigns with 2+ battles are included in duration analysis. "
    "User gaps = weeks between consecutive weeks with at least one event. "
    "Data from the analytics database snapshot."
)
