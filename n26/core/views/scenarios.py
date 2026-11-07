"""Standalone scenario generation, sharing and printing.

Keep results, picks and open dialogs in the query string. Connecting a
scenario to a battle requires its campaign arbitrator; accepted players
may also create battles from a generated scenario.
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
    """Link to the generator with encoded state and the scenario anchor."""
    here = reverse("n26-generate-scenario")
    return f"{here}?{urlencode(query)}#scenario" if query else here


def side_job_changes(request, form, here, extra=None):
    """Handle side-job additions, removals and rerolls without regenerating the scenario."""
    from n26.core.scenarios import parse, rolls_of

    if "generate" in request.GET:
        return None
    form.is_valid()
    if any(key != "__all__" for key in form.errors):
        return None
    if "add_side_job" in request.GET:
        picks = form.with_side_job_added()
    elif "remove_side_job" in request.GET:
        try:
            place = int(request.GET["remove_side_job"])
        except ValueError:
            place = 0
        picks = form.with_side_job_removed(place)
    elif "reroll_set" in request.GET:
        return _rerolled(request, form, here, extra)
    else:
        return None
    found, wrong = parse(request.GET)
    rolls = {} if wrong else rolls_of(found)
    query = urlencode({**picks, **rolls, **(extra or {})})
    return redirect(f"{here}?{query}#scenario-components")


REROLL_REFUSED = (
    "That side job could not be rolled again. Reload the page and try again."
)


def rerolled_rolls(data):
    """Reroll the named side job on the selected set, or return None for invalid input."""
    from n26.core.scenarios import parse, reroll_side_job

    found, wrong = parse(data)
    if wrong:
        return None
    return reroll_side_job(found, data.get("reroll", ""), data.get("reroll_set", ""))


def _rerolled(request, form, here, extra):
    """Redirect with one side job rerolled and the remaining picks and rolls preserved."""
    from n26.core.scenarios import parse, rolls_of
    from n26.library.scenario_tables import SIDE_JOB_KEYS

    found, wrong = parse(request.GET)
    key = request.GET.get("reroll", "")
    set_key = request.GET["reroll_set"]
    rolls = rerolled_rolls(request.GET)
    if rolls is None:
        picks, rolls = form.chosen_picks(), ({} if wrong else rolls_of(found))
    else:
        side_jobs = sum(1 for result in found if result.table.side_job_set)
        picks = form.with_side_job_set(SIDE_JOB_KEYS.index(key) + 1, set_key, side_jobs)
    query = urlencode({**picks, **rolls, **(extra or {})})
    return redirect(f"{here}?{query}#scenario")


def reroll_dialog(request, here, rolls, extra=None):
    """Build reroll links and dialog props for a valid selected side job.

    Carry current picks and rolls into the request handled by side_job_changes.
    """
    from n26.core.forms import ScenarioGeneratorForm
    from n26.core.scenarios import parse
    from n26.library.scenario_tables import SIDE_JOB_KEYS, SIDE_JOB_SETS

    form = ScenarioGeneratorForm(request.GET)
    state = {
        **(form.chosen_picks() if form.is_valid() else {}),
        **rolls,
        **(extra or {}),
    }
    links = {
        key: f"{here}?{urlencode({**state, 'reroll': key})}#scenario"
        for key in rolls
        if key in SIDE_JOB_KEYS
    }
    key = request.GET.get("reroll", "")
    if key not in links:
        return None, links
    found, _ = parse(rolls)
    (result,) = [r for r in found if r.table.key == key]
    return {
        "title": f"Reroll {result.table.name.lower()}",
        "action": here,
        "cancelUrl": f"{here}?{urlencode(state)}#scenario",
        "fields": [
            [name, str(value)] for name, value in {**state, "reroll": key}.items()
        ],
        "sets": [{"value": s.key, "label": s.label} for s in SIDE_JOB_SETS],
        "set": result.table.side_job_set.key,
    }, links


def _picks(request):
    """Return valid non-default scenario picks from the query string."""
    from n26.core.forms import ScenarioGeneratorForm

    form = ScenarioGeneratorForm(request.GET)
    return form.chosen_picks() if form.is_valid() else {}


def _render_generator(request, *, dialog=None, dialog_form=None, data=None):
    """Render a scenario and an authorised action dialog.

    A supplied bound dialog form reopens with its submitted values and errors.
    """
    from n26.core.campaign_permissions import recording_campaigns
    from n26.core.forms import (
        ConnectScenarioToBattleForm,
        ScenarioCampaignForm,
        ScenarioGeneratorForm,
    )
    from n26.core.scenarios import parse, rolls_of

    data = request.GET if data is None else data
    from n26.core.views.scenario_props import scenario_picks_props

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

    # Reopen a bound form with its errors; validate URL-requested dialogs against permissions.
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

    reroll, reroll_links = (
        reroll_dialog(request, reverse("n26-generate-scenario"), rolls, connection)
        if not dialog
        else (None, {})
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
            "scenario_picks": scenario_picks_props(form),
            "scenario": scenario,
            "wrong": wrong,
            "rolls": rolls,
            "share_url": _generator_url(state).removesuffix("#scenario"),
            "print_url": f"{reverse('n26-scenario-print')}?{urlencode(rolls)}",
            "save_url": _generator_url({**state, **connection, "dialog": SAVE}),
            "record_url": _generator_url({**state, "dialog": RECORD}),
            "may_record": may_record,
            "may_connect": may_connect,
            "scenario_dialog": dialog_props,
            "scenario_reroll": reroll,
            "reroll_links": reroll_links,
            "dialog": dialog,
            "dialog_form": dialog_form,
            "dialog_action": action,
            "dialog_cancel_url": _generator_url(state),
        },
    )


@login_required
def generate_scenario(request):
    """Generate or reroll scenario components as JSON or shareable URL state.

    Preserve explicit picks across generation. Save and record dialogs select
    the campaign for the resulting scenario.
    """
    from n26.core.forms import ScenarioGeneratorForm

    form = ScenarioGeneratorForm(request.GET)
    connection = {
        key: request.GET[key] for key in ("campaign", "battle") if request.GET.get(key)
    }
    # The battle form requests a single side-job reroll as JSON.
    if "reroll_set" in request.GET and request.GET.get("format") == "json":
        rolls = rerolled_rolls(request.GET)
        if rolls is None:
            return JsonResponse({"errors": [REROLL_REFUSED]}, status=400)
        return JsonResponse({"rolls": rolls})
    changed = side_job_changes(
        request, form, reverse("n26-generate-scenario"), connection
    )
    if changed:
        return changed
    if "generate" in request.GET and form.is_valid():
        rolls = form.generate()
        if request.GET.get("format") == "json":
            return JsonResponse({"rolls": rolls})
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
    """Attach scenario components to an existing battle on POST.

    Support generation or one side-job reroll in the same request. Return JSON
    for battle islands or redisplay a refused generator dialog with its values.
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
        from n26.library.scenario_tables import SIDE_JOB_KEYS, TABLES

        for key in [table.key for table in TABLES] + list(SIDE_JOB_KEYS):
            data.pop(key, None)
        data.update(generator.generate())
    elif request.POST.get("reroll_set"):
        rolls = rerolled_rolls(request.POST)
        if rolls is None:
            return JsonResponse({"errors": [REROLL_REFUSED]}, status=400)
        data = request.POST.copy()
        from n26.library.scenario_tables import SIDE_JOB_KEYS, TABLES

        for key in [table.key for table in TABLES] + list(SIDE_JOB_KEYS):
            data.pop(key, None)
        data.update(rolls)
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
    """Redirect a valid scenario to the selected campaign's battle creation form."""
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
    """Render a valid scenario with a caller-supplied return URL; reject missing results."""
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
    """Print scenario components and deployment map with a return link to the generator."""
    from n26.core.scenarios import rolls_of

    return _print(
        request,
        lambda scenario: _generator_url({**_picks(request), **rolls_of(scenario)}),
    )


@login_required
def campaign_print_scenario(request, pk):
    """Print a campaign scenario for any reader allowed to view the campaign."""
    from n26.core.scenarios import rolls_of
    from n26.core.views.permissions import _any_campaign_or_404

    found = _any_campaign_or_404(request, pk, with_owner_badge=False)
    generator = reverse("n26-scenario-generator", args=[found.pk])

    def back_url(scenario):
        query = {**_picks(request), **rolls_of(scenario)}
        return f"{generator}?{urlencode(query)}#scenario"

    return _print(request, back_url)
