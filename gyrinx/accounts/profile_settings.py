"""Owner-only account presentation, saved through one native form contract."""

from django import forms
from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from gyrinx.accounts.models import UserProfile
from gyrinx.accounts.validators import (
    instagram_handle,
    social_link_href,
    validate_profile_location,
)
from gyrinx.colours import GANG_COLOURS
from gyrinx.images import MAX_PX, SQUARE, to_shape

SALT = "account-profile-settings"


def state(profile):
    return [
        profile.picture.name,
        profile.social_links,
        profile.colour,
        profile.location,
        profile.instagram_handle,
        profile.discord_handle,
        profile.discord_user_id,
    ]


class ProfileSettingsForm(forms.Form):
    snapshot = forms.CharField()
    location = forms.CharField(
        required=False, max_length=20, validators=[validate_profile_location]
    )
    instagram = forms.CharField(required=False, max_length=31)
    discord = forms.RegexField(
        r"^@?[a-z0-9_.]{2,32}$",
        required=False,
        max_length=33,
        error_messages={
            "invalid": "Enter your Discord handle using lowercase letters, numbers, periods or underscores."
        },
    )
    discord_user_id = forms.RegexField(
        r"^[1-9][0-9]{16,19}$",
        required=False,
        max_length=20,
        error_messages={
            "invalid": "Enter the numeric user ID copied from your Discord profile."
        },
    )
    remove_extra_links = forms.BooleanField(required=False)

    colour = forms.ChoiceField(
        required=False,
        choices=[("", "Default"), *((c, c.title()) for c in GANG_COLOURS)],
    )
    picture = forms.ImageField(required=False)
    remove_picture = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for index in range(3):
            self.fields[f"link_{index}"] = forms.CharField(
                required=False, max_length=2048, strip=False
            )

    def clean_discord(self):
        handle = self.cleaned_data["discord"].removeprefix("@")
        if ".." in handle:
            raise ValidationError(
                "Your Discord handle cannot contain two periods together."
            )
        return handle

    def clean_discord_user_id(self):
        value = self.cleaned_data["discord_user_id"]
        if value and int(value) >= 2**64:
            raise ValidationError(
                "Enter the numeric user ID copied from your Discord profile."
            )
        return value

    def clean_instagram(self):
        return instagram_handle(self.cleaned_data["instagram"])

    def clean_picture(self):
        picture = self.cleaned_data["picture"]
        if picture:
            if picture.size > 10 * 1024 * 1024:
                raise ValidationError("Select a picture up to 10 MB.")
            return to_shape(picture, SQUARE)
        return picture

    def clean(self):
        cleaned = super().clean()
        if any(
            key.startswith("link_") and key not in self.fields and self.data.get(key)
            for key in self.data
        ):
            self.add_error(None, "Add up to three links or email addresses.")
        for index in range(3):
            name = f"link_{index}"
            value = cleaned.get(name, "")
            if value:
                try:
                    social_link_href(value)
                except ValidationError:
                    self.add_error(
                        name,
                        "Enter a link starting with http:// or https://, or an email address.",
                    )
        if cleaned.get("picture") and cleaned.get("remove_picture"):
            self.add_error("picture", "Choose a new picture or remove the current one.")
        return cleaned


def settings_props(request, person, profile, form=None, *, conflict=False):
    if request.user.pk != person.pk:
        return None
    from django.urls import reverse

    values = (
        form.data
        if form is not None
        else {
            "colour": profile.colour,
            "location": profile.location,
            "instagram": profile.instagram_handle,
            "discord": profile.discord_handle,
            "discord_user_id": profile.discord_user_id,
            **{f"link_{i}": v for i, v in enumerate(profile.social_links)},
        }
    )
    return {
        "actionUrl": reverse("profile-settings", args=[person.username])
        + "?"
        + request.GET.urlencode(),
        "csrfToken": get_token(request),
        "snapshot": form.data.get("snapshot", "")
        if form is not None
        else signing.dumps([person.pk, state(profile)], salt=SALT),
        "colour": values.get("colour", ""),
        "location": values.get("location", ""),
        "instagram": values.get("instagram", ""),
        "discord": values.get("discord", ""),
        "discordUserId": values.get("discord_user_id", ""),
        "extraLinks": profile.social_links[3:],
        "removeExtraLinks": bool(values.get("remove_extra_links", False)),
        "colours": list(GANG_COLOURS),
        "links": [values.get(f"link_{i}", "") for i in range(3)],
        "pictureUrl": profile.picture.url if profile.picture else "",
        "cropMax": MAX_PX,
        "errors": {name: list(errors) for name, errors in form.errors.items()}
        if form is not None
        else {},
        "open": form is not None,
        "removePicture": bool(values.get("remove_picture", False)),
        "conflict": conflict,
        "reloadUrl": reverse("user-profile", args=[person.username])
        + "?"
        + request.GET.urlencode(),
    }


@require_POST
def profile_settings(request, username):
    from gyrinx.accounts.public_profiles import (
        profile_href,
        profile_person,
        user_profile,
    )

    person = profile_person(username)
    if not request.user.is_authenticated or request.user.pk != person.pk:
        return HttpResponseForbidden("Only the account owner can edit this profile.")
    form = ProfileSettingsForm(request.POST, request.FILES)
    conflict = False
    status = 400
    if form.is_valid():
        with transaction.atomic():
            UserProfile.objects.get_or_create(user=person)
            profile = UserProfile.objects.select_for_update().get(user=person)
            try:
                starting = signing.loads(form.cleaned_data["snapshot"], salt=SALT)
            except signing.BadSignature:
                starting = None
            desired_links = [
                form.cleaned_data[f"link_{i}"]
                for i in range(3)
                if form.cleaned_data[f"link_{i}"]
            ]
            if not form.cleaned_data["remove_extra_links"]:
                desired_links += profile.social_links[3:]
            unchanged = (
                profile.location == form.cleaned_data["location"]
                and profile.instagram_handle == form.cleaned_data["instagram"]
                and profile.discord_handle == form.cleaned_data["discord"]
                and profile.discord_user_id == form.cleaned_data["discord_user_id"]
                and profile.social_links == desired_links
                and profile.colour == form.cleaned_data["colour"]
                and not form.cleaned_data["picture"]
                and (not form.cleaned_data["remove_picture"] or not profile.picture)
            )
            valid_snapshot = (
                isinstance(starting, list)
                and len(starting) == 2
                and starting[0] == person.pk
            )
            if not valid_snapshot or (starting[1] != state(profile) and not unchanged):
                form.add_error(
                    None,
                    "Your profile changed in another tab. Reload to edit the latest settings.",
                )
                conflict = True
                status = 409
            else:
                profile.social_links = desired_links
                profile.location = form.cleaned_data["location"]
                profile.instagram_handle = form.cleaned_data["instagram"]
                profile.discord_handle = form.cleaned_data["discord"]
                profile.discord_user_id = form.cleaned_data["discord_user_id"]
                profile.colour = form.cleaned_data["colour"]
                if form.cleaned_data["remove_picture"]:
                    profile.picture = ""
                elif form.cleaned_data["picture"]:
                    profile.picture = form.cleaned_data["picture"]
                if not unchanged:
                    profile.save(
                        update_fields=[
                            "picture",
                            "social_links",
                            "colour",
                            "location",
                            "instagram_handle",
                            "discord_handle",
                            "discord_user_id",
                            "modified",
                        ]
                    )
                messages.success(request, "Profile settings saved.")
                href = profile_href(person)
                return redirect(
                    href + ("?" + request.GET.urlencode() if request.GET else "")
                )
    if "snapshot" in form.errors:
        form.add_error(None, "Reload your profile before saving.")
        conflict = True
        status = 409
    return user_profile(
        request,
        person.username,
        settings_form=form,
        settings_conflict=conflict,
        status=status,
    )
