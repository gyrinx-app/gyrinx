"""Shared preparation and conflict handling for editing one campaign holding."""

from dataclasses import dataclass

from django import forms
from django.core import signing

from n26.core.campaigns import campaign_operation
from n26.core.forms import EditAssetForm
from n26.core.models import CampaignAsset
from n26.core.operations import Refusal

SALT = "n26.edit-holding"


class HoldingEditForm(EditAssetForm):
    snapshot = forms.CharField(widget=forms.HiddenInput)


def values(holding):
    return {
        "name": holding.name,
        "income": (
            holding.income_override.contributes_to_counter.amount
            if holding.income_override_id
            else None
        ),
    }


def initial_form(holding, user):
    original = values(holding)
    snapshot = signing.dumps(
        {
            "holding": str(holding.pk),
            "actor": user.pk,
            "modified": holding.modified.isoformat(),
            "values": original,
        },
        salt=SALT,
    )
    return HoldingEditForm(initial={**original, "snapshot": snapshot})


@dataclass
class HoldingEdit:
    form: HoldingEditForm
    saved: bool = False
    applied: bool = False
    conflict: bool = False
    current: dict | None = None
    message: str = ""


def change(campaign, holding, user, data):
    result = HoldingEdit(HoldingEditForm(data))
    form = result.form
    if not form.is_valid():
        return result
    try:
        snapshot = signing.loads(form.cleaned_data["snapshot"], salt=SALT)
    except signing.BadSignature:
        form.add_error(
            "snapshot",
            "This form could not be verified. Reload the page before saving.",
        )
        return result
    desired = {name: form.cleaned_data[name] for name in ("name", "income")}
    try:
        with campaign_operation(campaign, actor=user) as op:
            if campaign.archived or campaign.owner_id != user.pk:
                raise Refusal(
                    "You cannot edit this asset. Only the campaign’s arbitrator can."
                )
            if snapshot["holding"] != str(holding.pk) or snapshot["actor"] != user.pk:
                raise Refusal(
                    "This form belongs to another asset or account. Reload the page."
                )
            current = (
                CampaignAsset.objects.select_related(
                    "income_override__contributes_to_counter"
                )
                .filter(pk=holding.pk, campaign=campaign)
                .first()
            )
            if current is None:
                raise Refusal("This asset was removed from the campaign.")
            current_values = values(current)
            if current_values != desired and (
                current.modified.isoformat() != snapshot["modified"]
                or current_values != snapshot["values"]
            ):
                result.conflict = True
                result.current = current_values
                raise Refusal(
                    "This asset changed while you were editing. Review its current details before saving."
                )
            edited = op.edit_asset(current, **desired)
        result.saved = True
        result.applied = edited is not None
        result.message = (
            "Nothing changed." if snapshot["values"] == desired else "Asset saved."
        )
    except Refusal as error:
        form.add_error(None, error.public_message)
    return result
