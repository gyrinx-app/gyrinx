"""Lore/narrative usage analysis."""

import streamlit as st
import pandas as pd
from config import setup_sidebar

st.set_page_config(page_title="Lore Usage", page_icon="📖", layout="wide")
st.title("📖 Lore Usage")
st.caption("Lists and fighters with narrative/about text filled in")

engine, start_date, date_trunc, time_range = setup_sidebar()


@st.cache_data(ttl=300)
def get_lore_stats(_engine, min_fighters=3):
    """Get lists ranked by % of fighters with lore."""
    query = f"""
        WITH fighter_stats AS (
            SELECT
                l.id as list_id,
                l.name as list_name,
                l.narrative as list_narrative,
                h.name as house,
                u.username as owner,
                count(*) as total_fighters,
                count(*) FILTER (WHERE lf.narrative <> '') as fighters_with_lore,
                sum(length(lf.narrative)) as total_fighter_lore_chars
            FROM core_list l
            JOIN content_contenthouse h ON l.content_house_id = h.id
            LEFT JOIN auth_user u ON l.owner_id = u.id
            LEFT JOIN core_listfighter lf ON lf.list_id = l.id AND lf.archived = false
            WHERE l.archived = false
            GROUP BY l.id, l.name, l.narrative, h.name, u.username
        )
        SELECT
            list_id,
            list_name,
            house,
            owner,
            list_narrative <> '' as list_has_lore,
            length(list_narrative) as list_lore_chars,
            total_fighters,
            fighters_with_lore,
            total_fighter_lore_chars,
            CASE
                WHEN total_fighters > 0
                THEN round(100.0 * fighters_with_lore / total_fighters, 1)
                ELSE 0
            END as pct_fighters_with_lore
        FROM fighter_stats
        WHERE total_fighters >= {min_fighters}
        ORDER BY pct_fighters_with_lore DESC, fighters_with_lore DESC
        LIMIT 50
    """  # nosec B608 - min_fighters from slider, not user text input
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_overall_stats(_engine):
    """Get overall lore usage stats."""
    query = """
        SELECT
            (SELECT count(*) FROM core_list WHERE archived = false) as total_lists,
            (SELECT count(*) FROM core_list WHERE archived = false AND narrative <> '') as lists_with_lore,
            (SELECT count(*) FROM core_listfighter WHERE archived = false) as total_fighters,
            (SELECT count(*) FROM core_listfighter WHERE archived = false AND narrative <> '') as fighters_with_lore
    """
    return pd.read_sql(query, _engine).iloc[0]


# Overall stats
stats = get_overall_stats(engine)

st.header("Overall Stats")
col1, col2, col3, col4 = st.columns(4)
with col1:
    pct = (
        100 * stats["lists_with_lore"] / stats["total_lists"]
        if stats["total_lists"] > 0
        else 0
    )
    st.metric("Lists with Lore", f"{stats['lists_with_lore']:,}", f"{pct:.1f}%")
with col2:
    st.metric("Total Lists", f"{stats['total_lists']:,}")
with col3:
    pct = (
        100 * stats["fighters_with_lore"] / stats["total_fighters"]
        if stats["total_fighters"] > 0
        else 0
    )
    st.metric("Fighters with Lore", f"{stats['fighters_with_lore']:,}", f"{pct:.1f}%")
with col4:
    st.metric("Total Fighters", f"{stats['total_fighters']:,}")

st.divider()

# Top lists by lore usage
st.header("Top Lists by Lore Usage")

min_fighters = st.slider("Minimum fighters in list", 1, 20, 3)
df_lore = get_lore_stats(engine, min_fighters)

if df_lore.empty:
    st.info("No lists found matching criteria.")
else:
    # Add URL column
    df_lore["url"] = df_lore["list_id"].apply(lambda x: f"https://gyrinx.app/list/{x}")

    # Format for display
    df_display = df_lore[
        [
            "list_name",
            "house",
            "owner",
            "list_has_lore",
            "fighters_with_lore",
            "total_fighters",
            "pct_fighters_with_lore",
            "url",
        ]
    ].copy()

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "list_name": "List",
            "house": "House",
            "owner": "Owner",
            "list_has_lore": st.column_config.CheckboxColumn("List Lore?"),
            "fighters_with_lore": "Fighters w/ Lore",
            "total_fighters": "Total Fighters",
            "pct_fighters_with_lore": st.column_config.ProgressColumn(
                "% Fighters w/ Lore",
                min_value=0,
                max_value=100,
                format="%.1f%%",
            ),
            "url": st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )

    # Summary cards for top 3
    st.subheader("Top 3 Most Lore-Rich Lists")
    cols = st.columns(3)
    for i, (_, row) in enumerate(df_lore.head(3).iterrows()):
        with cols[i]:
            st.markdown(f"""
**{row["list_name"]}**
*{row["house"]}* by {row["owner"] or "Anonymous"}

- {"✅" if row["list_has_lore"] else "❌"} List has lore ({row["list_lore_chars"]:,} chars)
- {row["fighters_with_lore"]}/{row["total_fighters"]} fighters with lore ({row["pct_fighters_with_lore"]}%)
- {row["total_fighter_lore_chars"]:,} total fighter lore chars

[Open list](https://gyrinx.app/list/{row["list_id"]})
""")
