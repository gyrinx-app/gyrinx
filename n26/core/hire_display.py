"""Catalogue reads and explicit display facts for the Hire workflow."""

from functools import cached_property
from urllib.parse import urlencode

from django.urls import reverse

from n26.core import hire_workflow
from n26.core.access import gang_collections
from n26.core.hire import (
    build_entries,
    build_hire_entry,
    collection_offers,
    gang_scope_sections,
    hireable_profiles,
    section_by_gang_type,
    section_hire_list,
    supplementary_profiles,
)
from n26.core.render import roster, summarise_roster
from n26.library.staged import sees_staged

HIRE_SCOPES = {
    "gang": "Gang list",
    "supplementary": "Supplementary",
    "all": "All profiles",
}


class HireCatalogue:
    """Share each request's collection reads between confirmation and catalogue."""

    def __init__(self, gang, user, scope):
        self.gang = gang
        self.user = user
        self.scope = scope if scope in HIRE_SCOPES else "gang"
        self.shown = sees_staged(user)

    @cached_property
    def carried(self):
        return [access.collection for access in gang_collections(self.gang)]

    @cached_property
    def offers(self):
        return collection_offers(self.carried, include_staged=self.shown)

    @cached_property
    def sections(self):
        if self.scope == "supplementary":
            return section_hire_list(
                build_entries(
                    list(supplementary_profiles(include_staged=self.shown)),
                    with_cards=False,
                )
            )
        if self.scope == "all":
            return section_by_gang_type(
                build_entries(
                    list(hireable_profiles(include_staged=self.shown)),
                    with_cards=False,
                )
            )
        return gang_scope_sections(
            self.offers,
            self.gang.gang_type,
            self.carried,
            with_cards=False,
            include_staged=self.shown,
        )

    @cached_property
    def summary(self):
        return summarise_roster(roster(self.gang))


def listing_url(gang, scope="gang", section=""):
    path = reverse("n26-hire-fighter", args=[gang.pk])
    params = [
        *([("list", scope)] if scope != "gang" else []),
        *([("section", section)] if section else []),
    ]
    return f"{path}?{urlencode(params)}" if params else path


def entry_data(gang, entry, scope, section):
    preview = reverse("n26-hire-preview", args=[gang.pk, entry.profile.pk])
    if entry.entry is not None:
        preview += "?" + urlencode({"entry": str(entry.entry.pk)})
    confirm = listing_url(gang, scope, section)
    confirm += ("&" if "?" in confirm else "?") + urlencode({"hire": entry.key})
    return {
        "key": entry.key,
        "name": entry.name,
        "profileType": entry.profile_type,
        "basePrice": entry.base_price,
        "previewHref": preview,
        "confirmationHref": confirm,
        "groups": [
            {
                "choose": group.choose,
                "offersChoice": group.offers_a_choice,
                "options": [
                    {
                        "key": option.option_key,
                        "name": option.name,
                        "price": option.price,
                        "totalPrice": option.total_price,
                        "default": option.is_default,
                    }
                    for option in group.options
                ],
            }
            for group in entry.groups
        ],
    }


def catalogue_data(catalogue, section=""):
    sections = catalogue.sections
    names = [each.name for each in sections]
    current = section if section in names else next(iter(names), "")
    prices = [entry.base_price for each in sections for entry in each.all_entries()]
    return {
        "scope": catalogue.scope,
        "scopeLabel": HIRE_SCOPES[catalogue.scope],
        "scopeTabs": [
            {"key": key, "label": label, "href": listing_url(catalogue.gang, key)}
            for key, label in HIRE_SCOPES.items()
        ],
        "section": current,
        "listingHref": listing_url(catalogue.gang, catalogue.scope, current),
        "priceFloor": min(prices, default=0),
        "priceCeiling": max(prices, default=0),
        "categories": list(
            dict.fromkeys(
                category.name or each.name
                for each in sections
                for category in each.categories
            )
        ),
        "categoryOptions": list(
            dict.fromkeys(
                category.name
                for each in sections
                for category in each.categories
                if category.name
            )
        ),
        "sections": [
            {
                "name": each.name,
                "categories": [
                    {
                        "name": category.name,
                        "entries": [
                            entry_data(
                                catalogue.gang, entry, catalogue.scope, each.name
                            )
                            for entry in category.entries
                        ],
                    }
                    for category in each.categories
                ],
            }
            for each in sections
        ],
    }


def confirmation_data(profile, offered, key, data):
    """Prepare the quote and stable selection for a confirmation URL."""
    entry = build_hire_entry(profile, with_cards=False)
    if "selection" in data:
        keys = (
            hire_workflow.SelectionField(required=False).clean(data.get("selection"))
            or []
        )
    else:
        keys = [
            pick.option.option_key
            for pick in hire_workflow.resolve_picks(data, profile, entry, key=key)
            if pick.option.option_key
        ]
    known = {
        option.option_key
        for group in entry.groups
        for option in group.options
        if option.option_key
    }
    if set(keys) - known:
        raise hire_workflow.UnavailableHire("No such option")
    selected = set(keys)
    choices = []
    for group in entry.groups:
        picked = [option for option in group.options if option.option_key in selected]
        if not picked and group.choose == "one":
            picked = [option for option in group.options if option.is_default]
            keys.extend(option.option_key for option in picked if option.option_key)
        if group.offers_a_choice:
            choices.extend(option.name for option in picked if option.default_set)
    return {
        "key": key,
        "profileName": profile.name,
        "quote": hire_workflow.quote_sets(
            profile, hire_workflow.resolve_sets(profile, keys), offered
        ),
        "choices": choices,
        "selection": keys,
    }


def figures_data(gang, summary, *, trade_points_href="", credits_href=""):
    def figure(short, label, value, *, unit="¢", absent="", href=""):
        return {
            "short": short,
            "label": label,
            "value": "—" if absent else f"{value}{unit}",
            "absent": absent,
            "href": href,
        }

    return {
        "items": [
            figure(
                "TP",
                "Trade points",
                gang.trade_points_left,
                unit="",
                absent=""
                if gang.visiting_trading_post
                else "No Visit Trading Post action open",
                href=trade_points_href,
            ),
            figure("R", "Rating", gang.rating),
            figure(
                "Cr",
                "Credits",
                gang.credits,
                absent="Unlimited credits" if gang.credits_unlimited else "",
                href=credits_href,
            ),
            figure("St", "Stash", gang.stash_rating),
            figure("W", "Wealth", gang.wealth),
        ],
        "roster": {
            "count": summary.count,
            "rating": summary.rating,
            "groups": [
                {
                    "profile": group.profile,
                    "category": group.category,
                    "count": group.count,
                }
                for group in summary.groups
            ],
            "models": [
                {"name": model.name, "rating": model.rating} for model in summary.models
            ],
        },
    }
