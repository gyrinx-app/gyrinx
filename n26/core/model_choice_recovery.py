"""Read-only recovery targets in a currently owned, active gang.

A removed model remains addressable only through explicit recovery navigation.
An actor's stored command can identify a model that no longer has a membership.
The normal model pages retain their live-membership requirement.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class RecoveryTarget:
    gang: object
    name: str


def target_for(model_key, actor, *, action):
    from n26.core.models import Miniature, ModelChoiceReceipt

    if not actor.is_authenticated:
        return None
    try:
        miniature = (
            Miniature.objects.select_related("membership__gang__owner")
            .filter(
                pk=model_key,
                membership__gang__owner=actor,
                membership__gang__archived=False,
                membership__archived=True,
            )
            .first()
        )
    except ValidationError:
        return None
    if miniature is not None:
        return RecoveryTarget(miniature.gang, miniature.name)
    receipt = (
        ModelChoiceReceipt.objects.select_related("gang__owner")
        .filter(
            actor=actor,
            gang__owner=actor,
            gang__archived=False,
            payload__model=str(model_key),
            payload__action=action,
        )
        .order_by("-created")
        .first()
    )
    if receipt is not None:
        return RecoveryTarget(
            receipt.gang, receipt.result.get("model_name", "Removed model")
        )
    return None
