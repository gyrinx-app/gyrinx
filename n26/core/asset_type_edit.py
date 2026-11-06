"""Shared validation and revision checks for a campaign's own asset types."""

from dataclasses import dataclass

from django import forms
from django.core import signing

from n26.core.campaigns import campaign_operation, ownership_fixed_because
from n26.core.forms import EditAssetTypeForm
from n26.core.operations import Refusal
from n26.library.models import AssetType

SALT = "n26.edit-asset-type"
FIELDS = ("label_singular", "label_plural", "display_group", "ownership")


class TypeEditForm(EditAssetTypeForm):
    snapshot = forms.CharField(widget=forms.HiddenInput)


def values(asset_type):
    return {name: getattr(asset_type, name) for name in FIELDS}


def initial_form(campaign, asset_type, user):
    original = values(asset_type)
    locked = bool(ownership_fixed_because(campaign, asset_type))
    snapshot = signing.dumps(
        {
            "subject": str(asset_type.pk),
            "actor": user.pk,
            "modified": asset_type.modified.isoformat(),
            "values": original,
            "locked": locked,
        },
        salt=SALT,
    )
    return TypeEditForm(
        initial={**original, "snapshot": snapshot}, ownership_locked=locked
    )


@dataclass
class TypeEdit:
    form: TypeEditForm
    saved: bool = False
    applied: bool = False
    conflict: bool = False
    current: dict | None = None
    message: str = ""


def change(campaign, asset_type, user, data):
    form = TypeEditForm(
        data,
        initial=values(asset_type),
        ownership_locked=bool(ownership_fixed_because(campaign, asset_type)),
    )
    result = TypeEdit(form)
    try:
        snapshot = signing.loads(data.get("snapshot", ""), salt=SALT)
    except signing.BadSignature:
        form.is_valid()
        form.add_error(
            "snapshot",
            "This form could not be verified. Reload the page before saving.",
        )
        return result
    # Use the signed starting value so a newly locked ownership field cannot
    # silently discard an earlier selection.
    form = TypeEditForm(
        data, initial=snapshot["values"], ownership_locked=snapshot["locked"]
    )
    result.form = form
    if not form.is_valid():
        return result
    desired = {name: form.cleaned_data[name] for name in FIELDS}
    try:
        with campaign_operation(campaign, actor=user) as op:
            if campaign.archived or campaign.owner_id != user.pk:
                raise Refusal(
                    "You cannot edit this asset type. Only the campaign’s arbitrator can."
                )
            current = AssetType.objects.filter(
                pk=asset_type.pk, campaign_type_id=campaign.additions_id
            ).first()
            if current is None:
                raise Refusal("You can only edit this campaign’s own asset types here.")
            if snapshot["subject"] != str(current.pk) or snapshot["actor"] != user.pk:
                raise Refusal(
                    "This form belongs to another asset type or account. Reload the page."
                )
            current_values = values(current)
            fixed = ownership_fixed_because(campaign, current)
            if current_values != desired and (
                current.modified.isoformat() != snapshot["modified"]
                or current_values != snapshot["values"]
                or bool(fixed) != snapshot["locked"]
            ):
                result.conflict = True
                result.current = {
                    **current_values,
                    "ownershipLabel": current.get_ownership_display(),
                    "fixedReason": fixed,
                }
                raise Refusal(
                    "This asset type changed while you were editing. Review its current details before saving."
                )
            edited = op.edit_asset_type(current, **desired)
        result.saved = True
        result.applied = edited is not None
        result.message = (
            "Nothing changed."
            if snapshot["values"] == desired
            else f"Saved the asset type {desired['label_singular']}."
        )
    except Refusal as error:
        form.add_error(None, error.public_message)
    return result
