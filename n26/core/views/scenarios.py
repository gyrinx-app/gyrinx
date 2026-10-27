"""The scenario generator outside a campaign, from the N26 menu, for
campaign and skirmish play alike. The campaign-specific generator is ``n26.core.views.campaigns.scenario_generator``; both draw
the same tables and results.

Any signed-in reader may generate, share and print a scenario, because
standalone generation saves nothing. Connecting a scenario to an existing
battle is restricted to arbitrators.
Creating a battle is offered to arbitrators and accepted players. Both
actions ask for the campaign in a dialog on the generator page.

The page's whole state is in the query string: each table's result under
its key, each pick that is not a roll under ``<key>_pick``, and the open
dialog, if any, under ``dialog``.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

SAVE = "save"
RECORD = "record"
DIALOGS = (SAVE, RECORD)


def _generator_url(query):
    """The generator's address for a query, with the scenario in view."""
    here = reverse("n26-generate-scenario")
    return f"{here}?{urlencode(query)}#scenario" if query else here


def _picks(request):
    """The non-default picks the address carries, so actions keep them."""
    from n26.core.forms import ScenarioGeneratorForm

    form = ScenarioGeneratorForm(request.GET)
    return form.chosen_picks() if form.is_valid() else {}


def _render_generator(request, *, dialog=None, dialog_form=None, data=None):
    """Draw the generator for the scenario ``data`` names, with an action
    dialog open when ``dialog`` is set. A dialog form posted with an error
    is passed in bound, so the reader's entries are kept."""
    from n26.core.campaign_permissions import recording_campaigns
    from n26.core.forms import (
        ConnectScenarioToBattleForm,
        ScenarioCampaignForm,
        ScenarioGeneratorForm,
    )
    from n26.core.scenarios import parse, rolls_of

    data = request.GET if data is None else data
    form = ScenarioGeneratorForm(request.GET)
    valid = form.is_valid()
    scenario, wrong = parse(data)
    if wrong:
        scenario = []
    rolls = rolls_of(scenario)
    picks = form.chosen_picks() if valid else {}
    state = {**picks, **rolls}
    connection = {
        key: request.GET[key] for key in ("campaign", "battle") if request.GET.get(key)
    }
    campaigns = recording_campaigns(request.user)
    may_record = bool(scenario) and campaigns.exists()
    connecting_campaigns = campaigns.filter(owner=request.user)
    may_connect = bool(scenario) and connecting_campaigns.exists()

    # A dialog posted with an error reopens whatever it was refused for, so
    # the reader sees why; one asked for in the address opens only when
    # there is a scenario and a campaign to use it in.
    if dialog_form is None and (
        dialog not in DIALOGS or not (may_connect if dialog == SAVE else may_record)
    ):
        dialog = None
    if dialog and dialog_form is None:
        form_class = (
            ConnectScenarioToBattleForm if dialog == SAVE else ScenarioCampaignForm
        )
        dialog_form = form_class(
            campaigns=connecting_campaigns if dialog == SAVE else campaigns,
            initial={**rolls, **connection},
        )

    picks_query = f"?{urlencode(picks)}" if picks else ""
    action = (
        reverse(
            "n26-generate-scenario-save"
            if dialog == SAVE
            else "n26-generate-scenario-record"
        )
        + picks_query
    )
    dialog_props = None
    if dialog:
        from django.middleware.csrf import get_token

        battles = list(dialog_form.fields["battle"].queryset) if dialog == SAVE else []
        if dialog == SAVE and not dialog_form.is_bound:
            selected = next(
                (b for b in battles if str(b.pk) == connection.get("battle")), None
            )
            if selected:
                dialog_form.initial["revision"] = selected.revision
        dialog_props = {
            "mode": dialog,
            "action": action,
            "cancelUrl": _generator_url(state),
            "selectionUrl": _generator_url({**state, "dialog": dialog}),
            "csrfToken": get_token(request),
            "rolls": rolls,
            "campaigns": [
                {"value": str(c.pk), "label": c.name}
                for c in dialog_form.fields["campaign"].queryset
            ],
            "campaign": str(dialog_form["campaign"].value() or ""),
            "battles": [
                {
                    "value": str(b.pk),
                    "label": f"{b.title} — {b.date.isoformat()}",
                    "revision": b.revision,
                    "hasScenario": bool(b.scenario_rolls),
                }
                for b in battles
            ],
            "battle": str(dialog_form["battle"].value() or "")
            if dialog == SAVE
            else "",
            "revision": dialog_form["revision"].value() if dialog == SAVE else None,
            "errors": {key: list(values) for key, values in dialog_form.errors.items()},
        }

    return render(
        request,
        "n26/generate_scenario.html",
        {
            "form": form,
            "scenario": scenario,
            "wrong": wrong,
            "share_url": _generator_url(state).removesuffix("#scenario"),
            "print_url": f"{reverse('n26-scenario-print')}?{urlencode(rolls)}",
            "save_url": _generator_url({**state, **connection, "dialog": SAVE}),
            "record_url": _generator_url({**state, "dialog": RECORD}),
            "may_record": may_record,
            "may_connect": may_connect,
            "scenario_dialog": dialog_props,
            "dialog": dialog,
            "dialog_form": dialog_form,
            "dialog_action": action,
            "dialog_cancel_url": _generator_url(state),
        },
    )


@login_required
def generate_scenario(request):
    """For each scenario table, roll a D6, leave it out, or use a named
    entry, then see the scenario.

    Generate scenario (``?generate``) rolls once and redirects to an
    address holding the result and the picks, so a reload or a shared link
    shows the same scenario, and generating again keeps the picks and
    rolls afresh. ``?dialog=save`` or ``?dialog=record`` opens the dialog
    that asks which campaign the scenario is for.
    """
    from n26.core.forms import ScenarioGeneratorForm

    form = ScenarioGeneratorForm(request.GET)
    if "generate" in request.GET and form.is_valid():
        rolls = form.generate()
        if request.GET.get("format") == "json":
            return JsonResponse({"rolls": rolls})
        connection = {
            key: request.GET[key]
            for key in ("campaign", "battle")
            if request.GET.get(key)
        }
        return redirect(_generator_url({**form.chosen_picks(), **rolls, **connection}))
    if "generate" in request.GET and request.GET.get("format") == "json":
        return JsonResponse(
            {
                "errors": [
                    str(error) for errors in form.errors.values() for error in errors
                ]
            },
            status=400,
        )
    return _render_generator(request, dialog=request.GET.get("dialog"))


@login_required
def save_scenario_to_campaign(request):
    """Connect generated components to an existing battle.

    POST only, from the connection dialog or saved-battle island. The latter
    sends table picks to generate and attach in one request. A dialog error redraws the generator with the dialog open and the entries kept.
    """
    from n26.core.campaign_permissions import recording_campaigns
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import ConnectScenarioToBattleForm, ScenarioGeneratorForm
    from n26.core.operations import Refusal

    if request.method != "POST":
        raise Http404("Nothing to save")
    data = request.POST
    if request.POST.get("generate") == "1":
        generator = ScenarioGeneratorForm(request.POST)
        if not generator.is_valid():
            return JsonResponse(
                {
                    "errors": [
                        str(error)
                        for errors in generator.errors.values()
                        for error in errors
                    ]
                },
                status=400,
            )
        data = request.POST.copy()
        from n26.library.scenario_tables import TABLES

        for table in TABLES:
            data.pop(table.key, None)
        data.update(generator.generate())
    form = ConnectScenarioToBattleForm(
        data,
        campaigns=recording_campaigns(request.user).filter(owner=request.user),
    )
    if form.is_valid():
        campaign = form.cleaned_data["campaign"]
        rolls = form.cleaned_data["scenario_rolls"]
        try:
            with campaign_operation(campaign, actor=request.user) as act:
                attached = act.connect_scenario(
                    form.cleaned_data["battle"],
                    rolls,
                    revision=form.cleaned_data["revision"],
                )
        except Refusal as refused:
            form.add_error(None, str(refused))
        else:
            battle_url = reverse(
                "n26-battle", args=[campaign.pk, form.cleaned_data["battle"].pk]
            )
            if request.POST.get("format") == "json":
                return JsonResponse(
                    {
                        "url": battle_url,
                        "revision": attached.revision,
                        "rolls": attached.scenario_rolls,
                    }
                )
            messages.success(request, "Scenario connected to the battle.")
            return redirect(battle_url)
    if request.POST.get("format") == "json":
        return JsonResponse(
            {
                "errors": [
                    str(error) for errors in form.errors.values() for error in errors
                ]
            },
            status=400,
        )
    return _render_generator(request, dialog=SAVE, dialog_form=form, data=request.POST)


@login_required
def record_scenario_battle(request):
    """Take the scenario to Record a battle in a campaign the reader
    chooses. POST only, from the generator's Record a battle dialog; the
    battle form carries the scenario on from there."""
    from n26.core.campaign_permissions import recording_campaigns
    from n26.core.forms import ScenarioCampaignForm

    if request.method != "POST":
        raise Http404("Nothing to record")
    form = ScenarioCampaignForm(
        request.POST, campaigns=recording_campaigns(request.user)
    )
    if form.is_valid():
        campaign = form.cleaned_data["campaign"]
        add_battle = reverse("n26-campaign-add-battle", args=[campaign.pk])
        return redirect(
            f"{add_battle}?{urlencode(form.cleaned_data['scenario_rolls'])}"
        )
    return _render_generator(
        request, dialog=RECORD, dialog_form=form, data=request.POST
    )


def _print(request, back_url):
    """The scenario the address names, on paper, with a way back to the
    generator it came from. A missing or wrong scenario is not found."""
    from n26.core.scenarios import parse

    scenario, wrong = parse(request.GET)
    if wrong or not scenario:
        raise Http404("No scenario to print")
    return render(
        request,
        "n26/print_scenario.html",
        {"scenario": scenario, "back_url": back_url(scenario)},
    )


@login_required
def print_scenario(request):
    """The scenario on paper: one card per component, in the order the
    generator shows them, with the deployment map. A bare document, like
    a gang's print, so what a phone opens is what turns into a PDF."""
    from n26.core.scenarios import rolls_of

    return _print(
        request,
        lambda scenario: _generator_url({**_picks(request), **rolls_of(scenario)}),
    )


@login_required
def campaign_print_scenario(request, pk):
    """The same print from a campaign's own generator, for whoever can read
    the campaign. Back to scenario returns to that campaign's generator."""
    from n26.core.scenarios import rolls_of
    from n26.core.views.permissions import _any_campaign_or_404

    found = _any_campaign_or_404(request, pk, with_owner_badge=False)
    generator = reverse("n26-scenario-generator", args=[found.pk])

    def back_url(scenario):
        query = {**_picks(request), **rolls_of(scenario)}
        return f"{generator}?{urlencode(query)}#scenario"

    return _print(request, back_url)
