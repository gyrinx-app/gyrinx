"""The scenario generator outside a campaign, from the N26 menu, for
campaign and skirmish play alike. The generator inside a campaign, from its
Battles box, is ``n26.core.views.campaigns.scenario_generator``; both draw
the same tables and results.

Any signed-in reader may generate, share and print a scenario, because
nothing is saved by doing so. Saving a scenario to a campaign, or
recording a battle with it, is offered for the campaigns the reader may
record in, chosen in a dialog on the generator page.

The page's whole state is in the query string: each table's result under
its key, each pick that is not a roll under ``<key>_pick``, and the open
dialog, if any, under ``dialog``.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
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
        SaveScenarioToCampaignForm,
        ScenarioCampaignForm,
        ScenarioGeneratorForm,
    )
    from n26.core.scenarios import parse, rolls_of

    data = request.GET if data is None else data
    form = ScenarioGeneratorForm(request.GET)
    form.is_valid()
    scenario, wrong = parse(data)
    if wrong:
        scenario = []
    rolls = rolls_of(scenario)
    picks = _picks(request)
    state = {**picks, **rolls}
    campaigns = recording_campaigns(request.user)
    may_record = bool(scenario) and campaigns.exists()

    # A dialog posted with an error reopens whatever it was refused for, so
    # the reader sees why; one asked for in the address opens only when
    # there is a scenario and a campaign to use it in.
    if dialog_form is None and (dialog not in DIALOGS or not may_record):
        dialog = None
    if dialog and dialog_form is None:
        form_class = (
            SaveScenarioToCampaignForm if dialog == SAVE else ScenarioCampaignForm
        )
        dialog_form = form_class(
            campaigns=campaigns,
            initial={**rolls, "campaign": request.GET.get("campaign")},
        )

    picks_query = f"?{urlencode(picks)}" if picks else ""
    return render(
        request,
        "n26/generate_scenario.html",
        {
            "form": form,
            "scenario": scenario,
            "wrong": wrong,
            "share_url": _generator_url(state).removesuffix("#scenario"),
            "print_url": f"{reverse('n26-scenario-print')}?{urlencode(rolls)}",
            "save_url": _generator_url({**state, "dialog": SAVE}),
            "record_url": _generator_url({**state, "dialog": RECORD}),
            "may_record": may_record,
            "dialog": dialog,
            "dialog_form": dialog_form,
            "dialog_action": (
                reverse(
                    "n26-generate-scenario-save"
                    if dialog == SAVE
                    else "n26-generate-scenario-record"
                )
                + picks_query
            ),
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
        return redirect(_generator_url({**form.chosen_picks(), **form.generate()}))
    return _render_generator(request, dialog=request.GET.get("dialog"))


@login_required
def save_scenario_to_campaign(request):
    """Save the scenario to the log of a campaign the reader chooses.

    POST only, from the generator's Save to campaign dialog. An error
    redraws the generator with the dialog open and the entries kept.
    """
    from n26.core.campaign_permissions import recording_campaigns
    from n26.core.campaigns import campaign_operation
    from n26.core.forms import SaveScenarioToCampaignForm
    from n26.core.operations import Refusal

    if request.method != "POST":
        raise Http404("Nothing to save")
    form = SaveScenarioToCampaignForm(
        request.POST, campaigns=recording_campaigns(request.user)
    )
    if form.is_valid():
        campaign = form.cleaned_data["campaign"]
        rolls = form.cleaned_data["scenario_rolls"]
        try:
            with campaign_operation(campaign, actor=request.user) as act:
                act.save_scenario(rolls, name=form.cleaned_data["name"])
        except Refusal as refused:
            form.add_error(None, str(refused))
        else:
            messages.success(
                request, f"Scenario saved to the {campaign.name} campaign log."
            )
            return redirect(_generator_url({**_picks(request), **rolls}))
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
