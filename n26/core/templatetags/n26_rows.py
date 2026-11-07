"""Adapters for choice-only detail-list consumers."""

from django import template

from n26.core.rows import choice_rows, row_text

register = template.Library()


@register.simple_tag
def composed_choices(choices):
    return choice_rows(choices or (), owner="detail-list")


@register.filter
def read_row(row):
    return row_text(row)
