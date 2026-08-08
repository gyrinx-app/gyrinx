"""Where a gang type's badge lives, and what an address is allowed to name.

A badge is a small SVG drawing. It is stored as a file in the site's own
storage — the same bucket every other upload goes to — and the row keeps its
address. That gives an author two ways to set one and one thing to read back:
upload a file, or paste the address of a drawing that is already there. The
upload writes into the same box, so there is never a pair of values competing
to be the answer.

The badge is drawn *inline* rather than as an image, which is what lets it take
the colour of the text beside it: an ``<img>`` is opaque to the page's colours,
so a badge in a heading and the same badge in a breadcrumb could not follow
either. Inline means the server reads the bytes, and reading bytes at an
address somebody typed is the dangerous half of this module.

So the address is resolved, never fetched. ``storage_key`` maps an address to
an object in this site's own storage and refuses everything else; the bytes
then come from the storage backend. There is no outbound request anywhere in
here, which is the point — a text box that made this server fetch whatever the
author could reach would reach internal services and cloud metadata endpoints,
not only the bucket.

What comes back is still untrusted: it is a file somebody uploaded. It is
cleaned where it is drawn (``n26.core.templatetags.artwork``), not here and not
on the way in, so tightening the allowlist re-secures artwork that is already
stored.
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

#: Where an uploaded badge is written inside the site's storage.
UPLOAD_PREFIX = "gang-type-icons/"

#: A badge is a line drawing of a few kilobytes. The cap is what keeps a
#: mistaken upload — a photograph, a whole map — out of the storage, and keeps
#: a page from pulling megabytes into memory to draw one glyph.
MAX_BYTES = 256 * 1024

#: The refusal an address outside this site's storage earns. Written once
#: because the authoring form and the admin both give it.
NOT_OURS = (
    "That address is not in this site's storage. Upload the drawing instead, "
    "or paste the address of one that is already uploaded here."
)

_CACHE_PREFIX = "n26-gang-type-artwork:"

#: How long a drawing that was read stays cached. Long, because a page that
#: lists gang types reads one object per type and every one of those is a
#: round trip to a bucket. An upload always lands on a name of its own, so the
#: only thing this delays is a drawing replaced in the bucket by hand.
_CACHE_HIT_SECONDS = 24 * 60 * 60

#: How long a failure stays cached. Short, so a missing object does not cost a
#: round trip on every render while a badge that has just been fixed appears
#: without waiting a day.
_CACHE_MISS_SECONDS = 60


def storage_bases():
    """Every address prefix that names this site's own uploads.

    ``MEDIA_URL`` is where the storage backend publishes what it holds, which
    is a local path in development and a bucket or a CDN address in
    production. The bucket's own address is listed as well: a CDN in front of
    it does not stop the bucket serving the same object, and both are
    addresses an author will have to hand.

    Every prefix ends in a slash, which is load-bearing — without it a bucket
    named in an attacker's own hostname would match on a prefix test.
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
    """The stored object an address names, or ``None`` if it names none.

    Refusing is the normal outcome for anything unexpected: the caller reads
    the bytes at whatever this returns, so a generous reading here is what
    would turn a text box into a way of making the server fetch arbitrary
    things. Only addresses inside this site's storage resolve.
    """
    if not address:
        return None

    split = urlsplit(str(address).strip())
    # A copied address often trails a query or a fragment. Neither names a
    # different object, so they are dropped rather than refused.
    trimmed = urlunsplit((split.scheme, split.netloc, split.path, "", ""))

    for base in storage_bases():
        if trimmed.startswith(base):
            key = unquote(trimmed[len(base) :])
            break
    else:
        return None

    # Decoding can put traversal back into a key that looked clean, so the
    # check happens after it and not before.
    if not key or key.startswith("/") or ".." in PurePosixPath(key).parts:
        return None
    return key


def read(address):
    """The SVG source at an address, or ``""`` if there is nothing to draw.

    Cached, because a badge is drawn once per row and reading one is a round
    trip to storage. The key is the object's own key, so two types pointing at
    the same drawing share an entry and repointing a type lands on a different
    one. Failures are cached as well, on a shorter clock.
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
        # Anything over the cap is not a badge, and inlining it would put
        # megabytes of somebody else's file into a page.
        if len(raw) <= MAX_BYTES:
            source = raw.decode("utf-8")
    except Exception:
        # Storage fails in as many ways as there are backends — a missing
        # object, a permission, a socket. None of them is a reason for a page
        # to stop drawing, so a badge that cannot be read is a badge that is
        # not there.
        logger.warning("Gang type artwork could not be read: %s", key, exc_info=True)

    cache.set(cache_key, source, _CACHE_HIT_SECONDS if source else _CACHE_MISS_SECONDS)
    return source


def store(upload):
    """Put an uploaded drawing in the site's storage; return its address.

    Refusals are in words, because an author trips them — the wrong kind of
    file, or one far too large to be a badge. Beyond those the file is stored
    as it arrived: the markup is cleaned every time it is drawn, so cleaning
    it here as well would only mean the stored drawing stops matching what its
    author made while gaining nothing.
    """
    name = PurePosixPath(upload.name or "").name
    if not name.lower().endswith(".svg"):
        raise ValidationError("A badge is an SVG file, and that one is not.")
    if upload.size and upload.size > MAX_BYTES:
        raise ValidationError(
            f"That file is over {MAX_BYTES // 1024}KB. A badge is a line "
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

    stem = slugify(PurePosixPath(name).stem) or "badge"
    stored = default_storage.save(f"{UPLOAD_PREFIX}{stem}.svg", ContentFile(raw))
    return default_storage.url(stored)


def clean_onto(form, cleaned, name, upload_name):
    """Settle one address field from its two controls, in place.

    An upload wins. It cannot happen by accident, whereas the address box
    arrives pre-filled with whatever the row already said — so uploading is
    how an author replaces a badge, and there is no state where the two
    controls disagree about the answer.

    Shared by the authoring form and the admin so the rule is stated once.
    """
    upload = cleaned.get(upload_name)
    if upload is not None:
        try:
            cleaned[name] = store(upload)
        except ValidationError as refusal:
            form.add_error(upload_name, refusal)
        return

    address = (cleaned.get(name) or "").strip()
    if address and storage_key(address) is None:
        form.add_error(name, NOT_OURS)
        return
    cleaned[name] = address
