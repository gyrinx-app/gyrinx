from django.urls import path

from . import views

app_name = "designsystem"

urlpatterns = [
    path("", views.index, name="index"),
    path("theming/", views.theming, name="theming"),
    path("tokens/", views.token_reference, name="tokens"),
    # The lab is the harness; the sheet is the thing under test, and has to be a
    # URL of its own so it can be opened on a phone, framed as a preview, or
    # handed to a headless browser to print.
    path("print/", views.print_lab, name="print_lab"),
    path("print/sheet/", views.print_sheet, name="print_sheet"),
    # A view on its own, at real width. The component page's own chrome decides
    # the width at 390px, so it cannot answer whether a screen fits a phone.
    # The app's page shell, rendered. A base nothing inherits from is markup
    # nobody has compiled — and a view only ever seen on its own is one nobody has
    # seen next to a nav and a footer. Three pages so the shell can be walked
    # rather than glanced at: they link to each other through the nav.
    path("shell/", views.shell_home, name="shell_home"),
    path("shell/new-gang/", views.shell_new_gang, name="shell_new_gang"),
    path("shell/gang/", views.shell_gang, name="shell_gang"),
    path("shell/campaign/", views.shell_campaign, name="shell_campaign"),
    path("shell/hire/", views.shell_hire, name="shell_hire"),
    path("shell/shop/", views.shell_shop, name="shell_shop"),
    path("shell/print/", views.shell_print, name="shell_print"),
    path("view/<slug:slug>/", views.view_preview, name="view_preview"),
    # What the deferred component's demo fetches: a bare sample fragment,
    # meeting the same contract a real call site's endpoint must.
    path("fragment/", views.sample_fragment, name="sample_fragment"),
    path("c/<slug:slug>/", views.component, name="component"),
]
