"""Form widgets shared across the project."""

from tinymce.widgets import TinyMCE

from n26.uploads import TINYMCE_UPLOAD_CONFIG


class RichText(TinyMCE):
    """A rich text widget using settings.TINYMCE_DEFAULT_CONFIG.

    Campaign summaries opt into the shared image-upload handler through the
    edition seam. Other fields use URL-based image controls.

    Render form.media so the textarea is enhanced into an editor.
    ``height`` sets both height and max_height to bound TinyMCE autoresize.
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
    "setup": "n26CampaignImages",
}


def campaign_editor_props():
    """The campaign description editor configuration for a React-owned editor."""
    from django.templatetags.static import static
    from tinymce.settings import DEFAULT_CONFIG, get_js_url

    config = {**DEFAULT_CONFIG, **CAMPAIGN_SUMMARY_CONFIG}
    for callback in ("setup", "images_upload_handler"):
        config.pop(callback, None)
    return {
        "scriptUrl": get_js_url(),
        "imageSetupUrl": static("n26/richtext.js"),
        "uploadUrl": "/tinymce/upload/",
        "config": config,
    }
