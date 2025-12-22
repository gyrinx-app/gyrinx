"""Cached facts analysis - lists with dirty=False."""

import streamlit as st
import pandas as pd
from config import setup_sidebar

st.set_page_config(page_title="Cached Facts", page_icon="💾", layout="wide")
st.title("💾 Cached Facts (dirty=False)")
st.caption("Analysis of lists with cached rating/stash/credits values")

engine, start_date, date_trunc, time_range = setup_sidebar()


@st.cache_data(ttl=300)
def get_dirty_stats(_engine):
    """Get proportion of lists by dirty status."""
    query = """
        SELECT
            dirty,
            count(*) as count
        FROM core_list
        WHERE archived = false
        GROUP BY dirty
    """
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_clean_lists(_engine, limit=100):
    """Get lists with dirty=False and their cached facts."""
    query = f"""
        SELECT
            l.id,
            l.name as list_name,
            h.name as house,
            u.username as owner,
            l.rating_current,
            l.stash_current,
            l.credits_current,
            l.rating_current + l.stash_current + l.credits_current as wealth_current,
            (SELECT count(*) FROM core_listfighter lf
             WHERE lf.list_id = l.id AND lf.archived = false) as fighter_count
        FROM core_list l
        JOIN content_contenthouse h ON l.content_house_id = h.id
        LEFT JOIN auth_user u ON l.owner_id = u.id
        WHERE l.archived = false AND l.dirty = false
        ORDER BY l.rating_current DESC
        LIMIT {limit}
    """  # nosec B608 - limit is controlled integer from slider
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_dirty_lists(_engine, limit=50):
    """Get sample of lists with dirty=True."""
    query = f"""
        SELECT
            l.id,
            l.name as list_name,
            h.name as house,
            u.username as owner,
            (SELECT count(*) FROM core_listfighter lf
             WHERE lf.list_id = l.id AND lf.archived = false) as fighter_count
        FROM core_list l
        JOIN content_contenthouse h ON l.content_house_id = h.id
        LEFT JOIN auth_user u ON l.owner_id = u.id
        WHERE l.archived = false AND l.dirty = true
        ORDER BY l.created DESC
        LIMIT {limit}
    """  # nosec B608 - limit is controlled integer
    return pd.read_sql(query, _engine)


# Overview stats
st.header("Dirty Status Overview")

df_stats = get_dirty_stats(engine)

if df_stats.empty:
    st.info("No lists found.")
else:
    total = df_stats["count"].sum()
    clean_count = (
        df_stats[~df_stats["dirty"]]["count"].sum()
        if False in df_stats["dirty"].values
        else 0
    )
    dirty_count = (
        df_stats[df_stats["dirty"]]["count"].sum()
        if True in df_stats["dirty"].values
        else 0
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Active Lists", f"{total:,}")
    with col2:
        pct_clean = 100 * clean_count / total if total > 0 else 0
        st.metric("Clean (dirty=False)", f"{clean_count:,}", f"{pct_clean:.1f}%")
    with col3:
        pct_dirty = 100 * dirty_count / total if total > 0 else 0
        st.metric("Dirty (dirty=True)", f"{dirty_count:,}", f"{pct_dirty:.1f}%")
    with col4:
        st.metric("Clean Ratio", f"{pct_clean:.1f}%")

st.divider()

# Clean lists with facts
st.header("Lists with Cached Facts (dirty=False)")
st.caption("These lists have valid cached rating/stash/credits values from facts()")

limit = st.slider("Number of lists to show", 10, 200, 100)
df_clean = get_clean_lists(engine, limit)

if df_clean.empty:
    st.warning("No lists with dirty=False found.")
else:
    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Avg Rating", f"{df_clean['rating_current'].mean():,.0f}")
    with col2:
        st.metric("Avg Stash", f"{df_clean['stash_current'].mean():,.0f}")
    with col3:
        st.metric("Avg Credits", f"{df_clean['credits_current'].mean():,.0f}")
    with col4:
        st.metric("Avg Wealth", f"{df_clean['wealth_current'].mean():,.0f}")

    # Add URL column
    df_clean["url"] = df_clean["id"].apply(lambda x: f"https://gyrinx.app/list/{x}")

    st.dataframe(
        df_clean[
            [
                "list_name",
                "house",
                "owner",
                "fighter_count",
                "rating_current",
                "stash_current",
                "credits_current",
                "wealth_current",
                "url",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "list_name": "List",
            "house": "House",
            "owner": "Owner",
            "fighter_count": "Fighters",
            "rating_current": st.column_config.NumberColumn("Rating", format="%d"),
            "stash_current": st.column_config.NumberColumn("Stash", format="%d"),
            "credits_current": st.column_config.NumberColumn("Credits", format="%d"),
            "wealth_current": st.column_config.NumberColumn("Wealth", format="%d"),
            "url": st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )

    # Distribution charts
    st.subheader("Distribution of Cached Values")

    col1, col2 = st.columns(2)
    with col1:
        import plotly.express as px

        fig = px.histogram(
            df_clean,
            x="rating_current",
            nbins=30,
            title="Rating Distribution",
            labels={"rating_current": "Rating"},
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.histogram(
            df_clean,
            x="wealth_current",
            nbins=30,
            title="Wealth Distribution",
            labels={"wealth_current": "Wealth (rating + stash + credits)"},
        )
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# Sample of dirty lists
st.header("Sample Dirty Lists (dirty=True)")
st.caption("These lists need facts_from_db() to refresh cached values")

df_dirty = get_dirty_lists(engine)

if df_dirty.empty:
    st.success("No dirty lists found - all caches are up to date!")
else:
    df_dirty["url"] = df_dirty["id"].apply(lambda x: f"https://gyrinx.app/list/{x}")

    st.dataframe(
        df_dirty[["list_name", "house", "owner", "fighter_count", "url"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "list_name": "List",
            "house": "House",
            "owner": "Owner",
            "fighter_count": "Fighters",
            "url": st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )
