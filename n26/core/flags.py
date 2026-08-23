"""Which accounts may reach a feature that is still being built.

A feature under construction ships gated: its code lands on the main branch
like any other, but only the accounts named here can open it, so half a
screen is never a stranger's first impression of it.

There are two controls because they answer different questions, and both
have to agree before anyone gets in. The **setting** says whether the
feature exists at all — turning it off takes it away from everybody,
including the people on the allowlist, which is what makes it a kill
switch and the thing to reach for when a half-built screen starts writing
bad rows. The **allowlist** says who gets it while it does exist, and is an
ordinary group an administrator can add people to and take them out of
without a deploy.

Availability is one of three words rather than a boolean, because "off",
"a few people" and "everyone" are three states and inferring the middle one
from whether a group happens to exist makes a typo indistinguishable from a
launch.

A gated view answers a reader who may not see it with **404, never 403**:
which features are being built is not something to be probed for, and every
other guard in this edition already answers a stranger the same way. Signing
in is required even where the ungated page would not ask for it — a feature
nobody is supposed to know about should not announce itself to a visitor.

There is no bypass for staff or superusers. An account that should see a
gated feature goes on its allowlist, so what a person can reach is one
question with one answer rather than two rules that drift.
"""

from dataclasses import dataclass
from functools import wraps

from django.conf import settings
from django.http import Http404


class Availability:
    """How widely a feature is open. Stored as the setting's value."""

    #: Nobody, whatever the allowlist says. The kill switch.
    OFF = "off"
    #: Whoever is in the feature's group.
    ALLOWLIST = "allowlist"
    #: Every signed-in reader. What shipping looks like.
    EVERYONE = "everyone"

    ALL = (OFF, ALLOWLIST, EVERYONE)


@dataclass(frozen=True)
class Flag:
    """One gated feature: what it is called, where its switch is, and which
    group holds the people allowed in while it is being built."""

    name: str
    setting: str
    group: str


#: Every gated feature in this edition, by the name callers use.
FLAGS = {
    "campaigns": Flag(
        name="campaigns",
        setting="N26_FLAG_CAMPAIGNS",
        group="N26 Campaigns",
    ),
}


def availability(flag):
    """What the setting says, refusing anything it does not recognise.

    An unrecognised word is a deployment mistake rather than something a
    reader can cause, so it raises instead of guessing. Guessing "off"
    would hide a launched feature and guessing "everyone" would leak an
    unfinished one; both are worse than a failure that names itself.
    """
    state = getattr(settings, flag.setting, Availability.OFF)
    if state not in Availability.ALL:
        raise ValueError(
            f"{flag.setting} is {state!r}; expected one of {Availability.ALL}"
        )
    return state


def enabled(name, user):
    """Whether this account may reach the named feature.

    An unknown name is a caller's mistake, not a reader's, so it raises.
    """
    try:
        flag = FLAGS[name]
    except KeyError:
        raise ValueError(f"No such feature flag: {name!r}") from None

    state = availability(flag)
    if state == Availability.OFF:
        return False
    if not user or not user.is_authenticated:
        return False
    if state == Availability.EVERYONE:
        return True
    return user.groups.filter(name=flag.group).exists()


def requires_flag(name):
    """Guard a view with a feature flag, answering 404 where it is closed.

    Sits outside ``login_required`` where a view has both, so that a
    visitor to a gated address is told the page does not exist rather than
    being sent to sign in and learning that something is there.
    """

    def decorate(view):
        @wraps(view)
        def guarded(request, *args, **kwargs):
            if not enabled(name, request.user):
                raise Http404(f"The {name} feature is not open to this account")
            return view(request, *args, **kwargs)

        return guarded

    return decorate
