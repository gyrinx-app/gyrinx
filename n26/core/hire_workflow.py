"""Offer resolution, validation and retriable hires shared by HTTP adapters."""

from dataclasses import dataclass

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from n26.core.forms import HireFighterForm
from n26.core.models import HireReceipt
from n26.core.operations import Refusal, operation
from n26.core.prices import BadPrice, price_typed
from n26.library.staged import sees_staged


class UnavailableHire(Exception):
    """The submitted offer or option cannot be resolved."""


class SelectionField(forms.JSONField):
    default_error_messages = {"invalid": "Choose the model options again."}

    def validate(self, value):
        super().validate(value)
        if value is None:
            return
        if (
            not isinstance(value, list)
            or any(not isinstance(key, str) or not key for key in value)
            or len(value) != len(set(value))
        ):
            raise forms.ValidationError("Choose the model options again.")


class HireSubmissionForm(HireFighterForm):
    selection = SelectionField(required=False, widget=forms.HiddenInput)
    request_key = forms.UUIDField(
        widget=forms.HiddenInput,
        error_messages={
            "required": "Reload this page before hiring.",
            "invalid": "Reload this page before hiring.",
        },
    )


@dataclass(frozen=True)
class Pick:
    field: str
    value: str
    option: object


def resolve_offer(raw, offers, *, include_staged=False):
    """Resolve the profile and validate an optional collection-price identity."""
    from n26.library.models import Profile

    profile_pk, _, entry_pk = (raw or "").partition("-")
    try:
        profiles = Profile.objects.filter(pk=profile_pk, hireable=True).unarchived()
        if not include_staged:
            profiles = profiles.live()
        profile = profiles.first()
    except ValidationError:
        profile = None
    if profile is None or not entry_pk:
        return profile, None
    entry = next(
        (
            offer.entry
            for offer in offers()
            if offer.entry is not None
            and str(offer.entry.pk) == entry_pk
            and offer.profile.pk == profile.pk
        ),
        None,
    )
    if entry is None:
        raise UnavailableHire("No such offer")
    return profile, entry


def resolve_picks(data, profile, entry, key=None):
    """Read the same option-group indices the catalogue submits."""
    prefix = slugify(key or str(profile.pk))
    picked = []
    for group_index, group in enumerate(entry.groups):
        field = f"{prefix}:{group_index}"
        for value in data.getlist(field):
            if value == "":
                continue
            try:
                if not value.isdigit():
                    raise ValueError(value)
                option = group.options[int(value)]
            except ValueError, IndexError:
                raise UnavailableHire("No such option") from None
            picked.append(Pick(field, value, option))
    return picked


def chosen_sets(picks):
    return [pick.option.default_set for pick in picks if pick.option.default_set]


def resolve_sets(profile, keys):
    """Resolve stable option identities, never their changing group positions."""
    offered = {
        str(option.pk): option.default_set
        for option in profile.options.select_related("default_set")
    }
    try:
        return [offered[key] for key in keys or []]
    except KeyError:
        raise UnavailableHire("No such option") from None


def base_price(entry):
    return entry.price_override if entry is not None else None


def quote(profile, picks, entry):
    return quote_sets(profile, chosen_sets(picks), entry)


def quote_sets(profile, selection, entry):
    try:
        return profile.price_with(selection, base=base_price(entry))
    except ValueError:
        raise UnavailableHire("No such option") from None


def command_payload(data, name, selection=None):
    """Retain submitted intent independently of later catalogue changes.

    Blank payment remains different from zero. UI destinations and credentials
    do not identify the acquisition. Legacy option fields retain their indices;
    stable selections retain the library option identifiers.
    """
    raw = data.get("profile", "")
    prefix = f"{slugify(raw)}:"
    payload = {
        "profile": raw,
        "name": name,
        "paid": data.get("paid", "").strip(),
        "rateAtPaid": data.get("rate") == "paid",
    }
    if "selection" in data:
        return {**payload, "version": 2, "selection": sorted(selection or [])}
    return {
        **payload,
        "version": 1,
        "options": {
            field: sorted(value for value in data.getlist(field) if value != "")
            for field in sorted(data)
            if field.startswith(prefix)
        },
    }


@dataclass
class HireResult:
    form: HireSubmissionForm
    receipt: HireReceipt | None = None
    miniature: object = None
    applied: bool = False
    conflict: bool = False
    refused: str = ""

    @property
    def saved(self):
        return self.receipt is not None

    @property
    def written(self):
        return set(self.receipt.written) if self.receipt else set()

    @property
    def message(self):
        receipt = self.receipt
        if not self.applied:
            return f"{receipt.model_name} was already hired."
        subject = (
            receipt.profile_name
            if receipt.model_name == receipt.profile_name
            else (f"{receipt.model_name} — {receipt.profile_name}")
        )
        if receipt.paid is None:
            return f"Hired {subject}."
        if receipt.model_name == receipt.profile_name:
            return f"Hired {subject} for {receipt.paid}¢."
        return f"Hired {subject}, {receipt.paid}¢."


def change(gang, user, data):
    """Validate and commit one hire, or confirm its original committed result."""
    from n26.core.access import gang_collections
    from n26.core.hire import build_hire_entry, collection_offers

    result = HireResult(HireSubmissionForm(data))
    if not result.form.is_valid():
        return result
    key = result.form.cleaned_data["request_key"]
    payload = command_payload(
        data, result.form.cleaned_data["name"], result.form.cleaned_data["selection"]
    )
    try:
        with operation(gang, actor=user) as op:
            gang.refresh_from_db()
            gang.forget_open_activities()
            if not user.is_authenticated or gang.owner_id != user.pk or gang.archived:
                raise Refusal("You can no longer hire models for this gang.")
            previous = HireReceipt.objects.filter(gang=gang, request_key=key).first()
            if previous is not None:
                if previous.actor_id != user.pk or previous.payload != payload:
                    result.conflict = True
                    raise Refusal(
                        "A different hire was already saved from this form. Reload the page."
                    )
                result.receipt = previous
            else:
                shown = sees_staged(user)

                def offers():
                    return collection_offers(
                        [access.collection for access in gang_collections(gang)],
                        include_staged=shown,
                    )

                profile, offered = resolve_offer(
                    data.get("profile", ""), offers, include_staged=shown
                )
                if profile is None:
                    result.form.add_error(
                        None, "This profile is no longer available. Choose another."
                    )
                    return result
                if "selection" in data:
                    taken = resolve_sets(profile, result.form.cleaned_data["selection"])
                else:
                    taken = chosen_sets(
                        resolve_picks(
                            data,
                            profile,
                            build_hire_entry(profile, with_cards=False),
                            key=data.get("profile"),
                        )
                    )
                quoted = quote_sets(profile, taken, offered)
                paid = price_typed(data, "paid", quoted, profile.name)
                rate_at_paid = payload["rateAtPaid"]
                try:
                    miniature = op.hire(
                        profile,
                        result.form.cleaned_data["name"] or profile.name,
                        option=taken,
                        paid=paid,
                        list_price=paid if rate_at_paid else quoted,
                        discount=0 if rate_at_paid else quoted - paid,
                        bought_from=offered,
                    )
                except ValueError:
                    raise UnavailableHire("No such option") from None
                result.receipt = op.record_hire_receipt(
                    key, payload, miniature, profile.name
                )
                result.miniature = miniature
                result.applied = True
    except (Refusal, BadPrice) as error:
        result.receipt = None
        result.miniature = None
        result.applied = False
        result.refused = error.public_message
        result.form.add_error(None, error.public_message)
    return result
