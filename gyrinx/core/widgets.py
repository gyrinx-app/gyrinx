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

    # Predefined color palette — dark / base / light per hue
    COLOR_PALETTE = [
        ("", "None (Default)"),
        ("#681438", "Dark Red"),
        ("#d6638b", "Red"),
        ("#ffb6cb", "Light Red"),
        ("#6b1900", "Dark Orange"),
        ("#da694a", "Orange"),
        ("#ffbba8", "Light Orange"),
        ("#523300", "Dark Yellow"),
        ("#c27f00", "Yellow"),
        ("#f7c383", "Light Yellow"),
        ("#3f3d00", "Dark Green"),
        ("#989400", "Green"),
        ("#d4d385", "Light Green"),
        ("#004809", "Dark Teal"),
        ("#4da64f", "Teal"),
        ("#a6dfa4", "Light Teal"),
        ("#00453c", "Dark Cyan"),
        ("#00a692", "Cyan"),
        ("#7ee3d0", "Light Cyan"),
        ("#00424f", "Dark Azure"),
        ("#00a0bc", "Azure"),
        ("#7adef7", "Light Azure"),
        ("#003b6f", "Dark Blue"),
        ("#4092e7", "Blue"),
        ("#aad2ff", "Light Blue"),
        ("#3a2b74", "Dark Magenta"),
        ("#8c7de4", "Magenta"),
        ("#cac6ff", "Light Magenta"),
        ("#571e5d", "Dark Rose"),
        ("#bb6cc2", "Rose"),
        ("#efb8f3", "Light Rose"),
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
