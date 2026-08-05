"""Shared helpers for building and formatting fighter statlines.

Both the pack editor (a player-facing view in the core app) and the fighter
admin need to resolve which statline a fighter should have, format the values
typed into it, and describe them to the user. They live here so the content
admin does not have to import from ``core.views``.
"""

from django import forms

from n23.content.models.equipment import AUTO_EQUIPMENT_CATEGORY_BY_FIGHTER_CATEGORY
from n23.content.models.statline import ContentStatlineType
from gyrinx.models import SMART_QUOTES


def statline_type_for_category(category):
    """Look up the ContentStatlineType for a fighter category.

    Falls back to the "Fighter" type if no specific mapping exists, EXCEPT
    for auto-equipment categories (VEHICLE, EXOTIC_BEAST) where a wrong-fit
    fallback would silently produce nonsense statlines on the auto-created
    companion equipment. For those, raise ContentStatlineType.DoesNotExist
    so the create flow surfaces a loud failure instead.

    Raises ValueError if multiple types are configured for the same category.
    """
    qs = ContentStatlineType.objects.filter(default_for_categories__contains=category)
    count = qs.count()
    if count == 0:
        if category in AUTO_EQUIPMENT_CATEGORY_BY_FIGHTER_CATEGORY:
            raise ContentStatlineType.DoesNotExist(
                f"No ContentStatlineType configured for {category!r}. "
                f"Auto-equipment fighter categories require an explicit "
                f"matching ContentStatlineType — silently falling back to "
                f"the Fighter statline would produce wrong stats."
            )
        return ContentStatlineType.objects.get(name="Fighter")
    if count == 1:
        return qs.first()
    raise ValueError(
        f"Multiple ContentStatlineType objects configured for category "
        f"{category!r} in default_for_categories"
    )


def stat_definitions_for(category=None, statline_type_override=None):
    """Load the stat definitions for a fighter category's statline type."""
    if statline_type_override:
        statline_type = statline_type_override
    elif category:
        statline_type = statline_type_for_category(category)
    else:
        statline_type = ContentStatlineType.objects.get(name="Fighter")
    return statline_type.stats.select_related("stat").order_by("position")


def normalize_stat_value(raw_value, content_stat):
    """Normalize a stat value based on ContentStat formatting config.

    Auto-adds the correct suffix/prefix:
    - is_inches: ``4`` → ``4"``
    - is_target: ``3`` → ``3+``
    - is_modifier: ``2`` → ``+2``
    """
    value = raw_value.strip() if raw_value else ""
    # Replace smart quotes with straight quotes.
    value = value.replace("“", '"').replace("”", '"')
    value = value.replace("‘", "'").replace("’", "'")

    if value in ("", "-"):
        return "-"

    if content_stat.is_inches:
        # Strip trailing " to get the number, then re-add.
        number_str = value.rstrip('"').strip()
        try:
            n = int(number_str)
            return f'{n}"'
        except ValueError:
            return value

    if content_stat.is_target:
        # Strip trailing + to get the number, then re-add.
        number_str = value.rstrip("+").strip()
        try:
            n = int(number_str)
            return f"{n}+"
        except ValueError:
            return value

    if content_stat.is_modifier:
        # Strip leading +/- to get the number, then re-add sign.
        number_str = value.lstrip("+-").strip()
        try:
            n = int(number_str)
            # Preserve sign from original input; default positive.
            if value.startswith("-"):
                n = -abs(n)
            else:
                n = abs(n)
            return f"+{n}" if n >= 0 else str(n)
        except ValueError:
            return value

    # Plain number stat — store as-is.
    return value


def set_fighter_statline(fighter, statline_type, values_by_type_stat=None):
    """Give ``fighter`` a statline of ``statline_type`` holding these values.

    The single write path for a fighter's stats, used by the admin, the pack
    editor and the post_save that guarantees every fighter has one. It
    reconciles rather than creates, because a fighter has at most one statline
    (OneToOne) and more than one of those callers can run for the same
    fighter: creating blindly raced into a unique-constraint error.

    ``values_by_type_stat`` maps ContentStatlineTypeStat id to a raw value;
    anything missing is left as it was, or written as "-" if new. Values for
    stats outside the type are dropped, so switching type does not leave
    orphans behind — ContentStatline.clean() requires exactly the type's set.
    """
    from n23.content.models.statline import ContentStatline, ContentStatlineStat

    values_by_type_stat = values_by_type_stat or {}

    statline, created = ContentStatline.objects.get_or_create(
        content_fighter=fighter, defaults={"statline_type": statline_type}
    )
    if not created and statline.statline_type_id != statline_type.id:
        statline.statline_type = statline_type
        statline.save(update_fields=["statline_type"])

    type_stats = list(statline_type.stats.select_related("stat"))
    statline.stats.exclude(
        statline_type_stat__in=[type_stat.id for type_stat in type_stats]
    ).delete()

    existing = {stat.statline_type_stat_id: stat for stat in statline.stats.all()}
    for type_stat in type_stats:
        if type_stat.id in values_by_type_stat:
            value = normalize_stat_value(
                values_by_type_stat[type_stat.id], type_stat.stat
            )
        elif type_stat.id in existing:
            continue
        else:
            value = "-"
        ContentStatlineStat.objects.update_or_create(
            statline=statline,
            statline_type_stat=type_stat,
            defaults={"value": value},
        )

    # Point the fighter we were handed at what we just wrote. Django caches the
    # reverse one-to-one, so a caller reading fighter.custom_statline after
    # this — the admin does, and so does anything rendering a card — would
    # otherwise get the statline as it was before, including its old type.
    statline.statline_type = statline_type
    fighter._state.fields_cache["custom_statline"] = statline
    return statline


def stat_placeholder(content_stat):
    """Return a placeholder example for a stat input field."""
    if content_stat.is_inches:
        return '4"'
    if content_stat.is_target:
        return "3+"
    if content_stat.is_modifier:
        return "+1"
    return "3"


def validate_no_smart_quotes(value):
    """Reject curly quotes in a stat value.

    They look almost identical to straight quotes and break comparisons
    against values typed elsewhere, so the admin refuses them rather than
    silently rewriting what was entered.
    """
    if (
        value
        and isinstance(value, str)
        and any(quote in value for quote in SMART_QUOTES.values())
    ):
        raise forms.ValidationError(
            'Smart quotes are not allowed. Please use simple quotes (") instead.'
        )
    return value
