"""Read and store uploaded SVG artwork within this site's storage.

Resolve addresses to storage keys before reading bytes. Never fetch arbitrary
URLs: they could expose internal services or cloud metadata. Returned SVG is
untrusted and must pass through gyrinx.svg.sanitize_inline_svg at rendering,
so allowlist changes also apply to existing uploads.
"""

import logging
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit, urlunsplit

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify

logger = logging.getLogger(__name__)

#: Where an upload is written when the caller names no folder of its own.
DEFAULT_UPLOAD_PREFIX = "artwork/"

# : Limit uploads and reads so inline artwork cannot consume excessive memory.
MAX_BYTES = 256 * 1024

# : Shared validation message for addresses outside this site's storage.
NOT_OURS = (
    "That address is not in this site's storage. Upload the drawing instead, "
    "or paste the address of one that is already uploaded here."
)

_CACHE_PREFIX = "artwork:"

# : Uploads use unique names, so cache hits only delay manual storage replacements.
_CACHE_HIT_SECONDS = 24 * 60 * 60

# : Retry missing or repaired artwork sooner while avoiding a read on every render.
_CACHE_MISS_SECONDS = 60


def storage_bases():
    """Return slash-terminated URL prefixes for this site's uploads.

    Accept MEDIA_URL and the configured bucket address, including when a CDN
    serves the same objects. The trailing slash prevents matching a different
    host or bucket with the same prefix.
    """
    bases = []
    media = str(getattr(settings, "MEDIA_URL", "") or "")
    if media:
        bases.append(media if media.endswith("/") else media + "/")
    bucket = getattr(settings, "GS_BUCKET_NAME", None)
    if bucket:
        bases.append(f"https://storage.googleapis.com/{bucket}/")
    return bases


def storage_key(address):
    """Return the storage key for an allowed upload address, or None.

    Only this site's storage prefixes may resolve; callers read the resulting
    key directly from the storage backend.
    """
    if not address:
        return None

    split = urlsplit(str(address).strip())
    # Queries and fragments do not change the stored object identity.
    trimmed = urlunsplit((split.scheme, split.netloc, split.path, "", ""))

    for base in storage_bases():
        if trimmed.startswith(base):
            key = unquote(trimmed[len(base) :])
            break
    else:
        return None

    # Check traversal after decoding, which may reveal encoded path segments.
    if not key or key.startswith("/") or ".." in PurePosixPath(key).parts:
        return None
    return key


def read(address):
    """Return the stored SVG source, or an empty string when it is unavailable.

    Cache by storage key so references to the same artwork share a read. Cache
    read failures for a shorter period.
    """
    key = storage_key(address)
    if key is None:
        return ""

    cache_key = _CACHE_PREFIX + sha256(key.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    source = ""
    try:
        with default_storage.open(key, "rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        # Do not inline a file that exceeds the artwork size limit.
        if len(raw) <= MAX_BYTES:
            source = raw.decode("utf-8")
    except Exception:
        # Storage errors omit artwork without preventing the page from rendering.
        logger.warning("Artwork could not be read: %s", key, exc_info=True)

    cache.set(cache_key, source, _CACHE_HIT_SECONDS if source else _CACHE_MISS_SECONDS)
    return source


def store(upload, prefix=DEFAULT_UPLOAD_PREFIX):
    """Store an uploaded SVG under prefix and return its address.

    Raise ValidationError for an invalid file type or excessive size. Store
    the source unchanged; callers sanitise it when rendering.
    """
    name = PurePosixPath(upload.name or "").name
    if not name.lower().endswith(".svg"):
        raise ValidationError("A drawing is an SVG file, and that one is not.")
    if upload.size and upload.size > MAX_BYTES:
        raise ValidationError(
            f"That file is over {MAX_BYTES // 1024}KB. A drawing is a line "
            f"drawing of a few kilobytes, so this is probably not one."
        )

    raw = upload.read()
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as refusal:
        raise ValidationError(
            "That file does not read as text, so it is not SVG source."
        ) from refusal
    if "<svg" not in source.lower():
        raise ValidationError("That file has no <svg> element in it.")

    stem = slugify(PurePosixPath(name).stem) or "artwork"
    stored = default_storage.save(f"{prefix}{stem}.svg", ContentFile(raw))
    return default_storage.url(stored)


def clean_onto(form, cleaned, name, upload_name, prefix=DEFAULT_UPLOAD_PREFIX):
    """Set an artwork address from form data, with uploads taking precedence.

    The address control may contain an existing value, so an explicit upload
    replaces it. Shared by authoring forms and admin forms.
    """
    upload = cleaned.get(upload_name)
    if upload is not None:
        try:
            cleaned[name] = store(upload, prefix=prefix)
        except ValidationError as refusal:
            form.add_error(upload_name, refusal)
        return

    address = (cleaned.get(name) or "").strip()
    if address and storage_key(address) is None:
        form.add_error(name, NOT_OURS)
        return
    cleaned[name] = address
