from allauth.account.forms import ResetPasswordForm
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.utils.translation import gettext as _

from gyrinx.pages.forms import InviteUserForm
from gyrinx.pages.models import WaitingListEntry


@admin.action(description="Invite user")
def invite_user(self, request, queryset):
    selected = queryset.values_list("pk", flat=True)

    if request.POST.get("post"):
        User = get_user_model()
        try:
            for item in queryset:
                item = WaitingListEntry.objects.get(pk=item.pk)
                username = item.username_cleaned()
                if not User.objects.filter(username=username).exists():
                    User.objects.create_user(
                        username=username,
                        email=item.email,
                        # This causes Django to generate a password
                        password=None,
                    )

                # A bit of a hack to send the reset password email
                reset_form = ResetPasswordForm(data={"email": item.email})
                if reset_form.is_valid():
                    reset_form.save(request=request)
                else:
                    raise Exception(
                        f"Error sending reset password email: {reset_form.errors}"
                    )

                item.invited = True
                item.save()

        except Exception as e:
            self.message_user(
                request,
                _("An error occurred while inviting: %s") % str(e),
                messages.ERROR,
            )
            return None

        self.message_user(
            request,
            _("The selected entries have been invited."),
            messages.SUCCESS,
        )
        return None

    form = InviteUserForm(initial={"_selected_action": selected})
    title = _("Invite users from waiting list?")
    subtitle = _("")

    context = {
        **self.admin_site.each_context(request),
        "title": title,
        "subtitle": subtitle,
        "queryset": queryset,
        "form": form,
        "action_name": "invite_user",
    }
    request.current_app = self.admin_site.name
    return render(
        request,
        "pages/invite_user.html",
        context,
    )
