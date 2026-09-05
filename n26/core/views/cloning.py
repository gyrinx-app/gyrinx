"""Copy a gang or one of its models from a named form."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from n26.core.views.permissions import _any_gang_or_404, _own_miniature_or_404


@login_required
def clone_gang(request, pk):
    """Copy a shared gang into a new gang owned by the reader."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.cloning import clone_name
    from n26.core.forms import CloneGangForm
    from n26.core.operations import Refusal
    from n26.core.operations import clone_gang as perform_clone

    source = _any_gang_or_404(request, pk)
    if request.method == "POST":
        form = CloneGangForm(request.POST)
        if form.is_valid():
            try:
                cloned = perform_clone(
                    source,
                    name=form.cleaned_data["name"],
                    owner=request.user,
                    actor=request.user,
                )
            except Refusal as refusal:
                form.add_error(None, str(refusal))
            else:
                record(
                    request,
                    N26Noun.GANG,
                    EventVerb.CLONE,
                    cloned,
                    source_gang_id=str(source.pk),
                    source_gang_name=source.name,
                )
                messages.success(request, f"Cloned {source.name} as {cloned.name}.")
                return redirect("n26-gang", pk=cloned.pk)
    else:
        form = CloneGangForm(initial={"name": clone_name(source.name)})

    return render(
        request,
        "n26/clone_gang.html",
        {"source": source, "form": form},
    )


@login_required
def clone_fighter(request, pk):
    """Copy one of the reader's models inside its gang."""
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.cloning import clone_name
    from n26.core.forms import CloneFighterForm
    from n26.core.operations import Refusal, operation

    source = _own_miniature_or_404(request, pk)
    gang = source.membership.gang
    if request.method == "POST":
        form = CloneFighterForm(request.POST)
        if form.is_valid():
            try:
                with operation(gang, actor=request.user) as op:
                    cloned = op.clone_miniature(
                        source,
                        name=form.cleaned_data["name"],
                    )
            except Refusal as refusal:
                form.add_error(None, str(refusal))
            else:
                record(
                    request,
                    N26Noun.MODEL,
                    EventVerb.CLONE,
                    cloned,
                    source_model_id=str(source.pk),
                    source_model_name=source.name,
                    gang_id=str(gang.pk),
                )
                messages.success(request, f"Cloned {source.name} as {cloned.name}.")
                return redirect("n26-edit-fighter", pk=cloned.pk)
    else:
        form = CloneFighterForm(initial={"name": clone_name(source.name)})

    return render(
        request,
        "n26/clone_fighter.html",
        {"source": source, "gang": gang, "form": form},
    )
