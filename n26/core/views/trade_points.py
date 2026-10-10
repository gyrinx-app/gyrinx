"""Owner-only lifecycle controls for a model's hire-time Trade Points."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse

from n26.core.operations import Refusal, operation
from n26.core.views.permissions import _own_miniature_or_404, may_see_founding


@login_required
def fighter_hire_time_action(request, pk):
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import Activity

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.membership.gang
    if not may_see_founding(gang, request.user):
        raise Http404
    at = reverse("n26-edit-fighter", args=[miniature.pk]) + "#actions"
    if request.method != "POST":
        return redirect(at)
    act = request.POST.get("act")
    changed = None
    try:
        with operation(gang, actor=request.user) as op:
            if act in ("start", "reopen"):
                if act == "reopen":
                    previous = gang.hire_time_activities().get(miniature.pk)
                    if previous is None or str(previous.pk) != request.POST.get(
                        "activity"
                    ):
                        raise Refusal(
                            "This action has changed. Reload the page before reopening it."
                        )
                changed = op.start_hire_time_tp(miniature, reopen=act == "reopen")
            elif act == "finish":
                active = gang.open_activity(Activity.Kind.HIRE_TIME, miniature)
                if active is not None:
                    if str(active.pk) != request.POST.get("activity"):
                        raise Refusal(
                            "This action has changed. Reload the page before completing it."
                        )
                    changed = op.close_activity(active)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(at)
    if changed is not None:
        record(
            request,
            N26Noun.MODEL,
            EventVerb.UPDATE,
            miniature,
            action=Activity.Kind.HIRE_TIME,
            act=act,
        )
        messages.success(
            request,
            "Hire-time Trade Points action completed."
            if act == "finish"
            else "Hire-time Trade Points action opened.",
        )
    return redirect(at)


def hire_time_context(gang, miniature, computed):
    """Prepare the Edit page's personal controls without reading another card."""
    from n26.core.activities import ActivityCard
    from n26.core.founding import budget_for, hire_time_states
    from n26.core.models import Activity

    state = hire_time_states(gang, [miniature], {str(miniature.pk): computed}).get(
        str(miniature.pk)
    )
    at = reverse("n26-fighter-hire-time-action", args=[miniature.pk])
    card = None
    if state is not None and state.act == "finish":
        budget = budget_for(gang, miniature, computed)
        card = ActivityCard(
            title=Activity.Kind.HIRE_TIME.label,
            action=at,
            about="Spend these Trade Points at the Trading Post.",
            help="Complete when you have finished equipping. Unspent Trade Points become unavailable.",
            facts=budget.facts,
            marked=True,
            activity_id=state.activity_id,
        )
    return {
        "hire_time_state": state,
        "hire_time_card": card,
        "hire_time_action_url": at,
    }
