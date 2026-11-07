"""Adapters for choice-only detail-list consumers."""

from django import template

from n26.core.printing import detail_columns
from n26.core.rows import choice_rows, part_text, row_text

register = template.Library()


@register.simple_tag
def composed_choices(choices):
    return choice_rows(choices or (), owner="detail-list")


@register.filter
def read_row(row):
    return row_text(row)


@register.simple_tag
def campaign_columns(campaign):
    return detail_columns(campaign)


@register.filter
def read_part(part):
    return part_text(part)
