from django import forms
from tinymce.widgets import TinyMCE

# Additional TinyMCE configuration for forms
TINYMCE_EXTRA_ATTRS = {
    "menu": {
        "edit": {
            "title": "Edit",
            "items": "undo redo | cut copy paste pastetext | selectall | searchreplace",
        },
        "view": {
            "title": "View",
            "items": "code revisionhistory | visualaid visualchars visualblocks | spellchecker | preview fullscreen | showcomments",
        },
        "insert": {
            "title": "Insert",
            "items": "image link media addcomment pageembed codesample inserttable | math | charmap emoticons hr | pagebreak nonbreaking anchor tableofcontents | insertdatetime",
        },
        "format": {
            "title": "Format",
            "items": "bold italic underline strikethrough superscript subscript codeformat | styles blocks fontfamily fontsize align lineheight | forecolor backcolor | language | removeformat",
        },
        "tools": {
            "title": "Tools",
            "items": "spellchecker spellcheckerlanguage | a11ycheck code wordcount",
        },
        "table": {
            "title": "Table",
            "items": "inserttable | cell row column | advtablesort | tableprops deletetable",
        },
    },
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
    "plugins": "autoresize autosave code emoticons fullscreen help image link lists quickbars textpattern visualblocks",
    "toolbar": "undo redo | blocks | bold italic underline link image | numlist bullist align | code",
    "menubar": "edit view insert format table tools help",
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

                // Fall back to cookie
                const name = 'csrftoken';
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

    # Predefined color palette
    COLOR_PALETTE = [
        ("", "None (Default)"),
        # Base colors
        ("#386b33", "Green"),
        ("#6bb261", "Bright Green"),
        ("#a7d9a3", "Pastel Green"),
        ("#d62e31", "Red"),
        ("#ff5a5e", "Bright Red"),
        ("#ffb3b5", "Pastel Red"),
        ("#ffa629", "Orange"),
        ("#ffbc5c", "Bright Orange"),
        ("#ffd6a6", "Pastel Orange"),
        ("#ffbb5c", "Yellow"),
        ("#ffcc77", "Bright Yellow"),
        ("#ffe4b3", "Pastel Yellow"),
        ("#4593c4", "Blue"),
        ("#5fa9d9", "Bright Blue"),
        ("#a1c8e2", "Pastel Blue"),
        ("#7b68ee", "Purple"),
        ("#9d8fff", "Bright Purple"),
        ("#c4b5fd", "Pastel Purple"),
        ("#ff69b4", "Pink"),
        ("#ff8ec4", "Bright Pink"),
        ("#ffb6d9", "Pastel Pink"),
        ("#40e0d0", "Turquoise"),
        ("#66e9de", "Bright Turquoise"),
        ("#a3f0e8", "Pastel Turquoise"),
        ("#fefdfb", "White"),
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
