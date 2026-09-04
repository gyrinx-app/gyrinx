"""Reach — a piece of content explained in sentences.

Two questions an author has about anything in the library, and neither is
answerable from the row's own page as it stands: **what does this do** to
whoever ends up with it, and **how does anyone come to have it** at all.
The first is downstream, the modifiers; the second is upstream, every
edge that puts the thing in somebody's hands.

Both are compiled here into plain sentences a player could read, each
carrying the mechanics as a hint for whoever wants them and an identity
for whoever wants to link it. Structures before renderers: this module
knows no HTML and no URLs — a ``Sentence``'s ``href`` is left empty for
the view to fill, the way the hire list's cards are pointed at their
addresses after they are built.

The register is the option cards' (``specs.py``): short, concrete,
player-plain, the game's own words. Four rules hold the voice together:

* **Who a modifier speaks of follows from who carries it.** The same
  "the bearer's weapons gain Backstab" reads three ways — carried by a
  subtype it is about anyone with that subtype, carried by a piece of
  gear it is about whoever holds the gear, held by the gang it is about
  every fighter in it. So the subject is computed from the carriage, not
  written into the modifier.
* **A sentence about a person's own sheet says "they"; one about their
  kit names the bearer.** "Their Psychoteric Whispers set appears as
  Primary" and "its bearer's weapons gain Backstab" are the two
  registers, and the second exists because a bare "their weapons" would
  be taken for the gang's.
* **Structural facts say "is"; potential routes say "may".** Being built
  into a gang type is a fact about the world; being chosen for an
  offered choice is something that might happen.
* **A content name is said exactly as it was authored.** "3 Hive Scum",
  never "3 Hive Scums": the name is the book's, and inflecting it
  invents a word no author wrote. Ordinary words around it still count
  properly — two gangs, three times.

A hint says what happens for the row in front of the reader, in their
own timeline — when it arrives, what takes it away, what a page will
warn about. It never explains how the app is built and never argues the
design.
"""

from dataclasses import dataclass, field, replace

from django.utils.text import capfirst

from n26.library.references import (
    carrying_models,
    of_kind,
    reading_sentences,
    references_to,
)

#: How a thing comes to be held, which is what decides who its modifiers
#: speak of. Not a property of the thing: a rule reaches every fighter
#: when the gang holds it and one fighter when they do, and the same row
#: is read both ways.
GANG = "gang"
SUBTYPE = "subtype"
KIT = "kit"
CARD = "card"
#: Nothing carries it yet — the composer's case, where a modifier is
#: being written before there is anything to hang it on.
UNATTACHED = "unattached"


@dataclass(frozen=True)
class Sentence:
    """One statement about a piece of content.

    ``text`` is what a player could read. ``hint`` is the mechanics
    behind it, for a reader who hovers. ``href`` is the address of the
    row the sentence is about, filled in by the view — the compiler
    knows no URLs. ``key`` is that row's identity, ``(model label, pk)``,
    so a view can point each sentence at its subject without reading the
    words.
    """

    text: str
    hint: str = ""
    href: str = ""
    key: tuple = ()

    def at(self, href):
        """This sentence, pointed at an address.

        The rows are frozen, so a view decorates by replacing rather than
        by writing into them: it walks the prose, turns each ``key`` into
        a URL of its own, and keeps what comes back.
        """
        return replace(self, href=href)


@dataclass(frozen=True)
class AssignedTo:
    """How much of the player side is standing on this thing."""

    gangs: int
    rows: int


@dataclass(frozen=True)
class Prose:
    """Everything the reach column says about one thing.

    ``referenced_by`` is how anyone comes to have it, ``does`` is what it
    does once they have it, in the order the rules apply it.
    ``assigned_to`` is the player-side tally, and ``None`` for a kind
    nobody can be assigned.
    """

    referenced_by: tuple = ()
    does: tuple = ()
    assigned_to: AssignedTo | None = None


# --- Who a modifier speaks of ---------------------------------------------


@dataclass(frozen=True)
class _Who:
    """The words a sentence needs for whoever a modifier reaches.

    Every phrase is stored with a small first letter; the finished
    sentence is capitalised once, at the end. That way a leading clause
    ("While their XP is 75 or more, …") can be put in front of any of
    them without each renderer having to know it might not be first.
    """

    subject: str
    possessive: str
    #: The bearer's weapons, said as a noun phrase. Always plural.
    weapons: str
    #: Whether ``subject`` takes a plural verb.
    plural: bool
    #: When what is given holds good — the tail of a giving sentence.
    persistence: str
    #: Who an offer is put to.
    asked: str = "them"
    #: Whether a narrowing may follow the subject as a phrase — "every
    #: fighter with Cawdor". A pronoun or a clause cannot take one, and
    #: its narrowings lead the sentence instead: "While holding Cawdor,
    #: they gain …".
    qualifiable: bool = True
    #: Whether a narrowing has been appended to ``subject``, so that a
    #: possessive can no longer be made by adding 's — "every fighter
    #: with Cawdor's weapons" hands the weapons to Cawdor — and what is
    #: owned is said the long way round instead (``_owned``).
    qualified: bool = False


def _owned(who, thing):
    """What the subject has, as a noun phrase: "their Ballistic Skill",
    or "the Ballistic Skill of every fighter with Cawdor" once the
    subject carries a narrowing of its own."""
    if who.qualified:
        return f"the {thing} of {who.subject}"
    return f"{who.possessive} {thing}"


def _a(name):
    """A name with its article. Naive on purpose — the leading letter and
    nothing more: the names are the books', and getting "a Unification
    Elder" right needs a pronunciation dictionary nobody maintains."""
    article = "an" if str(name)[:1].lower() in "aeiou" else "a"
    return f"{article} {name}"


def _who(carriage, thing=None):
    if carriage is GANG:
        return _Who(
            subject="every fighter",
            possessive="every fighter's",
            weapons="every fighter's weapons",
            plural=False,
            persistence="while the gang holds this",
        )
    if carriage is SUBTYPE:
        return _Who(
            subject=f"{_a(thing)} fighter",
            possessive=f"{_a(thing)} fighter's",
            weapons=f"{_a(thing)} fighter's weapons",
            plural=False,
            persistence="while the subtype stands",
        )
    if carriage is KIT:
        return _Who(
            subject="its bearer",
            possessive="its bearer's",
            weapons="its bearer's weapons",
            plural=False,
            persistence="while they carry it",
        )
    if carriage is UNATTACHED:
        # Nothing is carrying it, so the sentence names the carrier
        # instead of pointing at one.
        return _Who(
            subject="whoever ends up carrying this",
            possessive="the carrier's",
            weapons="the weapons of whoever ends up carrying this",
            plural=False,
            persistence="while they carry it",
            qualifiable=False,
        )
    return _Who(
        subject="they",
        possessive="their",
        weapons="their weapons",
        plural=True,
        persistence="while they have it",
        qualifiable=False,
    )


#: The kinds a fighter *carries*, where "bearer" is the right word. The
#: rest are had rather than held — a rule prints on a card, it is not
#: picked up — and their sentences say "they".
_CARRIED = ("weapon", "wargear", "weaponaccessory", "weaponprofile")


def carriage_of(thing, edges):
    """How this thing comes to be held, in the sense ``_who`` needs.

    Reaching the gang wins over everything: a rule built into a gang
    type does what it does to every member, whatever kind of row it is.
    Below that the kind decides, because a subtype is a fact about a
    model and a gun is something a model carries.
    """
    from n26.library.models import CampaignType, GangType, Subtype

    # Both types are assigned to the gang itself: a gang is founded on
    # one and joins a campaign on the other.
    if isinstance(thing, (CampaignType, GangType)):
        return GANG
    if _reaches_the_gang(edges):
        return GANG
    if isinstance(thing, Subtype):
        return SUBTYPE
    if type(thing)._meta.model_name in _CARRIED:
        return KIT
    return CARD


# --- Downstream: what it does ---------------------------------------------

#: One renderer per effect kind, keyed by its column on ``Modifier``. A
#: discovering test refuses an effect with no entry here: an effect
#: nothing can say is one the reach column silently drops.
DOWNSTREAM = {}


def _renders(field):
    def register(renderer):
        DOWNSTREAM[field] = renderer
        return renderer

    return register


@dataclass(frozen=True)
class _Parts:
    """What a renderer is handed: the reach, the target, and the chain.

    ``chain`` is what a granted thing gives in its own right, already
    looked up in a batch, because a sentence that asked for it a row at
    a time would cost a query per grant.
    """

    who: _Who
    target: str
    chain: dict


def _agrees(who, singular, plural):
    return plural if who.plural else singular


def _while(who):
    """When what is given holds good, where that still needs saying.

    Empty where the sentence has already said it: a scope conditioned on
    a threshold opens with "While their XP is 75 or more", and a second
    "while" at the end would say the same thing twice.
    """
    return f", {who.persistence}" if who.persistence else ""


def _gained(thing):
    """What arriving with a thing is called, in words that suit its kind.

    A trait on a firing line needs no noun after it; a collection is
    access rather than an object; a granted weapon is free kit and says
    so, because nothing about it is bought.
    """
    kind = type(thing)._meta.model_name
    if kind == "subtype":
        return f"the {thing} subtype"
    if kind == "skill":
        return f"the {thing} skill"
    if kind == "power":
        return f"the {thing} power"
    if kind == "collection":
        return f"access to {thing}"
    if kind == "weapon":
        return f"{thing}, free"
    return str(thing)


#: What the gang's copy of a grant amounts to. Only three kinds can land
#: there — a named rule, a list, and a hidden carrier — and each means
#: something different by arriving.
_ON_THE_GANG = {
    "rule": "printed on the gang page",
    "collection": "and every member may buy from it",
    "hidden": "which draws no line of its own",
}

_GANG_REACH = (
    "Anything assigned to the gang affects every fighter in it. It is not "
    "listed on each fighter's card."
)


@_renders("adds_assignable")
def _says_adds(effect, parts):
    from n26.library.models.modifier import GANG as GANG_TARGET
    from n26.library.models.modifier import WEAPON_PROFILE

    who, thing = parts.who, effect.thing
    chain = parts.chain.get(_identity(thing), ())
    tail = f" — which itself gives {_and_then(chain)}" if chain else ""
    hint = (
        "Applies while the item carrying this modifier is assigned, and "
        "goes with it. Free — adds nothing to any rating."
    )
    if parts.target == WEAPON_PROFILE:
        return f"{who.weapons} gain {thing}{_while(who)}{tail}.", hint
    if parts.target == GANG_TARGET:
        landing = _ON_THE_GANG.get(type(thing)._meta.model_name, "held by the gang")
        return (
            f"the gang gains {_gained(thing)}, {landing}{tail}.",
            f"{hint} {_GANG_REACH}",
        )
    verb = _agrees(who, "gains", "gain")
    return f"{who.subject} {verb} {_gained(thing)}{_while(who)}{tail}.", hint


@_renders("removes_assignable")
def _says_removes(effect, parts):
    from n26.library.models.modifier import GANG as GANG_TARGET
    from n26.library.models.modifier import WEAPON_PROFILE

    who, thing = parts.who, effect.thing
    hint = (
        "Removes things that were granted or built in — never things that "
        "were paid for. Nothing is deleted: remove the item carrying this "
        "modifier and they come back."
    )
    if parts.target == WEAPON_PROFILE:
        return f"{who.weapons} lose {thing}{_while(who)}.", hint
    gone = f"{_gained(thing)}, and everything it gave goes with it"
    if parts.target == GANG_TARGET:
        return f"the gang loses {gone}.", f"{hint} {_GANG_REACH}"
    verb = _agrees(who, "loses", "lose")
    return f"{who.subject} {verb} {gone}.", hint


@_renders("changes_stat")
def _says_changes_stat(effect, parts):
    from n26.library.models.modifier import WEAPON_PROFILE

    who = parts.who
    if effect.mode == effect.Mode.SET:
        change = f"set to {effect.amount}"
    else:
        better = "better" if effect.mode == effect.Mode.IMPROVE else "worse"
        change = f"{effect.amount} {better}"
    hint = (
        "“Better” and “worse” adapt to the characteristic: a 4+ target "
        "worsens to 5+, a plain number worsens downwards. The card shows "
        "what changed each cell."
    )
    if parts.target == WEAPON_PROFILE:
        return (
            f"on {who.weapons}, {effect.stat.full_name} is {change}{_while(who)}.",
            hint,
        )
    return (
        f"{_owned(who, effect.stat.full_name)} is {change}{_while(who)}.",
        hint,
    )


@_renders("contributes_to_counter")
def _says_contributes_to_counter(effect, parts):
    who = parts.who
    return (
        f"{effect.amount} is added to {who.possessive} {effect.counter} "
        f"reading{_while(who)}.",
        (
            "Worked out on every read, so the reading drops back when "
            "the item carrying this modifier goes. Nothing is written "
            "on the ledger."
        ),
    )


@_renders("changes_category")
def _says_changes_category(effect, parts):
    who = parts.who
    verb = _agrees(who, "files", "file")
    return (
        f"{who.subject} {verb} under {effect.category.name} on the gang "
        f"page{_while(who)}.",
        (
            "Where they sort on the gang page, and nothing else: the hire "
            "list and every collection go on filing them where their "
            "entry says."
        ),
    )


@_renders("offers_choice")
def _says_offers_choice(effect, parts):
    who = parts.who
    said = (
        f"it asks {who.asked} to choose one {effect.kind_label} — the "
        "card says Choose until they pick."
    )
    hint = (
        "The offered choice stays on the card until the choice is made. "
        "Making the choice late costs nothing."
    )
    if effect.from_section_id is not None:
        hint += (
            f" Only what appears as {effect.from_section.name} for that "
            "model is listed — a placement is what puts a set there, and "
            "an offered choice with no placement behind it has nothing "
            "on it."
        )
    if effect.will_be_assigned_to == effect.WillBeAssignedTo.GANG:
        said += (
            " What is chosen belongs to the gang and is broadcast, not to "
            "whoever was asked."
        )
    return said, hint


@_renders("places_category")
def _says_places_category(effect, parts):
    who = parts.who
    section = effect.section.name
    hint = (
        "Sets where that category appears, for this model only. If two "
        "items place the same category, the one nearer the top of the "
        "collection wins."
    )
    if effect.the_chosen:
        picks = _agrees(who, "picks", "pick")
        return (
            f"whatever set {who.subject} {picks} appears as {section}.",
            (
                f"{hint} With nothing chosen, the placement simply does "
                "not happen, and the plan says why."
            ),
        )
    return f"{_owned(who, f'{effect.category.name} set')} appears as {section}.", hint


@_renders("requires_companions")
def _says_requires_companions(effect, parts):
    return (
        f"the gang should field at least {effect.at_least} {effect.of} for "
        f"each {effect.for_each} — the gang page warns when it has fewer; "
        "nothing is blocked.",
        (
            "Adds a warning to the gang page when there are too few — "
            f"fewer than {effect.at_least} {effect.of} for each "
            f"{effect.for_each}, counted by the rank printed on each "
            "fighter's card. Nothing is blocked."
        ),
    )


@_renders("allows_at_most")
def _says_allows_at_most(effect, parts):
    from n26.library.models.modifier import GANG as GANG_TARGET

    # The name is the author's, whatever the number in front of it: "2
    # Aberrant" rather than a plural nobody wrote.
    named = str(effect.thing)
    ban = " A limit of 0 is a ban."
    if parts.target == GANG_TARGET:
        if not effect.at_most:
            said = f"the gang should hold no {named} at all"
        else:
            said = f"the gang should hold at most {effect.at_most} {named}"
        return (
            f"{said} — the gang page warns when it holds more; nothing is blocked.",
            (
                "Adds a warning to the gang page when the gang holds more "
                f"than {effect.at_most} {named}. Nothing is blocked.{ban}"
            ),
        )
    if not effect.at_most:
        said = f"no model should hold {named} at all"
    else:
        said = f"no model should hold more than {effect.at_most} {named}"
    return (
        f"{said} — their card warns when one does; nothing is blocked.",
        (
            "Adds a warning to a model's card when it holds more than "
            f"{effect.at_most} {named}. Nothing is blocked.{ban}"
        ),
    )


@_renders("op_adds_miniature")
def _says_op_adds_miniature(effect, parts):
    return (
        f"when this arrives, {_a(effect.profile)} joins the gang, free — "
        "and leaves again if this goes.",
        (
            "The model is created when this is bought — free, with XP and "
            "injuries of its own. Selling this removes it too."
        ),
    )


@_renders("op_changes_counter")
def _says_op_changes_counter(effect, parts):
    who = parts.who
    counter = _owned(who, str(effect.counter))
    if effect.mode == effect.Mode.ADD:
        moved = f"{effect.amount} is added to {counter}"
    elif effect.mode == effect.Mode.SUBTRACT:
        moved = f"{effect.amount} is taken from {counter}"
    else:
        moved = f"{counter} is set to {effect.amount}"
    return (
        f"when this arrives, {moved} — written on the ledger once; "
        "taking this away does not take it back.",
        (
            "Happens once, when this is assigned. Removing it later does "
            "not undo the change."
        ),
    )


def _and_then(names, joiner="and"):
    """Several names said as a list — "A, B and C", or with ``joiner``
    "or" where any one of them will do."""
    names = list(names)
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} {joiner} {names[-1]}"


def sentence_for(modifier, carriage=UNATTACHED, thing=None, chain=None):
    """One modifier, as a sentence about whoever carries it.

    ``carriage`` says who that is (``KIT``, ``CARD``, ``SUBTYPE``,
    ``GANG``, or ``UNATTACHED`` for a modifier nothing carries yet).
    ``thing`` is the carrier itself, which a subtype's sentence names.
    """
    from n26.library.models.modifier import GANG as GANG_TARGET
    from n26.library.models.modifier import _possible_kinds

    scope, effect = modifier.scope, modifier.effect
    # What the scope can ever reach, asked of the modifier's own rule
    # rather than restated here: a sentence that disagreed with the
    # constraint would describe a modifier the database refuses.
    target = _possible_kinds(scope)[0].kind
    who = _who(carriage, thing)
    if getattr(scope, "reach", None) == "every_model" and carriage is not GANG:
        # The author said everyone, so the sentence speaks of everyone —
        # while the carrier's own persistence still says how long, since
        # whoever holds it is not the gang.
        spoken = _who(GANG)
        who = _Who(
            subject=spoken.subject,
            possessive=spoken.possessive,
            weapons=spoken.weapons,
            plural=spoken.plural,
            persistence=who.persistence,
            asked=who.asked,
        )
    if target == GANG_TARGET:
        # The gang is the one thing every carrier reaches the same way,
        # so who holds the carrier stops mattering here.
        who = _Who(
            subject="the gang",
            possessive="the gang's",
            weapons="the gang's weapons",
            plural=False,
            persistence="",
            asked="the gang",
        )
    who, lead = _narrowed(who, scope)
    renderer = DOWNSTREAM[_effect_field(modifier)]
    said, hint = renderer(effect, _Parts(who=who, target=target, chain=chain or {}))
    if lead:
        said = f"{lead}, {said}"
    if getattr(scope, "reach", None) == "bearer" and carriage is GANG:
        # A bearer-reach modifier on something the gang holds: the
        # broadcast copy reaches nobody, and only saying so stops the
        # sentence promising everyone.
        hint += (
            " Only the model this is assigned to directly — what the "
            "gang holds does not reach anyone this way."
        )
    return Sentence(text=capfirst(said), hint=hint, key=_identity(modifier))


def _effect_field(modifier):
    from n26.library.models.modifier import EFFECT_FIELDS

    for name in EFFECT_FIELDS:
        if getattr(modifier, f"{name}_id") is not None:
            return name
    return None


@dataclass
class _Narrowings:
    """What a model scope's conditions narrow it to, sorted by the shape
    each takes in the sentence."""

    #: Ranks or entries named outright: they become the subject.
    named: list = field(default_factory=list)
    #: Types the model must be, lowercased: "vehicle".
    types: list = field(default_factory=list)
    #: Ranks, entries or types the row leaves out, worded: "Champion",
    #: "vehicles".
    left_out: list = field(default_factory=list)
    #: Whether one of ``left_out`` is a Type, which widens a gang-wide
    #: subject to "every model" — a vehicle left out of "every fighter"
    #: would read as though vehicles were fighters.
    a_type_left_out: bool = False
    #: Picks the model must hold or not hold, as ``(left out, names said
    #: as any of them)``: ``(False, "Cawdor")``, ``(True, "Cawdor or
    #: Delaque")``. Worded where the subject is known, because a phrase
    #: and a clause say them differently.
    picks: list = field(default_factory=list)
    #: Clauses about the moment rather than the model.
    clauses: list = field(default_factory=list)


def _names_ranks(row, found):
    names = [str(one) for one in row.subtypes.all()]
    (found.left_out if row.negate else found.named).extend(names)


def _names_entries(row, found):
    names = [str(one) for one in row.profiles.all()]
    (found.left_out if row.negate else found.named).extend(names)


def _names_type(row, found):
    types = [str(one).lower() for one in row.profile_types.all()]
    if not types:
        # An empty row says nothing, as its condition narrows nothing.
        return
    if row.negate:
        found.left_out.extend(f"{kind}s" for kind in types)
        found.a_type_left_out = True
    else:
        found.types.extend(types)


def _names_pick(row, found):
    picks = [str(one) for one in row.pickables.all()]
    if picks:
        # A row naming several picks is satisfied by any one of them.
        found.picks.append((row.negate, _and_then(picks, "or")))


def _names_threshold(row, found):
    found.clauses.append(f"while their {row.counter} is {row.at_least} or more")


#: How each condition a model scope can carry reaches the sentence, by
#: the condition's related name on the scope. It must name every entry
#: in the scope's ``CONDITIONS``: a kind missing here would be dropped
#: without a word, and the sentence would claim a wider reach than the
#: modifier has. A weapon scope's conditions join the noun phrase in
#: their own words instead.
MODEL_NARROWINGS = {
    "has_subtypes": _names_ranks,
    "is_profile": _names_entries,
    "is_profile_type": _names_type,
    "has_pickable": _names_pick,
    "counter_at_least": _names_threshold,
}


def _narrowed(who, scope):
    """The subject once the scope's conditions have had their say.

    Each narrowing has its own shape, because each means something
    different. Ranks or entries named become the subject — "Champion and
    Leader" says who is reached better than any pronoun could, in the
    names as authored, because a content name is never inflected — and
    a Type beside them is their kind: "Champion vehicles". A Type alone
    is the model's own word, "every vehicle". Whatever a row leaves out
    follows after one "except"; a pick held joins as "with" or
    "without", before the exception so it qualifies the subject and not
    what was left out. A threshold becomes a clause in front, being a
    condition on the moment rather than on the person, and the sentence
    then drops its own "while" so as not to say the same thing twice.

    A subject that is a pronoun or a clause takes no phrase after it, so
    its narrowings lead the sentence as clauses too: "While holding
    Cawdor, they gain …". A narrowing of the weapons joins the noun
    phrase, in the words the condition row says of itself, so the
    modifier's own name and this sentence cannot come to describe the
    selection differently.
    """
    if not getattr(scope, "CONDITIONS", ()) or scope.pk is None:
        return who, ""
    found = _Narrowings()
    of_weapons = []
    for related in scope.CONDITIONS:
        record = MODEL_NARROWINGS.get(related)
        for row in getattr(scope, related).all():
            if record is not None:
                record(row, found)
            else:
                of_weapons.append(str(row))

    subject, plural = who.subject, who.plural
    if found.named:
        subject = _and_then(found.named)
        plural = len(found.named) != 1
        if found.types:
            kinds = _and_then((f"{kind}s" for kind in found.types), "or")
            subject = f"{subject} {kinds}"
            plural = True
    elif found.types:
        subject = f"every {_and_then(found.types, 'or')}"
        plural = False
    elif found.a_type_left_out and who.qualifiable:
        subject = "every model"

    clauses = list(found.clauses)
    qualified = False
    if who.qualifiable or subject != who.subject:
        if found.picks:
            phrases = [
                f"{'without' if left_out else 'with'} {held}"
                for left_out, held in found.picks
            ]
            subject = f"{subject} {' and '.join(phrases)}"
        if found.left_out:
            subject = f"{subject} except {_and_then(found.left_out)}"
        qualified = bool(found.picks or found.left_out)
    else:
        # "They with Cawdor" is no sentence: a pronoun's narrowings are
        # said up front instead, and the closing "while" gives way to them.
        clauses.extend(
            f"while {'not holding' if left_out else 'holding'} {held}"
            for left_out, held in found.picks
        )
        if found.left_out:
            clauses.append(f"unless they are {_and_then(found.left_out, 'or')}")
    lead = " and ".join(clauses)

    possessive, weapons = who.possessive, " ".join([who.weapons, *of_weapons])
    if subject != who.subject:
        if qualified:
            weapons = " ".join([f"the weapons of {subject}", *of_weapons])
        else:
            possessive = f"{subject}'" if subject.endswith("s") else f"{subject}'s"
            weapons = " ".join([f"{possessive} weapons", *of_weapons])
    return (
        _Who(
            subject=subject,
            possessive=possessive,
            weapons=weapons,
            plural=plural,
            persistence="" if lead else who.persistence,
            asked=who.asked,
            qualifiable=who.qualifiable,
            qualified=qualified,
        ),
        lead,
    )


def _picks_asked(slot):
    """How many picks a choice takes, as a sentence says it."""
    if slot.min_picks == slot.max_picks:
        return "one" if slot.max_picks == 1 else str(slot.max_picks)
    return f"{slot.min_picks} to {slot.max_picks}"


def _asks(slot):
    """What a choice does by being on a card: it asks.

    Said before the modifiers a slot happens to carry, because this is
    the whole of what a choice is for and everything else is beside it.
    A hidden one asks nothing at all — the pick still arrives and still
    does everything it does, which is how several things come under one
    name.
    """
    count = _picks_asked(slot)
    named = slot.slot_type.name if slot.max_picks == 1 else slot.slot_type.plural
    bounds = (
        f"Fewer than {slot.min_picks} is a note on the card, never a "
        f"refusal, and the picker stops offering at {slot.max_picks}."
    )
    if slot.hidden:
        return Sentence(
            text=f"Holds {count} {named} from {slot.picklist}, and is hidden.",
            hint=(
                "No choice row is drawn. What is picked still does everything it does."
            ),
            key=_identity(slot.picklist),
        )
    said = f"Asks for {count} {named}, chosen from {slot.picklist}."
    if slot.assigned_to == slot.WillBeAssignedTo.GANG:
        said += (
            " What is chosen belongs to the gang and is broadcast, not to "
            "whoever was asked."
        )
    return Sentence(
        text=said,
        hint=(
            f"The choice stays on the card until it is made, and making it "
            f"late costs nothing. {bounds}"
        ),
        key=_identity(slot.picklist),
    )


def _structural(thing):
    """What a kind does by being what it is, before any modifier speaks.

    Only a choice has anything to say here: everything else on a card
    does what its modifiers do and nothing more.
    """
    from n26.library.models import Slot

    return (_asks(thing),) if isinstance(thing, Slot) else ()


def _does(thing, carriage):
    """Every modifier the thing carries, in the order the rules run them.

    Application order is specificity: an unconditional grant settles
    before anything that could depend on it, which is how "the Cutter
    grants Mounted" reaches a rule about Mounted models. Saying them in
    any other order would tell the reader a different story from the one
    the card lives by.
    """
    from n26.core import select

    modifiers = list(reading_sentences(thing.modifiers.all()))
    chain = _grants_of(
        [
            modifier.adds_assignable.thing
            for modifier in modifiers
            if modifier.adds_assignable_id is not None
            and modifier.adds_assignable.thing is not None
        ]
    )
    ordered = sorted(
        modifiers,
        key=lambda modifier: select.specificity(modifier.scope.as_selector()),
    )
    return (
        *_structural(thing),
        *(
            sentence_for(modifier, carriage, thing=thing, chain=chain)
            for modifier in ordered
        ),
    )


def _grants_of(things):
    """What each of these things gives in its own right, keyed by identity.

    The chain clause: a grant that hands over something which itself
    hands over something. One query per kind present and one for the
    modifiers, never one per thing — a bundle handing over eight rules
    is read at the price of a bundle handing over one.
    """
    from n26.library.models import Modifier
    from n26.library.models.modifier import GRANTABLE_FIELDS

    by_kind = {}
    for thing in things:
        by_kind.setdefault(type(thing), []).append(thing)
    carried = {}
    for model, rows in by_kind.items():
        through = model._meta.get_field("modifiers").remote_field.through
        column = model._meta.model_name
        for carrier, modifier in through.objects.filter(
            **{f"{column}__in": rows}
        ).values_list(f"{column}_id", "modifier_id"):
            carried.setdefault(modifier, []).append((model, carrier))
    if not carried:
        return {}
    gives = {}
    grants = Modifier.objects.filter(
        pk__in=carried, adds_assignable__isnull=False
    ).select_related(
        "adds_assignable",
        *(f"adds_assignable__{name}" for name in GRANTABLE_FIELDS),
    )
    for modifier in grants:
        given = modifier.adds_assignable.thing
        if given is None:
            continue
        for model, pk in carried[modifier.pk]:
            gives.setdefault((model._meta.label_lower, pk), []).append(str(given))
    return gives


# --- Upstream: how anyone comes to have it ---------------------------------


def _identity(row):
    """A row's identity for decoration — the same pair selectors key on."""
    return (type(row)._meta.label_lower, row.pk)


def _named(row):
    """A row as a sentence names it: what an author calls it, and its kind.

    Reads nothing but the row: an assignable says itself out of its own
    name and annotation, so a sentence naming fifty carriers costs no
    queries at all.
    """
    label = getattr(row, "authoring_label", None) or str(row)
    return f"the {label} {row._meta.verbose_name}"


def _modifier_of(row):
    """The modifier an effect row belongs to, or None for an orphan.

    An effect with no modifier is content half-written rather than a
    bug, and a page about something else should say the rest and move on.
    """
    from django.core.exceptions import ObjectDoesNotExist

    try:
        return row.modifier
    except ObjectDoesNotExist:
        return None


@dataclass(frozen=True)
class _Edges:
    """Every edge into a thing, read once and shared by the sentences.

    Four sweeps, each batched and each a fixed number of queries: what
    names the thing, what holds the sets it is built into, what carries
    the modifiers naming it, and which collections sweep its kind in.
    Gathered here rather than by each sentence, because a sentence that
    fetched its own subject would charge the page once per route it
    found.
    """

    thing: object
    references: tuple
    #: References into the sets the thing is built into — the things
    #: holding those sets, and the options offering them.
    holders: tuple
    #: The carriers of every modifier naming the thing, keyed by modifier.
    carriers: dict
    #: The offered choices its kind could be chosen for.
    offers: tuple
    #: The sweeps that catch the thing without naming it.
    swept: tuple = ()


def _edges_into(thing):
    references = references_to(thing)
    sets = _sets_holding(references)
    holders = references_to(*sets) if sets else ()
    offers = _offers_of_kind(thing)
    naming = [
        reference.row
        for label in (
            "library.addsassignable",
            "library.removesassignable",
            "library.opaddsminiature",
        )
        for reference in of_kind(references, label)
    ]
    wanted = [
        modifier
        for modifier in (_modifier_of(row) for row in (*naming, *offers))
        if modifier is not None
    ]
    return _Edges(
        thing=thing,
        references=references,
        holders=holders,
        carriers=_carriers_of(wanted),
        offers=offers,
        swept=_sweeps_catching(thing),
    )


def _sweeps_catching(thing):
    """The sweeps of the thing's kind that actually catch it.

    A sweep says a kind and a narrowing rather than a row, so nothing
    points at the thing and there is no edge to read — the sweeps of its
    kind are fetched and asked in memory, exactly as a browse asks them.
    Read here rather than where a sentence wants them, because two
    readers want the same answer: what offers the thing, and which
    offered choices it can genuinely be chosen for.
    """
    from django.contrib.contenttypes.models import ContentType

    from n26.core import select
    from n26.library.models import CollectionSelector

    sweeps = CollectionSelector.objects.filter(
        of_kind=ContentType.objects.get_for_model(type(thing))
    ).select_related("collection", "category")
    target = select.matchable(thing)
    return tuple(sweep for sweep in sweeps if sweep.as_selector().matches(target))


def _sets_holding(references):
    """The sets of defaults naming the thing, by identity.

    Archived memberships are skipped: an archived member no longer
    materialises, so a page saying the thing is built into something
    would contradict what a hire actually brings.
    """
    from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS

    sets = {}
    for reference in of_kind(references, "library.defaultassignment"):
        if reference.field in DEFAULT_ASSIGNABLE_FIELDS and not reference.row.archived:
            sets[reference.row.default_set_id] = reference.row.default_set
    return list(sets.values())


def _offers_of_kind(thing):
    """Every offered choice this thing's kind could be chosen for."""
    from django.contrib.contenttypes.models import ContentType

    from n26.library.models import OffersChoice

    return tuple(
        OffersChoice.objects.filter(
            of_kind=ContentType.objects.get_for_model(type(thing))
        ).select_related("from_section__collection", "modifier")
    )


def _carriers_of(modifiers):
    """Everything holding each of these modifiers, keyed by modifier.

    The kinds share no table, so the pairs are asked for one kind at a
    time — per call, though, never per modifier: a thing named by twenty
    modifiers is read at the price of one. The rows themselves are
    fetched only for the kinds that turned out to carry something, and
    plain, because a carrier says itself out of its own columns.
    """
    if not modifiers:
        return {}
    wanted = [modifier.pk for modifier in modifiers]
    carriers = {}
    for model in carrying_models():
        pairs = list(
            model.objects.filter(modifiers__in=wanted).values_list("pk", "modifiers")
        )
        if not pairs:
            continue
        rows = model.objects.in_bulk({pk for pk, _ in pairs})
        for pk, modifier in pairs:
            carriers.setdefault(modifier, []).append(rows[pk])
    return carriers


def _asking(credits):
    """What a listing asks for, as the tail of "offered by X …"."""
    if not credits:
        return "free"
    return f"at {credits} credit{'' if credits == 1 else 's'}"


def _price_facts(price):
    """A price said as facts, for the hint behind an offer.

    Both halves of what a buyer pays with, because the Trading Post half
    is the one a listing's own words leave out: an exclusive item is on
    an equipment list and nowhere else, and a thing with no trade-point
    price cannot be had for trade points at all.
    """
    if not price.credits:
        asked = "Free"
    else:
        asked = f"{price.credits} credit{'' if price.credits == 1 else 's'}"
    if price.is_exclusive:
        return f"{asked}; equipment list only, not at the Trading Post."
    if price.trade_points is None:
        return f"{asked}; no Trading Post price."
    points = f"{price.trade_points} trade point{'' if price.trade_points == 1 else 's'}"
    return f"{asked}; {points} at the Trading Post."


def _reaches_the_gang(edges):
    """Whether any edge puts the thing in the gang's own hands.

    Two ways it can: a gang type's built-ins, which every gang of that
    type is founded with, and a grant whose scope is the gang itself.
    Either way what it does reaches every member, so its sentences speak
    of every fighter rather than of a bearer.
    """
    from n26.library.models import CampaignType, GangType

    for reference in of_kind(edges.references, "library.addsassignable"):
        modifier = _modifier_of(reference.row)
        if modifier is not None and modifier.targets_gang_id is not None:
            return True
    return any(
        reference.field == "built_ins"
        and isinstance(reference.row, (CampaignType, GangType))
        for reference in edges.holders
    )


def _referenced_by(edges):
    """Every route by which somebody ends up holding this.

    Ordered as the reader needs it: what is structurally true first —
    built into something, given by something, taken away by something —
    and the routes that merely *may* happen after, because a collection
    that stocks it and a choice it could be chosen for are possibilities
    rather than facts.
    """
    said = [
        *_built_into(edges),
        *_started_with(edges),
        *_listed(edges),
        *_granted(edges),
        *_brought(edges),
        *_offered(edges),
        *_may_be_chosen(edges),
        *_offered_by_a_choice(edges),
    ]
    return tuple(_once(said))


#: What a sentence calls whatever carries a modifier when nothing does
#: yet, so the hint can still say when the thing arrives and when it goes.
_UNCARRIED = "the thing that carries it"

_GIVEN_HINT = (
    "Applies while {x} is assigned, and goes if {x} goes. Never bought or paid for."
)

_TAKEN_HINT = (
    "Removed while {x} is assigned. Nothing is deleted — remove {x} and "
    "this comes back. Paid-for items are never removed."
)


def _built_in_hint(holder=None):
    """When a built-in arrives and when it goes, said of what holds it.

    The holder is named where there is one, because the moment it arrives
    is a fact about that thing rather than about built-ins in general.
    """
    named = _named(holder) if holder is not None else "the thing it is built into"
    return (
        f"Arrives free when {named} is assigned — hired, founded, or "
        "bought. If that goes, this goes with it."
    )


def _built_into(edges):
    sets = _sets_holding(edges.references)
    if not sets:
        return []
    said = []
    for reference in edges.holders:
        if reference.field == "built_ins":
            said.append(
                Sentence(
                    text=f"Built into {_named(reference.row)}.",
                    hint=_built_in_hint(reference.row),
                    key=_identity(reference.row),
                )
            )
        elif reference.label == "library.option":
            option = reference.row
            said.append(
                Sentence(
                    text=(
                        f"Taken with the “{option.name}” option of "
                        f"{_named(option.carrier)}."
                    ),
                    hint="Only fighters who took this option get it.",
                    key=_identity(option),
                )
            )
    if not said:
        named = _and_then([f"“{name}”" for name in sorted(one.name for one in sets)])
        said.append(
            Sentence(
                text=f"Part of the {named} kit, which nothing uses yet.",
                hint=_built_in_hint(),
            )
        )
    return said


def _picklists_holding(edges):
    """The lists offering the thing, by identity."""
    lists = {}
    for reference in of_kind(edges.references, "library.picklistmember", "pickable"):
        lists[reference.row.picklist_id] = reference.row.picklist
    return lists


def _listed(edges):
    """The picklists that offer the thing.

    A fact about each picklist rather than a route on its own: being on
    a picklist is how a pickable comes to be offered, and which choices
    do the offering is said further down.
    """
    return [
        Sentence(
            text=f"Listed in {picklist}.",
            hint=(
                "A list of pickables for a slot. Everything on this list "
                "is offered wherever a slot offers a choice."
            ),
            key=_identity(picklist),
        )
        for picklist in sorted(_picklists_holding(edges).values(), key=str)
    ]


def _offered_by_a_choice(edges):
    """The choices that draw on a list the thing is on — the "may" half.

    A choice names a picklist, so nothing points at the pickable itself:
    every choice drawing on a list that offers it is a way somebody could
    come to have it. One query however many lists hold it.
    """
    from n26.library.models import Slot

    lists = _picklists_holding(edges)
    if not lists:
        return []
    return [
        Sentence(
            text=f"May be chosen for {_named(slot)}.",
            hint=(
                "This slot offers a choice from a picklist that contains this pickable."
            ),
            key=_identity(slot),
        )
        for slot in Slot.objects.filter(picklist__in=lists).order_by("name")
    ]


def _started_with(edges):
    """The choices this arrives already settling — a slot with a default.

    A route of its own: nothing gives the pickable and nobody picks it,
    it simply comes with the choice, changed afterwards by the ordinary
    rechoose.
    """
    return [
        Sentence(
            text=f"Chosen from the start for {_named(reference.row.slot)}.",
            hint="Arrives already picked. Players can change it.",
            key=_identity(reference.row.slot),
        )
        for reference in of_kind(
            edges.references, "library.defaultassignment", "default_pickable"
        )
        if reference.row.slot_id is not None
    ]


def _granted(edges):
    """Who gives it and who takes it away — the modifier routes."""
    routes = [
        ("library.addsassignable", "Given", " to the gang", _GIVEN_HINT),
        ("library.removesassignable", "Taken away", " from the gang", _TAKEN_HINT),
    ]
    said = []
    for label, verb, of_the_gang, hint in routes:
        for reference in of_kind(edges.references, label):
            modifier = _modifier_of(reference.row)
            if modifier is None:
                continue
            # Whose copy it is: a gang-scoped grant puts the thing in the
            # gang's own hands, where it reaches every member without
            # drawing a line on anybody's card.
            whose = of_the_gang if modifier.targets_gang_id is not None else ""
            holders = edges.carriers.get(modifier.pk, ())
            if not holders:
                said.append(
                    Sentence(
                        text=f"{verb}{whose} by a modifier nothing carries yet.",
                        hint=hint.format(x=_UNCARRIED),
                        key=_identity(modifier),
                    )
                )
            for holder in holders:
                named = _named(holder)
                said.append(
                    Sentence(
                        text=f"{verb}{whose} by {named}.",
                        hint=hint.format(x=named),
                        key=_identity(holder),
                    )
                )
    return said


def _brought(edges):
    """The stored effect that hires this fighter entry into a gang."""
    said = []
    for reference in of_kind(edges.references, "library.opaddsminiature", "profile"):
        modifier = _modifier_of(reference.row)
        if modifier is None:
            continue
        for holder in edges.carriers.get(modifier.pk, ()):
            named = _named(holder)
            said.append(
                Sentence(
                    text=f"Brought by {named}.",
                    hint=(
                        f"Created when {named} is bought — free, with XP and "
                        f"injuries of its own. Selling {named} removes it too."
                    ),
                    key=_identity(holder),
                )
            )
    return said


def _entries_naming(edges):
    """The entries that list the thing — the rows that put it in a catalogue.

    Gated to the columns that mean listing: an entry's usable-by columns
    name the fighters a line is for, and a line about somebody is not a
    line offering them.
    """
    from n26.library.models.collection import ENTRY_ASSIGNABLE_FIELDS

    return tuple(
        reference.row
        for reference in of_kind(edges.references, "library.collectionentry")
        if reference.field in ENTRY_ASSIGNABLE_FIELDS
    )


def _collections_holding(edges):
    """Every collection the thing is in, by identity.

    A collection holds a thing two ways and no others: an entry names
    it, or one of the collection's sweeps catches it.
    """
    held = {entry.collection_id for entry in _entries_naming(edges)}
    held.update(sweep.collection_id for sweep in edges.swept)
    return held


def _offered(edges):
    """Two routes to being sold: a list that names it, and a sweep that
    catches it."""
    from n26.library.models.collection import price_of

    thing = edges.thing
    said, listed = [], set()
    for entry in _entries_naming(edges):
        listed.add(entry.collection_id)
        # Priced against the thing in hand rather than through the
        # entry's own pointer back to it: the row is already loaded, and
        # asking the entry would fetch it again for every list that
        # stocks it.
        price = price_of(thing, entry=entry)
        narrowing = entry.usable_by_words()
        only = f", to {narrowing} only" if narrowing else ""
        hint = _price_facts(price)
        if narrowing:
            hint += (
                " Other fighters still see it on the list, with a note — "
                "nothing is blocked."
            )
        said.append(
            Sentence(
                text=(
                    f"Offered by {entry.collection.name} "
                    f"{_asking(price.credits)}{only}."
                ),
                hint=hint,
                key=_identity(entry.collection),
            )
        )
    said.extend(_swept(thing, edges.swept, listed))
    return said


def _swept(thing, sweeps, listed):
    """Collections that sweep the thing in without naming it.

    A collection that does both speaks once, in its entry's voice: an
    entry wins over a sweep for the same item, so the sweep's reference
    price is not what the reader would be asked for, and two "Offered
    by" sentences from one collection at two prices tell them nothing true.
    """
    from n26.library.models.collection import price_of

    return [
        Sentence(
            text=(
                f"Offered by {sweep.collection.name} "
                f"{_asking(price_of(thing).credits)}, swept in as {sweep}."
            ),
            hint=(
                "On this list because a rule includes it (“every weapon”), "
                "not because someone listed it. A hand-written entry for the "
                "same item overrides this."
            ),
            key=_identity(sweep.collection),
        )
        for sweep in sweeps
        if sweep.collection_id not in listed
    ]


def _may_be_chosen(edges):
    """Offered choices this could be chosen for — the "may" half.

    An offer names a kind, not a row, so nothing points at the thing:
    every choice of its kind is a way somebody could come to have it.

    An offer drawing from a section is narrower than its kind, though.
    What a player is shown there is what the section's collection holds,
    resectioned for their model — so a thing that collection neither
    lists nor sweeps in can never be chosen for that choice, whatever
    kind it is, and saying it may be would offer a route nobody can
    take.
    """
    holding = _collections_holding(edges)
    said = []
    for offer in edges.offers:
        if (
            offer.from_section_id is not None
            and offer.from_section.collection_id not in holding
        ):
            continue
        hint = (
            "The offered choice is on the card while the thing offering it "
            "is, and this is one of the things that can be chosen."
        )
        if offer.from_section_id is not None:
            hint += (
                f" Narrowed to what appears as {offer.from_section.name} for "
                "that model, so a model the set is not placed for is never "
                "offered it."
            )
        modifier = _modifier_of(offer)
        holders = edges.carriers.get(modifier.pk, ()) if modifier else ()
        if not holders:
            said.append(
                Sentence(
                    text=(
                        f"May be chosen for an offered choice of {offer.kind_label}."
                    ),
                    hint=hint,
                )
            )
        said.extend(
            Sentence(
                text=(
                    f"May be chosen for the {offer.kind_label} choice "
                    f"offered by {_named(holder)}."
                ),
                hint=hint,
                key=_identity(holder),
            )
            for holder in holders
        )
    return said


def _once(sentences):
    """The same sentence said twice is one sentence."""
    seen, kept = set(), []
    for sentence in sentences:
        if sentence.text in seen:
            continue
        seen.add(sentence.text)
        kept.append(sentence)
    return kept


# --- The player side -------------------------------------------------------


def assigned_to(thing):
    """How many rows and how many gangs are standing on this thing.

    ``None`` for a kind nobody can be assigned — a modifier, a set of
    defaults — where the question has no answer rather than an answer of
    nought.
    """
    from django.db.models import Count

    from n26.core.models import Assignment
    from n26.core.models.assignment import ASSIGNABLE_FIELDS

    column = _assignment_column(type(thing), ASSIGNABLE_FIELDS)
    if column is None:
        return None
    # Archived rows are things somebody parted with, so they hold
    # nothing; every reader that counts a gang's own rows leaves them
    # out the same way. An assignment that *removes* its assignable is
    # the opposite of holding it, so those are left out too.
    tally = Assignment.objects.filter(
        archived=False, removes=False, **{column: thing}
    ).aggregate(rows=Count("pk"), gangs=Count("gang_root", distinct=True))
    return AssignedTo(gangs=tally["gangs"], rows=tally["rows"])


def _assignment_column(model, fields):
    from django.apps import apps

    for name, path in fields.items():
        if apps.get_model(path) is model:
            return name
    return None


# --- The whole thing -------------------------------------------------------


def prose_for(thing):
    """Everything the reach column says about one piece of content.

    Handed a ``Modifier``, it says the one sentence that modifier amounts
    to and who carries it — what the composer needs while a modifier is
    being written, before it belongs to anything.
    """
    from n26.library.models import Modifier

    if isinstance(thing, Modifier):
        return _prose_for_modifier(thing)

    edges = _edges_into(thing)
    return Prose(
        referenced_by=_referenced_by(edges),
        does=_does(thing, carriage_of(thing, edges)),
        assigned_to=assigned_to(thing),
    )


def _prose_for_modifier(modifier):
    from n26.library.models import Modifier

    loaded = reading_sentences(Modifier.objects.filter(pk=modifier.pk)).first()
    carriers = _carriers_of([loaded]).get(loaded.pk, ())
    carrier = carriers[0] if carriers else None
    carriage = (
        carriage_of(carrier, _edges_into(carrier))
        if carrier is not None
        else UNATTACHED
    )
    return Prose(
        referenced_by=tuple(
            Sentence(
                text=f"Carried by {_named(holder)}.",
                hint=(
                    "A modifier is shared: editing it changes it everywhere "
                    "it is carried."
                ),
                key=_identity(holder),
            )
            for holder in carriers
        ),
        does=(sentence_for(loaded, carriage, thing=carrier, chain=_chain_for(loaded)),),
        assigned_to=None,
    )


def _chain_for(modifier):
    if modifier.adds_assignable_id is None:
        return {}
    given = modifier.adds_assignable.thing
    return _grants_of([given]) if given is not None else {}
