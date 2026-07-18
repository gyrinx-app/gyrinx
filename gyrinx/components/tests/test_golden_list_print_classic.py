"""Golden-equivalence test: classic-mode list print sheet.

``core/list_print_classic.html`` extends ``base_print.html`` — a chrome-less
``foundation.html`` with no ``#content`` wrapper. The two built-in scopes of
``assert_equivalent`` don't fit this page:

* ``scope="content"`` looks for an ``id="content"`` element, which the print
  layout doesn't have.
* ``scope="page"`` compares the whole document, but the shared Foundation shell
  serialises the inline GTM ``<script>`` and the GTM ``<noscript>`` iframe with
  slightly different insignificant whitespace than the legacy template. That
  pre-existing shell artifact (unrelated to this conversion) is exactly why the
  golden framework normally compares only ``#content``.

So we assert byte-equivalence on the part this page actually owns — the
``.print-sheet`` subtree emitted by the ``classic_sheet.html`` include — using
the same normalisation the framework applies elsewhere.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup
from django.test import RequestFactory

from gyrinx.components.testing import (
    normalise_fragment,
    render_component,
    render_legacy,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _print_sheet(html: str) -> str:
    """Return the normalised ``.print-sheet`` subtree (the page's own content)."""
    sheet = BeautifulSoup(html, "html.parser").find(class_="print-sheet")
    assert sheet is not None, "No .print-sheet element in rendered page"
    return normalise_fragment(str(sheet))


@pytest.mark.django_db
def test_list_print_classic_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.print_cards import blank_classic_card, card_from_fighter

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    # Rebuild the classic cards exactly as ListPrintView's GET branch does:
    # a card per (non-stash) fighter, then the configured blank cards.
    cards = []
    for f in [fighter]:
        card = card_from_fighter(f, lst)
        if card.kind == "stash":
            continue
        cards.append(card)
    cards += [blank_classic_card("fighter")]
    cards += [blank_classic_card("vehicle")]

    request = _request(user)
    context = {"list": lst, "classic_cards": cards}

    legacy = _print_sheet(
        render_legacy("core/list_print_classic.html", dict(context), request)
    )
    component = _print_sheet(
        render_component("core/list_print_classic.html", dict(context), request)
    )
    assert legacy == component
