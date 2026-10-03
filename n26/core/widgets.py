"""Form widgets shared across the project."""

from tinymce.widgets import TinyMCE

from gyrinx.widgets import TINYMCE_UPLOAD_CONFIG


class RichText(TinyMCE):
    """A rich text field, configured in ``settings.TINYMCE_DEFAULT_CONFIG``.

    Thin on purpose. django-tinymce already merges the project default config
    into every widget, so this exists to give the editor a name of its own —
    ``forms.CharField(widget=RichText())`` reads better than the library class,
    and it is somewhere to hang per-field overrides later.

    The main gyrinx app's equivalent, ``TinyMCEWithUpload``, also carries an
    image upload handler pointed at ``/tinymce/upload/``. Campaign summaries
    opt into that shared handler. Other fields retain their existing URL-only
    image controls.

    Remember ``{{ form.media }}``. The editor is inert without it — the widget
    only renders a textarea carrying its config in a data attribute, and the
    JavaScript that turns it into an editor arrives through the form's media.

    ``height`` fixes the editor at that many pixels, scrolling inside.
    Set as both ``height`` and ``max_height``: the first is only where an
    editor starts, and an editor running the autoresize plugin grows past
    it with what is typed until the second stops it. The bundled TinyMCE
    is version 7, whose autoresize reads ``max_height``.
    """

    def __init__(self, attrs=None, mce_attrs=None, height=None, **kwargs):
        attrs = {"rows": 10, **(attrs or {})}
        mce_attrs = dict(mce_attrs or {})
        if height is not None:
            mce_attrs = {"height": height, "max_height": height, **mce_attrs}
        super().__init__(attrs=attrs, mce_attrs=mce_attrs, **kwargs)


# A campaign summary needs links, tables and uploaded images without changing the
# controls offered by gang notes or library descriptions.
CAMPAIGN_SUMMARY_CONFIG = {
    **TINYMCE_UPLOAD_CONFIG,
    "plugins": "autoresize autolink image link lists table",
    "toolbar": (
        "undo redo | blocks | bold italic underline | bullist numlist | "
        "link image table | removeformat"
    ),
    "menubar": False,
    "image_dimensions": False,
    "object_resizing": False,
    "content_style": "img { max-width: 100%; height: auto; }",
    "paste_data_images": True,
    "paste_block_drop": False,
}
