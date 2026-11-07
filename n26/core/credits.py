"""Access, validation and writes shared by Manage credits transports."""

from dataclasses import dataclass

from django.urls import reverse

from n26.core.forms import CreditsForm
from n26.core.models import LedgerEvent
from n26.core.operations import NotEnoughCredits, Refusal, operation
from n26.core.views.permissions import credits_campaign

DIRECTION_HELP = {
    CreditsForm.ADD: "Credits the gang gained outside the app, such as a scenario reward.",
    CreditsForm.REMOVE: (
        "Credits the gang spent or lost outside the app. "
        "To buy equipment, use Equip instead."
    ),
}


def destination(gang, user):
    """Default return URL, or None when the user cannot change credits."""
    if gang.archived or gang.credits_unlimited:
        return None
    if gang.owner_id == user.pk:
        return reverse("n26-gang", args=[gang.pk])
    campaign = credits_campaign(gang, user)
    if campaign is not None:
        return reverse("n26-campaign", args=[campaign.pk]) + "#gangs"
    return None


def still_allowed(gang, user):
    """Check access using the gang's state after acquiring its lock."""
    gang.refresh_from_db(fields=["archived", "owner", "starting_credits"])
    return destination(gang, user) is not None


@dataclass
class CreditChange:
    form: CreditsForm
    amount: int = 0
    applied: bool = False
    saved: bool = False
    conflict: bool = False

    def message(self, gang):
        if self.amount > 0:
            return f"Added {self.amount}¢ to {gang.name}."
        return f"Removed {-self.amount}¢ from {gang.name}."


def change(gang, user, data):
    result = CreditChange(CreditsForm(data))
    form = result.form
    if not form.is_valid():
        return result
    amount = form.signed_amount()
    key = form.cleaned_data["request_key"]
    note = form.cleaned_data["note"]
    try:
        with operation(gang, actor=user) as op:
            if not still_allowed(gang, user):
                raise Refusal("You can no longer change this gang's credits.")
            previous = LedgerEvent.objects.filter(gang=gang, request_key=key).first()
            if previous is not None:
                if (
                    previous.kind != LedgerEvent.Kind.CREDITS_ADJUSTED
                    or previous.actor_id != user.pk
                    or previous.credits_delta != -amount
                    or previous.note != note
                ):
                    result.conflict = True
                    raise Refusal(
                        "A different change was already saved from this form. Reload the page."
                    )
            else:
                op.adjust_credits(amount, note, request_key=key)
        result.applied = previous is None
        result.amount = amount
        result.saved = True
    except NotEnoughCredits as short:
        had = -amount - short.shortfall
        form.add_error(
            "amount", f"You cannot remove more than {gang.name} has ({had}¢)."
        )
    except Refusal as refusal:
        form.add_error(None, refusal.public_message)
    gang.refresh_from_db(fields=["credits"])
    return result


def display(gang, user, form):
    """JSON-safe workflow facts for both initial and failed submissions."""
    from n26.core.people import person_link

    direction = form["direction"].value()
    if direction not in {CreditsForm.ADD, CreditsForm.REMOVE}:
        direction = CreditsForm.ADD
    badges = {}
    owner = person_link(gang.owner, badges) if gang.owner_id else {"name": ""}
    owner["badge"] = badges.get(owner.get("badge"))
    return {
        "gangName": gang.name,
        "balance": gang.credits,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "owner": owner,
        "historyHref": (
            reverse("n26-gang-history", args=[gang.pk]) + "?kind=credits"
            if gang.owner_id == user.pk
            else ""
        ),
        "directions": [
            {"value": value, "label": label, "description": DIRECTION_HELP[value]}
            for value, label in form.fields["direction"].choices
        ],
        "values": {
            "direction": direction,
            "amount": form["amount"].value() or "",
            "note": form["note"].value() or "",
            "request_key": str(form["request_key"].value() or ""),
        },
        "errors": dict(form.errors),
        "noteHelp": form.fields["note"].help_text,
    }
