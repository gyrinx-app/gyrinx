from django import forms
from django.conf import settings
from django.contrib.flatpages import views
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.shortcuts import get_current_site
from django.http import Http404, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx.core import url
from gyrinx.core.forms import BsCheckboxSelectMultiple
from gyrinx.pages.models import FlatPageVisibility, WaitingListEntry, WaitingListSkill


def flatpage(request, url):
    # This is copied from django.contrib.flatpages.views.flatpage

    if not url.startswith("/"):
        url = "/" + url
    site_id = get_current_site(request).id
    try:
        f = get_object_or_404(FlatPage, url=url, sites=site_id)
    except Http404:
        if not url.endswith("/") and settings.APPEND_SLASH:
            url += "/"
            f = get_object_or_404(FlatPage, url=url, sites=site_id)
            return HttpResponsePermanentRedirect("%s/" % request.path)
        else:
            raise

    # This is the new part
    # Check if the page is visible to the user
    # If the user is not authenticated, raise a 404
    visibility = FlatPageVisibility.objects.filter(page=f)
    if visibility.exists():
        if not request.user.is_authenticated:
            raise Http404
        groups = request.user.groups.all()
        if not visibility.filter(groups__in=groups).exists():
            raise Http404

    return views.render_flatpage(request, f)


class JoinWaitingListForm(forms.ModelForm):
    class Meta:
        model = WaitingListEntry
        fields = [
            "email",
            "desired_username",
            "yaktribe_username",
            "skills",
            "notes",
        ]
        read_only_fields = ["referred_by_code"]

    email = forms.EmailField(
        label="What's your email address?",
        help_text="If you support Gyrinx on Patreon, please use the email address associated with your Patreon account.",
        required=True,
        widget=forms.EmailInput(
            attrs={"placeholder": "you@example.com", "class": "form-control"}
        ),
    )
    desired_username = forms.CharField(
        label="What would you ideally like your Gyrinx username to be?",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "lord_helmawr", "class": "form-control"}
        ),
    )
    yaktribe_username = forms.CharField(
        label="YakTribe user? Tell us your username…",
        label_suffix="",
        help_text="We're working on ways to import your YakTribe data, so this will help us match you up.",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "lord_helmawr", "class": "form-control"}
        ),
    )
    skills = forms.ModelMultipleChoiceField(
        queryset=WaitingListSkill.objects.all(),
        label="Interested in helping out? Tell us what you'd bring to the table…",
        label_suffix="",
        required=False,
        widget=BsCheckboxSelectMultiple(
            attrs={"class": "form-check-input"},
        ),
    )
    notes = forms.CharField(
        label="Anything else you'd like to tell us?",
        required=False,
        widget=forms.Textarea(attrs={"placeholder": "", "class": "form-control"}),
    )
    referred_by_code = forms.UUIDField(
        widget=forms.HiddenInput(),
        required=False,
    )


def join_the_waiting_list(request):
    wlid = request.COOKIES.get("wlid")
    entry = None
    if wlid:
        try:
            entry = WaitingListEntry.objects.filter(pk=wlid).first()
        except Exception:
            pass

        if entry:
            return HttpResponseRedirect(reverse("join_the_waiting_list_success"))

    if not settings.WAITING_LIST_ALLOW_SIGNUPS:
        return HttpResponseRedirect(reverse("core:index"))

    share_code = request.GET.get("c")
    if request.method == "POST":
        form = JoinWaitingListForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            # If I'm honest, I'm not sure why this is necessary.
            instance.referred_by_code = form.cleaned_data.get("referred_by_code")
            instance.save()
            response = HttpResponseRedirect(reverse("join_the_waiting_list_success"))
            response.set_cookie(
                "wlid",
                form.instance.pk,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="Strict",
                secure=not settings.DEBUG,
            )
            return response
    else:
        form = JoinWaitingListForm(initial={"referred_by_code": share_code})

    response = render(request, "pages/join_the_waiting_list.html", {"form": form})
    response.delete_cookie("wlid")
    return response


def join_the_waiting_list_success(request):
    wlid = request.COOKIES.get("wlid")
    entry = None
    if wlid:
        try:
            entry = WaitingListEntry.objects.filter(pk=wlid).first()
        except Exception:
            pass

    if not entry:
        response = HttpResponseRedirect(reverse("join_the_waiting_list"))
        response.delete_cookie("wlid")
        return response

    join_url = reverse("join_the_waiting_list")
    full_url = url.fullurl(request, join_url)
    share_url = full_url + f"?c={entry.share_code}"

    return render(
        request,
        "pages/join_the_waiting_list_success.html",
        {"entry": entry, "share_url": share_url},
    )
