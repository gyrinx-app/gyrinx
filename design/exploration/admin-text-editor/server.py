"""Isolated staff-admin playground; never connects to the application database."""

import io
import json
import re
import secrets
import sys
import warnings
import zipfile
from pathlib import Path
from urllib.parse import quote

from bootstrap import HERE, PORT, secret
from django.contrib import admin
from django.contrib.auth import get_user_model, login
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import redirect
from django.urls import path
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST
from lab.models import Document
from PIL import Image, UnidentifiedImageError

UPLOAD_ROOT = HERE / "uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
FILE_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
IMAGE_TYPES = {
    ".png": ("PNG", "image/png"),
    ".jpg": ("JPEG", "image/jpeg"),
    ".jpeg": ("JPEG", "image/jpeg"),
    ".gif": ("GIF", "image/gif"),
    ".webp": ("WEBP", "image/webp"),
}


@require_POST
def upload(request):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    file = request.FILES.get("file")
    kind = request.POST.get("kind", "image")
    if file is None:
        return JsonResponse({"error": "Choose a file to upload."}, status=400)
    if kind not in ("file", "image"):
        return JsonResponse({"error": "Choose a file or image upload."}, status=400)
    if not file.size or file.size > MAX_UPLOAD_BYTES:
        return JsonResponse(
            {"error": "Choose a file between 1 byte and 10 MB."}, status=400
        )
    extension = Path(file.name).suffix.lower()
    if extension not in (IMAGE_TYPES if kind == "image" else FILE_TYPES):
        return JsonResponse({"error": "That file type is not supported."}, status=400)
    content = file.read(MAX_UPLOAD_BYTES + 1)
    try:
        if kind == "image":
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    if image.format != IMAGE_TYPES[extension][0]:
                        raise ValueError()
                    image.verify()
        elif extension == ".pdf":
            if not content.startswith(b"%PDF-"):
                raise ValueError()
        elif extension in (".txt", ".md", ".csv"):
            if "\x00" in content.decode("utf-8-sig"):
                raise ValueError()
        else:
            part = {
                ".docx": "word/document.xml",
                ".xlsx": "xl/workbook.xml",
                ".pptx": "ppt/presentation.xml",
            }[extension]
            with zipfile.ZipFile(io.BytesIO(content)) as document:
                names = document.namelist()
                if "[Content_Types].xml" not in names or part not in names:
                    raise ValueError()
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        zipfile.BadZipFile,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return JsonResponse(
            {"error": "The file could not be read as that file type."}, status=400
        )
    name = Path(get_valid_filename(file.name)).stem[:100] + extension
    token = secrets.token_hex(16)
    directory = UPLOAD_ROOT / token
    directory.mkdir(parents=True)
    (directory / name).write_bytes(content)
    return JsonResponse(
        {
            "location": request.build_absolute_uri(f"/uploads/{token}/{quote(name)}"),
            "filename": name,
            "size": len(content),
            "id": token,
        }
    )


def uploaded_file(request, token, filename):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    if not re.fullmatch(r"[a-f0-9]{32}", token) or filename != Path(filename).name:
        raise Http404()
    file = UPLOAD_ROOT / token / filename
    extension = file.suffix.lower()
    if not file.is_file() or extension not in {*FILE_TYPES, *IMAGE_TYPES}:
        raise Http404()
    response = FileResponse(
        file.open("rb"),
        as_attachment=extension in FILE_TYPES,
        filename=filename,
        content_type=FILE_TYPES.get(extension) or IMAGE_TYPES[extension][1],
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


def home(request):
    return HttpResponse(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Gyrinx editor design workspace</title></head><body style="font:16px system-ui;max-width:720px;margin:4rem auto;padding:1rem"><h1>Gyrinx editor design workspace</h1><p>A local Django staff-admin form with a working rich-text editor, using Gyrinx’s N26 design library.</p><p>Open the one-click preview link printed by the start script to sign in.</p><p>All documents are stored in this playground’s separate local database.</p></body></html>'
    )


def enter(request, token):
    if not secrets.compare_digest(token, secret):
        return HttpResponseForbidden("Invalid preview link.")
    user = get_user_model().objects.get(username="design-preview")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("/admin/flatpages/flatpage/1/change/")


@require_POST
def preview(request):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        html = json.loads(request.body)["html"]
        if not isinstance(html, str) or len(html) > 1_000_000:
            raise ValueError()
    except KeyError, ValueError:
        return JsonResponse({"error": "Invalid content"}, status=400)
    from callout_preview import rendered_preview

    return JsonResponse(rendered_preview(html))


urlpatterns = [
    path("", home),
    path("enter/<str:token>/", enter),
    path("tinymce/upload/", upload),
    path("uploads/<str:token>/<str:filename>", uploaded_file),
    path("preview/", preview),
    path(
        "admin/lab/document/1/change/",
        lambda request: redirect("/admin/flatpages/flatpage/1/change/"),
    ),
    path("admin/", admin.site.urls),
]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        call_command("migrate", run_syncdb=True, verbosity=0)
        user, created = get_user_model().objects.get_or_create(
            username="design-preview", defaults={"is_staff": True, "is_superuser": True}
        )
        if created:
            user.set_unusable_password()
            user.save()
        Document.objects.get_or_create(
            pk=1,
            defaults={
                "title": "Campaign introduction",
                "body": "<h2>The Ash Road</h2><p>Our campaign follows a trading route through the underhive. Add an introduction for the players.</p><p><strong>Before the first game</strong></p><ul><li>Choose a name for your gang.</li><li>Agree where the opening battle takes place.</li><li>Bring your roster and dice.</li></ul><blockquote><p>Keep campaign notes here as the story develops.</p></blockquote>",
            },
        )
        document = Document.objects.get(pk=1)
        page, created = FlatPage.objects.get_or_create(
            pk=1,
            defaults={
                "url": "/help/editor-playground/",
                "title": document.title,
                "content": document.body,
            },
        )
        site, _ = Site.objects.update_or_create(
            pk=1,
            defaults={
                "domain": f"127.0.0.1:{PORT}",
                "name": "Local Gyrinx playground",
            },
        )
        if created:
            page.sites.add(site)
        print("Demo database and staff preview account ready.")
    elif len(sys.argv) > 1 and sys.argv[1] == "link":
        print(f"http://127.0.0.1:{PORT}/enter/{secret}/")
    else:
        call_command("runserver", f"127.0.0.1:{PORT}", use_reloader=False)
