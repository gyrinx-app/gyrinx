"""Form widgets shared across the project."""

from tinymce.widgets import TinyMCE


class RichText(TinyMCE):
    """A rich text field, configured in ``settings.TINYMCE_DEFAULT_CONFIG``.

    Thin on purpose. django-tinymce already merges the project default config
    into every widget, so this exists to give the editor a name of its own —
    ``forms.CharField(widget=RichText())`` reads better than the library class,
    and it is somewhere to hang per-field overrides later.

    The main gyrinx app's equivalent, ``TinyMCEWithUpload``, also carries an
    image upload handler pointed at ``/tinymce/upload/``. That is left out here:
    this sandbox has no media storage or upload endpoint, and a broken upload
    button would be worse than none. The link and image plugins still work for
    URLs.

    Remember ``{{ form.media }}``. The editor is inert without it — the widget
    only renders a textarea carrying its config in a data attribute, and the
    JavaScript that turns it into an editor arrives through the form's media.
    """

    def __init__(self, attrs=None, mce_attrs=None, **kwargs):
        attrs = {"rows": 10, **(attrs or {})}
        super().__init__(attrs=attrs, mce_attrs=mce_attrs or {}, **kwargs)
