"""Exercise the local upload endpoint and its staff/CSRF boundaries."""

import io
import tempfile
from pathlib import Path

import server
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from PIL import Image

user = get_user_model().objects.get(username="design-preview")
with (
    override_settings(ALLOWED_HOSTS=["testserver"]),
    tempfile.TemporaryDirectory(prefix="gyrinx-upload-check-") as directory,
):
    server.UPLOAD_ROOT = Path(directory)
    client = Client(enforce_csrf_checks=True)
    assert (
        client.post(
            "/tinymce/upload/",
            {"file": SimpleUploadedFile("notes.txt", b"Notes"), "kind": "file"},
        ).status_code
        == 403
    )
    client.force_login(user)
    client.get("/admin/flatpages/flatpage/1/change/")
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    assert (
        client.post(
            "/tinymce/upload/",
            {"file": SimpleUploadedFile("notes.txt", b"Notes"), "kind": "file"},
        ).status_code
        == 403
    )

    def upload(name, content, kind="file"):
        return client.post(
            "/tinymce/upload/",
            {"file": SimpleUploadedFile(name, content), "kind": kind},
            HTTP_X_CSRFTOKEN=csrf,
        )

    assert upload("page.html", b"<script>alert(1)</script>").status_code == 400
    assert upload("fake.pdf", b"not a PDF").status_code == 400
    assert upload("fake.png", b"not an image", "image").status_code == 400
    assert upload("large.txt", b"x" * (server.MAX_UPLOAD_BYTES + 1)).status_code == 400
    assert upload("empty.txt", b"").status_code == 400
    response = upload("campaign notes.txt", b"Campaign notes")
    assert response.status_code == 200
    address = response.json()["location"].replace("http://testserver", "")
    stored = client.get(address)
    assert b"".join(stored.streaming_content) == b"Campaign notes"
    assert stored["Content-Disposition"].startswith("attachment;")
    assert stored["X-Content-Type-Options"] == "nosniff"
    assert Client().get(address).status_code == 403
    image = io.BytesIO()
    Image.new("RGB", (32, 16), "orange").save(image, format="PNG")
    response = upload("image.png", image.getvalue(), "image")
    assert response.status_code == 200
    stored = client.get(response.json()["location"].replace("http://testserver", ""))
    assert stored["Content-Type"] == "image/png"
    assert stored["Content-Disposition"].startswith("inline;")
    assert b"".join(stored.streaming_content) == image.getvalue()
print(
    "Passed: staff-only uploads/downloads, CSRF, file validation, size limit, stored document downloads and image rendering."
)
