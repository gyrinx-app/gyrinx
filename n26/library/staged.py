"""Content that is staged — written, but not yet put live — and who sees it.

Not the uploaded sheets waiting to be imported (``models/staging.py``):
those are files, and this is content that already exists as rows.

An author writes a new gang over days — its type, its fighters, the lists
they buy from — and players must not meet it half-built. The author,
though, must meet it exactly as players will: on the create-gang cards, the
hire screen, the equipment lists. That is the only test of content that
counts, and it is why a staged row is not simply hidden. It is held back
from every surface where a player adds to a gang, and shown on those same
surfaces to whoever may see it.

Two rules keep this small (design/collections.md, "Hiding content from
some viewers"):

* **The gate is where things are chosen, never where they are drawn.** A
  card, a sheet, a ledger line renders whatever it holds. Once a staged
  thing is on a gang — an author's test gang, or a live profile whose
  built-ins bring it — it draws for everyone, because a roster is a thing
  players send each other and what it shows cannot depend on who is
  looking.
* **Staging holds back new things; it does not hold back changes.** A
  change to a row that is already live is live at once. What staging adds
  is a place to leave the new until it is ready, and one act — putting
  everything live — that releases it all together.

Who sees staged content: staff, because the authoring pages are theirs;
and whoever the ``staged-content`` flag is open to, so a release can be
rehearsed with a group of players before it is made. Opening that flag to
everyone is a rehearsal with a way back; putting the rows live is the
release.
"""

from n26 import flags

#: Where the flag's reading is kept on the user for the rest of the request.
_KEPT_ON_USER = "_sees_staged"


def sees_staged(user) -> bool:
    """Whether this reader is shown staged content where players add to a gang.

    Anonymous readers never are: every such surface wants a signed-in
    owner anyway, and a roster — the one page a stranger reads — draws
    what it holds regardless.

    One screen asks this several times — for the listing, for each dialog
    on it, for the click it checks — and the flag cannot change between
    them, so it is read once and kept on the user for the request,
    the way Django keeps the permissions it has looked up.
    """
    if user is None or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    kept = getattr(user, _KEPT_ON_USER, None)
    if kept is None:
        kept = flags.enabled(flags.STAGED_CONTENT, user)
        setattr(user, _KEPT_ON_USER, kept)
    return kept


def content_kinds():
    """Every concrete kind built on ``Content``, in the order an author reads
    them — the tables that carry a ``staged`` column."""
    from django.apps import apps

    from n26.library.models import Content

    found = [
        model
        for model in apps.get_app_config("library").get_models()
        if issubclass(model, Content)
    ]
    return sorted(found, key=lambda model: str(model._meta.verbose_name_plural))


def stageable_kinds():
    """The kinds a player is offered somewhere, so staging one means something.

    Read off the places that offer them rather than listed again here: the
    types a gang or a campaign is founded on, what a collection may list,
    what a choice may offer, what a picklist holds, and the assets a
    campaign hands out. A kind that becomes offerable becomes stageable
    with nothing to remember. Everything else — a category, a modifier, a
    statline — is reached through one of these and needs no gate of its
    own.
    """
    from django.apps import apps

    from n26.library.models import Asset, CampaignType, GangType, PicklistMember
    from n26.library.models.collection import entryable_kinds
    from n26.library.models.modifier import OFFERABLE_KINDS

    kinds = {
        GangType,
        CampaignType,
        Asset,
        PicklistMember._meta.get_field("pickable").related_model,
        *entryable_kinds().values(),
        *(apps.get_model("library", name) for name in OFFERABLE_KINDS),
    }
    return frozenset(kinds)


def stageable(model) -> bool:
    """Whether rows of this kind can be staged from the authoring pages."""
    return model in stageable_kinds()


def staged_count():
    """How many rows are staged across the library — the figure the index
    shows beside its link. One count per kind."""
    return sum(model.objects.filter(staged=True).count() for model in content_kinds())


def staged_rows():
    """Every staged row, kind by kind — what the Staged content page lists.

    Every kind is asked, not only the stageable ones, so a row staged some
    other way is never invisible to the people who can put it live. A kind
    with nothing staged is left out. One query per kind, however many rows.
    """
    found = []
    for model in content_kinds():
        rows = list(model.objects.filter(staged=True))
        if rows:
            found.append((model, rows))
    return found
