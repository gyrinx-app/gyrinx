"""Content library changes analysis using django-simple-history tables."""

import streamlit as st
import pandas as pd
import plotly.express as px
from config import setup_sidebar

st.set_page_config(page_title="Content Library Changes", page_icon="📚", layout="wide")
st.title("📚 Content Library Changes")
st.caption("Historical changes to the content library tracked by django-simple-history")

engine, start_date, date_trunc, time_range = setup_sidebar()

# Models that affect costs (trigger dirty flags on user lists)
# These are the models whose cost changes propagate to ListFighter/ListFighterEquipmentAssignment
COST_AFFECTING_MODELS = {
    "content_historicalcontentequipment": ("ContentEquipment", "cost"),
    "content_historicalcontentfighter": ("ContentFighter", "base_cost"),
    "content_historicalcontentweaponprofile": ("ContentWeaponProfile", "cost"),
    "content_historicalcontentequipmentupgrade": ("ContentEquipmentUpgrade", "cost"),
    "content_historicalcontentweaponaccessory": ("ContentWeaponAccessory", "cost"),
    "content_historicalcontentfighterequipmentlistitem": (
        "ContentFighterEquipmentListItem",
        "cost",
    ),
    "content_historicalcontentfighterequipmentlistupgrade": (
        "ContentFighterEquipmentListUpgrade",
        "cost",
    ),
    "content_historicalcontentfighterequipmentlistweaponaccessory": (
        "ContentFighterEquipmentListWeaponAccessory",
        "cost",
    ),
    "content_historicalcontentequipmentlistexpansionitem": (
        "ContentEquipmentListExpansionItem",
        "cost_adjustment",
    ),
}

# All content history tables we want to track
# Format: (table_name, label, name_column) - name_column is the column to use for display name
ALL_CONTENT_TABLES = [
    ("content_historicalcontenthouse", "ContentHouse", "name"),
    (
        "content_historicalcontentfighter",
        "ContentFighter",
        "type",
    ),  # uses 'type' not 'name'
    ("content_historicalcontentequipment", "ContentEquipment", "name"),
    ("content_historicalcontentweaponprofile", "ContentWeaponProfile", "name"),
    ("content_historicalcontentweapontrait", "ContentWeaponTrait", "name"),
    ("content_historicalcontentweaponaccessory", "ContentWeaponAccessory", "name"),
    ("content_historicalcontentequipmentupgrade", "ContentEquipmentUpgrade", "name"),
    ("content_historicalcontentequipmentcategory", "ContentEquipmentCategory", "name"),
    ("content_historicalcontentskill", "ContentSkill", "name"),
    ("content_historicalcontentskillcategory", "ContentSkillCategory", "name"),
    ("content_historicalcontentinjury", "ContentInjury", "name"),
    ("content_historicalcontentinjurygroup", "ContentInjuryGroup", "name"),
    ("content_historicalcontentrule", "ContentRule", "name"),
    # These tables don't have a name column - use id::text as placeholder
    (
        "content_historicalcontentfighterdefaultassignment",
        "ContentFighterDefaultAssignment",
        None,
    ),
    (
        "content_historicalcontentfighterequipmentlistitem",
        "ContentFighterEquipmentListItem",
        None,
    ),
    (
        "content_historicalcontentfighterequipmentlistupgrade",
        "ContentFighterEquipmentListUpgrade",
        None,
    ),
    (
        "content_historicalcontentfighterequipmentlistweaponaccessory",
        "ContentFighterEquipmentListWeaponAccessory",
        None,
    ),
    (
        "content_historicalcontentequipmentlistexpansionitem",
        "ContentEquipmentListExpansionItem",
        None,
    ),
]

HISTORY_TYPE_LABELS = {"+": "Created", "~": "Updated", "-": "Deleted"}


@st.cache_data(ttl=300)
def get_content_changes_over_time(_engine, start_date, date_trunc):
    """Get content changes aggregated by model and time period."""
    unions = []
    for table, label, _name_col in ALL_CONTENT_TABLES:
        where_clause = ""
        if start_date:
            where_clause = f"WHERE history_date >= '{start_date.isoformat()}'"
        unions.append(f"""
            SELECT
                date_trunc('{date_trunc}', history_date) as period,
                '{label}' as model,
                history_type,
                count(*) as count
            FROM {table}
            {where_clause}
            GROUP BY 1, 2, 3
        """)  # nosec B608 - table names from controlled list, date_trunc from UI

    query = " UNION ALL ".join(unions) + " ORDER BY period, model"
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_overall_stats(_engine):
    """Get total counts for each content history table."""
    unions = []
    for table, label, _name_col in ALL_CONTENT_TABLES:
        unions.append(f"""
            SELECT '{label}' as model, count(*) as total_records
            FROM {table}
        """)  # nosec B608 - table names from controlled list

    query = " UNION ALL ".join(unions) + " ORDER BY total_records DESC"
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_cost_affecting_changes(_engine, start_date, date_trunc):
    """Get changes to cost-affecting models over time."""
    unions = []
    for table, (label, _cost_field) in COST_AFFECTING_MODELS.items():
        where_clause = ""
        if start_date:
            where_clause = f"WHERE history_date >= '{start_date.isoformat()}'"
        unions.append(f"""
            SELECT
                date_trunc('{date_trunc}', history_date) as period,
                '{label}' as model,
                history_type,
                count(*) as count
            FROM {table}
            {where_clause}
            GROUP BY 1, 2, 3
        """)  # nosec B608 - table names from controlled list, date_trunc from UI

    query = " UNION ALL ".join(unions) + " ORDER BY period, model"
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_recent_changes(_engine, limit=100):
    """Get most recent content changes with details."""
    unions = []
    for table, label, name_col in ALL_CONTENT_TABLES:
        # Use the appropriate column for name, or id if no name column exists
        name_expr = name_col if name_col else "id::text"
        unions.append(f"""
            SELECT
                history_date,
                '{label}' as model,
                history_type,
                {name_expr} as name,
                history_change_reason
            FROM {table}
        """)  # nosec B608 - table names from controlled list

    query = f"""
        WITH all_changes AS ({" UNION ALL ".join(unions)})
        SELECT * FROM all_changes
        ORDER BY history_date DESC
        LIMIT {limit}
    """  # nosec B608 - limit is from controlled slider
    return pd.read_sql(query, _engine)


@st.cache_data(ttl=300)
def get_cost_change_details(_engine, start_date, limit=50):
    """Get detailed cost changes for cost-affecting models."""
    # For ContentEquipment (cost is varchar)
    equipment_query = """
        SELECT
            h1.history_date,
            'ContentEquipment' as model,
            h1.name,
            h2.cost as old_cost,
            h1.cost as new_cost,
            h1.history_change_reason
        FROM content_historicalcontentequipment h1
        LEFT JOIN content_historicalcontentequipment h2
            ON h1.id = h2.id
            AND h2.history_id = (
                SELECT MAX(history_id)
                FROM content_historicalcontentequipment
                WHERE id = h1.id AND history_id < h1.history_id
            )
        WHERE h1.history_type = '~'
        AND h2.cost IS NOT NULL
        AND h1.cost != h2.cost
    """

    # For ContentFighter (base_cost is integer)
    fighter_query = """
        SELECT
            h1.history_date,
            'ContentFighter' as model,
            h1.type as name,
            h2.base_cost::text as old_cost,
            h1.base_cost::text as new_cost,
            h1.history_change_reason
        FROM content_historicalcontentfighter h1
        LEFT JOIN content_historicalcontentfighter h2
            ON h1.id = h2.id
            AND h2.history_id = (
                SELECT MAX(history_id)
                FROM content_historicalcontentfighter
                WHERE id = h1.id AND history_id < h1.history_id
            )
        WHERE h1.history_type = '~'
        AND h2.base_cost IS NOT NULL
        AND h1.base_cost != h2.base_cost
    """

    # For ContentWeaponProfile (cost is integer)
    weapon_query = """
        SELECT
            h1.history_date,
            'ContentWeaponProfile' as model,
            h1.name,
            h2.cost::text as old_cost,
            h1.cost::text as new_cost,
            h1.history_change_reason
        FROM content_historicalcontentweaponprofile h1
        LEFT JOIN content_historicalcontentweaponprofile h2
            ON h1.id = h2.id
            AND h2.history_id = (
                SELECT MAX(history_id)
                FROM content_historicalcontentweaponprofile
                WHERE id = h1.id AND history_id < h1.history_id
            )
        WHERE h1.history_type = '~'
        AND h2.cost IS NOT NULL
        AND h1.cost != h2.cost
    """

    where_clause = ""
    if start_date:
        where_clause = f"WHERE history_date >= '{start_date.isoformat()}'"

    query = f"""
        WITH cost_changes AS (
            {equipment_query}
            UNION ALL
            {fighter_query}
            UNION ALL
            {weapon_query}
        )
        SELECT * FROM cost_changes
        {where_clause}
        ORDER BY history_date DESC
        LIMIT {limit}
    """  # nosec B608 - limit is controlled integer
    return pd.read_sql(query, _engine)


# Overall Stats
st.header("Overview")
df_stats = get_overall_stats(engine)

if df_stats.empty:
    st.info("No historical content records found.")
else:
    total_records = df_stats["total_records"].sum()
    top_model = df_stats.iloc[0]["model"]
    top_count = df_stats.iloc[0]["total_records"]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total History Records", f"{total_records:,}")
    with col2:
        st.metric("Models Tracked", len(df_stats))
    with col3:
        st.metric("Most Changed", f"{top_model} ({top_count:,})")

    with st.expander("Records by model"):
        st.dataframe(
            df_stats,
            use_container_width=True,
            hide_index=True,
            column_config={
                "model": "Model",
                "total_records": st.column_config.NumberColumn(
                    "Total Records", format="%d"
                ),
            },
        )

st.divider()

# Content changes over time
st.header("Content Changes Over Time")

df_changes = get_content_changes_over_time(engine, start_date, date_trunc)

if df_changes.empty:
    st.info("No content changes found for the selected time range.")
else:
    # Aggregate by period and model (ignore history_type for main chart)
    df_agg = df_changes.groupby(["period", "model"])["count"].sum().reset_index()

    # Let user select models (all selected by default, sorted alphabetically)
    all_models = sorted(df_agg["model"].unique())

    selected_models = st.multiselect(
        "Models to display",
        options=all_models,
        default=all_models,
        help="Select which content models to show",
    )

    if selected_models:
        df_filtered = df_agg[df_agg["model"].isin(selected_models)]

        fig = px.bar(
            df_filtered,
            x="period",
            y="count",
            color="model",
            title=f"Content changes over time ({time_range.lower()})",
            labels={"period": "Date", "count": "Changes", "model": "Model"},
            barmode="stack",
        )
        fig.update_layout(
            height=500, legend=dict(orientation="h", yanchor="bottom", y=-0.3)
        )
        st.plotly_chart(fig, use_container_width=True)

        # By history type
        col1, col2 = st.columns(2)
        with col1:
            df_by_type = df_changes[df_changes["model"].isin(selected_models)].copy()
            df_by_type["history_type_label"] = df_by_type["history_type"].map(
                HISTORY_TYPE_LABELS
            )
            type_totals = (
                df_by_type.groupby("history_type_label")["count"].sum().reset_index()
            )

            fig_type = px.pie(
                type_totals,
                values="count",
                names="history_type_label",
                title="Changes by Type",
                color="history_type_label",
                color_discrete_map={
                    "Created": "#28a745",
                    "Updated": "#ffc107",
                    "Deleted": "#dc3545",
                },
            )
            st.plotly_chart(fig_type, use_container_width=True)

        with col2:
            model_totals = df_filtered.groupby("model")["count"].sum().reset_index()
            model_totals = model_totals.sort_values("count", ascending=True)

            fig_model = px.bar(
                model_totals,
                x="count",
                y="model",
                orientation="h",
                title="Total Changes by Model",
                labels={"count": "Changes", "model": "Model"},
            )
            st.plotly_chart(fig_model, use_container_width=True)

st.divider()

# Cost-affecting changes
st.header("Cost-Affecting Changes")
st.caption(
    "Changes to these models trigger dirty flags on user lists, requiring cost recalculation"
)

df_cost = get_cost_affecting_changes(engine, start_date, date_trunc)

if df_cost.empty:
    st.info("No cost-affecting changes found for the selected time range.")
else:
    df_cost_agg = df_cost.groupby(["period", "model"])["count"].sum().reset_index()

    # Summary metrics
    total_cost_changes = df_cost_agg["count"].sum()
    models_with_changes = df_cost_agg["model"].nunique()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Cost-Affecting Changes", f"{total_cost_changes:,}")
    with col2:
        st.metric("Models with Changes", models_with_changes)
    with col3:
        # Updates only (excluding creates/deletes)
        updates_only = df_cost[df_cost["history_type"] == "~"]["count"].sum()
        st.metric("Updates (potential cost changes)", f"{updates_only:,}")

    fig_cost = px.area(
        df_cost_agg,
        x="period",
        y="count",
        color="model",
        title=f"Cost-affecting changes over time ({time_range.lower()})",
        labels={"period": "Date", "count": "Changes", "model": "Model"},
    )
    fig_cost.update_layout(
        height=400, legend=dict(orientation="h", yanchor="bottom", y=-0.3)
    )
    st.plotly_chart(fig_cost, use_container_width=True)

    # Actual cost changes detail
    st.subheader("Actual Cost Changes")
    st.caption(
        "Updates where the cost value actually changed (compares to previous version)"
    )

    df_cost_details = get_cost_change_details(engine, start_date)

    if df_cost_details.empty:
        st.info("No actual cost value changes detected in the selected time range.")
    else:
        st.dataframe(
            df_cost_details,
            use_container_width=True,
            hide_index=True,
            column_config={
                "history_date": st.column_config.DatetimeColumn(
                    "Date", format="YYYY-MM-DD HH:mm"
                ),
                "model": "Model",
                "name": "Item",
                "old_cost": "Old Cost",
                "new_cost": "New Cost",
                "history_change_reason": "Reason",
            },
        )

st.divider()

# Recent changes
st.header("Recent Content Changes")

limit = st.slider("Number of recent changes to show", 20, 200, 50)
df_recent = get_recent_changes(engine, limit)

if df_recent.empty:
    st.info("No recent changes found.")
else:
    df_recent["history_type_label"] = df_recent["history_type"].map(HISTORY_TYPE_LABELS)

    st.dataframe(
        df_recent[
            [
                "history_date",
                "model",
                "history_type_label",
                "name",
                "history_change_reason",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "history_date": st.column_config.DatetimeColumn(
                "Date", format="YYYY-MM-DD HH:mm"
            ),
            "model": "Model",
            "history_type_label": "Action",
            "name": "Name",
            "history_change_reason": "Reason",
        },
    )
