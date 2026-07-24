from django import forms
from django.conf import settings
from tinymce.widgets import TinyMCE

# Additional TinyMCE configuration for forms. The menubar is off (see
# TINYMCE_UPLOAD_CONFIG), so this is just the Markdown-style shortcuts.
TINYMCE_EXTRA_ATTRS = {
    "textpattern_patterns": [
        {"start": "# ", "replacement": "<h1>%</h1>"},
        {"start": "## ", "replacement": "<h2>%</h2>"},
        {"start": "### ", "replacement": "<h3>%</h3>"},
        {"start": "#### ", "replacement": "<h4>%</h4>"},
        {"start": "##### ", "replacement": "<h5>%</h5>"},
        {"start": "###### ", "replacement": "<h6>%</h6>"},
        {
            "start": r"\*\*([^\*]+)\*\*",
            "replacement": "<strong>%</strong>",
        },
        {"start": r"\*([^\*]+)\*", "replacement": "<em>%</em>"},
    ],
}

# TinyMCE configuration with CSRF-aware upload handler
TINYMCE_UPLOAD_CONFIG = {
    "relative_urls": False,
    "promotion": False,
    "resize": "both",
    "width": "100%",
    "height": "400px",
    # Kept deliberately small. Across ~3,700 rich-text documents in production,
    # 80%+ are plain paragraphs; tables, colours and font pickers are used by a
    # handful of documents each, and nobody had ever set a text colour. The
    # menubar (which carried tables, fonts, colours, code samples and media) is
    # off, and the toolbar covers what people actually use.
    "plugins": "autoresize autosave image link lists textpattern",
    "toolbar": "undo redo | blocks | bold italic underline | bullist numlist | link image | removeformat",
    "menubar": False,
    # Images are laid out by the page, not hand-sized by the author: no
    # width/height fields in the image dialog and no drag handles, both of
    # which wrote inline dimensions (often percentages). Site CSS already caps
    # images at the container width.
    "image_dimensions": False,
    "object_resizing": False,
    "content_style": "img { max-width: 100%; height: auto; }",
    # Character encoding configuration
    "entity_encoding": "raw",  # Store UTF-8 characters instead of HTML entities
    # Image upload configuration
    "automatic_uploads": True,
    "images_upload_credentials": True,
    "file_picker_types": "image",
    "images_reuse_filename": False,
    # Custom upload handler to include CSRF token
    "images_upload_handler": """
        async function (blobInfo, progress) {
            // Get CSRF token from form field or cookie
            const getCsrfToken = () => {
                // Try to get from form field first
                const tokenField = document.querySelector('[name=csrfmiddlewaretoken]');
                if (tokenField?.value) {
                    return tokenField.value;
                }

                // Fall back to cookie (name injected from settings.CSRF_COOKIE_NAME
                // below, so per-worktree dev cookie renaming doesn't break uploads)
                const name = '__CSRF_COOKIE_NAME__';
                const cookies = document.cookie.split(';');
                for (const cookie of cookies) {
                    const trimmed = cookie.trim();
                    if (trimmed.startsWith(name + '=')) {
                        return decodeURIComponent(trimmed.substring(name.length + 1));
                    }
                }
                return null;
            };

            const formData = new FormData();
            formData.append('file', blobInfo.blob(), blobInfo.filename());

            try {
                const response = await fetch('/tinymce/upload/', {
                    method: 'POST',
                    body: formData,
                    credentials: 'same-origin',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                    },
                });

                if (!response.ok) {
                    throw new Error(`HTTP Error: ${response.status}`);
                }

                const data = await response.json();

                if (!data || typeof data.location !== 'string') {
                    throw new Error('Invalid response: missing location');
                }

                return data.location;
            } catch (error) {
                throw new Error(`Image upload failed: ${error.message}`);
            }
        }
    """,
}

# Inject the configured CSRF cookie name into the upload handler's cookie-fallback
# branch. Defaults to "csrftoken", but settings_dev.py renames it per-worktree so
# concurrent dev servers don't share one cookie jar — the JS must read the same name.
TINYMCE_UPLOAD_CONFIG["images_upload_handler"] = TINYMCE_UPLOAD_CONFIG[
    "images_upload_handler"
].replace("__CSRF_COOKIE_NAME__", settings.CSRF_COOKIE_NAME)


class TinyMCEWithUpload(TinyMCE):
    """TinyMCE widget with image upload support and CSRF handling."""

    def __init__(self, attrs=None, mce_attrs=None, **kwargs):
        if mce_attrs is None:
            mce_attrs = {}

        # Merge with default upload config
        final_mce_attrs = {**TINYMCE_UPLOAD_CONFIG, **mce_attrs}

        super().__init__(attrs=attrs, mce_attrs=final_mce_attrs, **kwargs)


class ColorRadioSelect(forms.RadioSelect):
    """
    Custom radio select widget for choosing colors from a predefined palette.
    """

    template_name = "core/widgets/color_radio_select.html"
    option_template_name = "core/widgets/color_radio_option.html"

    # Predefined color palette — dark / base / light per hue, paired in rows of 6
    COLOR_PALETTE = [
        # Row 1: None + White
        ("", "None (Default)"),
        ("#fefdfb", "White"),
        # Row 2: Red + Yellow
        ("#90101a", "Dark Red"),
        ("#f14d4c", "Red"),
        ("#ffbab3", "Light Red"),
        ("#6c4300", "Dark Yellow"),
        ("#c57d00", "Yellow"),
        ("#f8c384", "Light Yellow"),
        # Row 3: Green + Teal
        ("#4c5300", "Dark Green"),
        ("#8d9900", "Green"),
        ("#cbd689", "Light Green"),
        ("#005c3b", "Dark Teal"),
        ("#00aa6f", "Teal"),
        ("#92e2b7", "Light Teal"),
        # Row 4: Cyan + Blue
        ("#005860", "Dark Cyan"),
        ("#00a2af", "Cyan"),
        ("#76e1ed", "Light Cyan"),
        ("#004f8b", "Dark Blue"),
        ("#0092f9", "Blue"),
        ("#a8d2ff", "Light Blue"),
        # Row 5: Violet + Rose
        ("#563199", "Dark Violet"),
        ("#9b6efa", "Violet"),
        ("#d1c4ff", "Light Violet"),
        ("#811968", "Dark Rose"),
        ("#da52b5", "Rose"),
        ("#fbb4e2", "Light Rose"),
    ]

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, choices=self.COLOR_PALETTE)

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        # Add the color value to the option context for use in the template
        option["color"] = value
        option["label"] = label  # Ensure label is available for tooltip
        return option
