"""URL-based ordering and grouping for campaign gangs and inventory."""

from urllib.parse import parse_qs, urlencode, urlsplit

CAMPAIGN_VIEW_KEYS = ("sort", "group", "asset_sort", "asset_group")


def table_query(request, *, current_url=""):
    """Read table preferences from a known return URL or the visible HTMX page."""
    source = current_url or (
        request.headers.get("HX-Current-URL", "")
        if request.headers.get("HX-Request")
        else ""
    )
    if source:
        return {
            key: values[-1]
            for key, values in parse_qs(
                urlsplit(source).query, keep_blank_values=True
            ).items()
        }
    return request.GET


def table_view_href(request, here):
    """Keep only table preferences when returning to the campaign page."""
    query = table_query(request)
    preferences = {key: query.get(key) for key in CAMPAIGN_VIEW_KEYS if key in query}
    return here + ("?" + urlencode(preferences) if preferences else "")


def gang_sort_values(sheet, line):
    counter_keys = getattr(sheet, "counter_keys", []) or sheet.counter_columns
    label_ids = getattr(sheet, "label_ids", []) or sheet.label_columns
    return {
        "name": line.name.casefold(),
        "type": line.gang_type.casefold(),
        "owner": line.owner.username.casefold() if line.owner else None,
        "rating": line.rating,
        "credits": None if line.credits_unlimited else line.credits,
        "wealth": line.wealth,
        **{
            f"counter:{key}": counter.value if counter else None
            for key, counter in zip(counter_keys, line.counters, strict=True)
        },
        **{
            f"label:{key}": value.casefold() or None
            for key, value in zip(label_ids, line.labels, strict=True)
        },
    }


def prepare_gang_table(sheet, request, here, *, current_url=""):
    query = table_query(request, current_url=current_url)
    prepare_inventory(sheet, query, here)
    columns = [
        ("name", "Gang"),
        ("rating", "Rating"),
        ("credits", "Credits"),
        ("wealth", "Wealth"),
    ]
    counter_keys = getattr(sheet, "counter_keys", []) or sheet.counter_columns
    label_ids = getattr(sheet, "label_ids", []) or sheet.label_columns
    counters = [
        (f"counter:{key}", name)
        for key, name in zip(counter_keys, sheet.counter_columns, strict=True)
    ]
    groups = [
        (f"label:{key}", name)
        for key, name in zip(label_ids, sheet.label_columns, strict=True)
    ]
    columns += counters
    choices = [*columns, ("type", "Gang type"), ("owner", "Player")]
    choices += groups
    aliases = {f"counter-{i}": token for i, (token, _) in enumerate(counters)}
    aliases.update({f"label-{i}": token for i, (token, _) in enumerate(groups)})
    sort = query.get("sort", "name")
    descending = sort.startswith("-")
    key = sort.removeprefix("-")
    key = aliases.get(key, key)
    sort = ("-" if descending else "") + key
    if key not in dict(choices):
        key, sort, descending = "name", "name", False
    default = getattr(sheet, "default_group", "")
    default_group = f"label:{default}" if default in label_ids else ""
    group = query.get("group", default_group)
    group = aliases.get(group, group)
    if group not in dict(groups):
        group = ""

    def value(line):
        return gang_sort_values(sheet, line)[key]

    # Missing values stay last in either direction. Names break numeric ties.
    named = sorted(sheet.gangs, key=lambda line: (line.name.casefold(), line.gang_id))
    present = [line for line in named if value(line) is not None]
    absent = [line for line in named if value(line) is None]
    sheet.gangs = sorted(present, key=value, reverse=descending) + absent
    for line in sheet.gangs:
        line.grouped_label_index = (
            [token for token, _ in groups].index(group) if group else None
        )
    sheet.table_sort = sort
    sheet.table_group = group
    sheet.table_href = here
    if any(key in query for key in CAMPAIGN_VIEW_KEYS):
        preferences = {"sort": sort, "group": group}
        if "asset_sort" in query or "asset_group" in query:
            preferences.update(
                asset_sort=sheet.inventory_view["sort"],
                asset_group=sheet.inventory_view["group"],
            )
        sheet.table_href += "?" + urlencode(preferences)
    sheet.table_sort_options = [
        {
            "value": prefix + token,
            "label": label + suffix,
            "selected": sort == prefix + token,
        }
        for token, label in choices
        for prefix, suffix in [("", " (ascending)"), ("-", " (descending)")]
    ]
    sheet.table_group_options = [
        {"value": "", "label": "No grouping", "selected": not group},
        *(
            {"value": token, "label": name, "selected": group == token}
            for token, name in groups
        ),
    ]
    sheet.table_headers = [
        {
            "label": label,
            "href": here
            + "?"
            + urlencode(
                {
                    "sort": ("-" + token) if sort == token else token,
                    "group": group,
                    **{
                        field: sheet.inventory_view[value]
                        for field, value in (
                            ("asset_sort", "sort"),
                            ("asset_group", "group"),
                        )
                        if "asset_sort" in query or "asset_group" in query
                    },
                }
            )
            + "#gangs",
            "direction": ("descending" if descending else "ascending")
            if key == token
            else "none",
        }
        for token, label in columns
    ]
    if group:
        index = [token for token, _ in groups].index(group)
        buckets = {}
        for line in sheet.gangs:
            buckets.setdefault(line.labels[index], []).append(line)
        sheet.table_groups = [
            {
                "label": label or "Not set",
                "gangs": buckets[label],
                "colour": next(
                    (
                        option["colour"]
                        for option in getattr(sheet, "label_options", {}).get(
                            label_ids[index], []
                        )
                        if option["name"] == label
                    ),
                    "",
                )
                if label_ids
                else "",
            }
            for label in sorted(
                buckets, key=lambda label: (not bool(label), label.casefold())
            )
        ]
    else:
        sheet.table_groups = [{"label": "", "gangs": sheet.gangs}]


def label_options(campaign, slots):
    """Read every offered group and its campaign colour in one query."""
    from n26.library.models import PicklistMember

    members = list(
        PicklistMember.objects.filter(
            picklist_id__in=[slot.picklist_id for slot in slots],
            archived=False,
        )
        .select_related("pickable")
        .order_by("position", "pk")
    )
    return {
        str(slot.pk): [
            {
                "id": str(member.pickable_id),
                "name": member.pickable.name,
                "colour": campaign.group_colours.get(str(slot.pk), {}).get(
                    str(member.pickable_id), ""
                ),
            }
            for member in members
            if member.picklist_id == slot.picklist_id
        ]
        for slot in slots
    }


def gang_table_props(sheet):
    """JSON-safe table facts and permitted links from the prepared campaign sheet."""
    from hashlib import sha256

    from n26.badges import svg_tree
    from n26.core.people import person_link
    from n26.core.templatetags.artwork import safe_artwork
    from n26.core.templatetags.theme import css_color

    counter_keys = sheet.counter_keys or sheet.counter_columns
    label_ids = sheet.label_ids or sheet.label_columns
    badges = {}
    artwork = {}
    gangs = []
    for line in sheet.gangs:
        artwork_key = (
            sha256(line.type_icon.encode()).hexdigest() if line.type_icon else ""
        )
        if artwork_key and artwork_key not in artwork:
            artwork[artwork_key] = svg_tree(safe_artwork(line.type_icon))
        gangs.append(
            {
                "id": line.gang_id,
                "name": line.name,
                "type": line.gang_type,
                "artwork": artwork_key,
                "owner": person_link(line.owner, badges) if line.owner else None,
                "colour": css_color(line.colour) if line.colour else "",
                "href": line.href,
                "rating": line.rating,
                "credits": None if line.credits_unlimited else line.credits,
                "wealth": line.wealth,
                "creditsHref": line.credits_href,
                "removeHref": line.remove_href,
                "overBudget": line.over_budget,
                "sortValues": gang_sort_values(sheet, line),
                "labels": line.labels,
                "assets": [
                    {
                        "label": detail.label,
                        "names": [
                            {"name": item.name, "count": item.count, "text": item.text}
                            for item in detail.names
                        ],
                    }
                    for detail in line.grouped_assets or []
                ],
                "rolls": [
                    {"label": roll.label, "href": roll.href}
                    for roll in line.starting_rolls
                    if roll.href
                ],
                "counters": [
                    None
                    if counter is None
                    else {
                        "id": counter.assignment_id,
                        "name": counter.name,
                        "value": counter.value,
                        "adjustHref": counter.adjust_href,
                        "income": counter.income_explanation
                        if counter.is_income
                        else None,
                    }
                    for counter in line.counters
                ],
            }
        )
    return {
        "href": sheet.table_href or "#",
        "sort": sheet.table_sort,
        "group": sheet.table_group,
        "defaultGroup": f"label:{sheet.default_group}"
        if sheet.default_group in label_ids
        else "",
        "counters": [
            {"token": f"counter:{key}", "label": name}
            for key, name in zip(counter_keys, sheet.counter_columns, strict=True)
        ],
        "labels": [
            {
                "token": f"label:{key}",
                "label": name,
                "colours": {
                    option["name"]: css_color(option["colour"])
                    for option in sheet.label_options.get(key, [])
                    if option["colour"]
                },
            }
            for key, name in zip(label_ids, sheet.label_columns, strict=True)
        ],
        "gangs": gangs,
        "badges": badges,
        "artwork": artwork,
        "focusCounter": getattr(sheet, "table_focus_counter", ""),
    }


def prepare_inventory(sheet, query, here):
    """Validate the independent inventory view without loading more data."""
    sort = query.get("asset_sort", "name")
    if sort.removeprefix("-") not in {"name", "holder", "income"}:
        sort = "name"
    group = query.get("asset_group", "status")
    if group not in {"", "status", "holder"}:
        group = "status"
    sheet.inventory_view = {"href": here, "sort": sort, "group": group}
    for table in sheet.assets:
        table.inventory_view = sheet.inventory_view


def asset_table_props(table):
    """The inventory's prepared holdings and permitted actions, as display data."""
    return {
        "label": table.label,
        "plural": table.plural,
        "typeId": table.asset_type_id,
        "href": table.inventory_view.get("href", ""),
        "sort": table.inventory_view.get("sort", "name"),
        "group": table.inventory_view.get("group", "status"),
        "entries": [
            {
                "id": entry.campaign_asset_id,
                "name": entry.name,
                "assetName": entry.asset_name,
                "boon": entry.boon,
                "income": entry.income_explanation,
                "held": entry.held,
                "holder": entry.holder,
                "holderId": entry.holder_gang_id,
                "holderHref": entry.holder_href,
                "href": entry.href,
                "sortValues": {
                    "name": entry.name.casefold(),
                    "holder": entry.holder.casefold(),
                    "income": entry.income,
                },
                "actions": [
                    {
                        "label": label,
                        "href": href,
                        "dialog": dialog,
                        "tone": tone,
                        "separatorBefore": False,
                    }
                    for label, href, dialog, tone in (
                        (entry.transfer_label, entry.transfer_href, True, "default"),
                        ("Unassign", entry.unassign_href, True, "default"),
                        ("Assign", entry.assign_href, True, "default"),
                        ("Remove", entry.remove_href, False, "danger"),
                    )
                    if href
                ],
            }
            for entry in table.entries
        ],
    }
