"""Move the Necromunda 2023 help pages under /help/n23/.

Eight of the ten pages under /help/ are about playing Necromunda 2023
specifically — six of them say "Necromunda" in the opening line. The other two
(the hub itself, and Alpha Testing) are about Gyrinx the product. Separating
them now means a second edition has somewhere to put its own guides.

Done as one migration rather than by hand in the admin so that the URL change
and its redirect land together. Split across two deploys — or two admin
sessions — there is a window where a page has moved and every existing link to
it 404s.

Three things have to happen together, and the third is the one that is easy to
miss:

1. The eight pages move.
2. A redirect is created for each old URL, so bookmarks and search results keep
   working. django.contrib.redirects serves these; enabled separately.
3. A new /help/n23/ hub page is created.

(3) is not cosmetic. The help navigation in flatpages/default.html is derived
from the URL path, not from links: `pages_parent` looks up the parent URL,
sibling lists come from a path prefix, and each page lists its own children.
Without a page at /help/n23/, the eight moved pages would each lose their
back-link (pages_parent returns None), and /help/ would stop listing them
entirely — its children would be Alpha Testing and nothing else. Nothing would
error. The help section would just quietly become unnavigable.

Internal links in nine other pages are rewritten too. The redirects would keep
them working, but every one would cost a 301 hop, and the point of the redirects
is bookmarks and external links rather than covering for our own stale hrefs.
"""

from django.db import migrations

MOVES = {
    "/help/arbitration/": "/help/n23/arbitration/",
    "/help/buildingalist/": "/help/n23/buildingalist/",
    "/help/campaignplay/": "/help/n23/campaignplay/",
    "/help/customcontent/": "/help/n23/customcontent/",
    "/help/outcasts/": "/help/n23/outcasts/",
    "/help/rules/": "/help/n23/rules/",
    "/help/tipsandtricksforlists/": "/help/n23/tipsandtricksforlists/",
    "/help/vehicles/": "/help/n23/vehicles/",
}

HUB_URL = "/help/n23/"
HUB_TITLE = "Necromunda 2023"
HUB_CONTENT = (
    '<h1><strong><span style="font-size: 24pt;">Necromunda 2023</span></strong></h1>\r\n'
    "<p>(Gangs, campaigns, and the rules)</p>\r\n"
    "<p><strong>Everything here is about playing Necromunda 2023 with Gyrinx — "
    "building a gang, running a campaign, and how we handle the rules.</strong></p>\r\n"
    "<p>Guides that apply however you use Gyrinx stay in the main "
    '<a href="/help/">help hub</a>.</p>'
)


def _rewrite_links(FlatPage, mapping):
    """Repoint internal hrefs. Only touches pages that actually contain one."""
    changed = 0
    for page in FlatPage.objects.all():
        content = page.content or ""
        updated = content
        for old, new in mapping.items():
            updated = updated.replace(f'href="{old}"', f'href="{new}"')
        if updated != content:
            page.content = updated
            page.save(update_fields=["content"])
            changed += 1
    return changed


def move_to_n23(apps, schema_editor):
    FlatPage = apps.get_model("flatpages", "FlatPage")
    Redirect = apps.get_model("redirects", "Redirect")
    Site = apps.get_model("sites", "Site")

    site = Site.objects.first()
    if site is None:
        return  # a database with no site configured has no flatpages to move

    # The hub first, so the moved pages have a parent to point at.
    hub, created = FlatPage.objects.get_or_create(
        url=HUB_URL, defaults={"title": HUB_TITLE, "content": HUB_CONTENT}
    )
    if created:
        hub.sites.add(site)

    for old, new in MOVES.items():
        page = FlatPage.objects.filter(url=old).first()
        if page is None:
            continue  # already moved, or never existed here
        page.url = new
        page.save(update_fields=["url"])
        Redirect.objects.get_or_create(
            site=site, old_path=old, defaults={"new_path": new}
        )

    _rewrite_links(FlatPage, MOVES)


def move_back(apps, schema_editor):
    FlatPage = apps.get_model("flatpages", "FlatPage")
    Redirect = apps.get_model("redirects", "Redirect")

    for old, new in MOVES.items():
        page = FlatPage.objects.filter(url=new).first()
        if page is not None:
            page.url = old
            page.save(update_fields=["url"])
    Redirect.objects.filter(old_path__in=MOVES).delete()

    _rewrite_links(FlatPage, {v: k for k, v in MOVES.items()})

    # Only remove the hub if it is still the page this migration wrote. If
    # someone has edited it, leave it — losing their copy would be worse than
    # leaving a stray page behind.
    hub = FlatPage.objects.filter(url=HUB_URL).first()
    if hub is not None and hub.content == HUB_CONTENT:
        hub.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0006_alter_flatpagevisibility_created_and_more"),
        ("flatpages", "0001_initial"),
        ("redirects", "0002_alter_redirect_new_path_help_text"),
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [migrations.RunPython(move_to_n23, move_back)]
