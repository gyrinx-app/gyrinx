"""Campaign asset-type edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, i, label, small
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"

# Static markup (templates + inline scripts) from
# ``core/campaign/includes/property_schema_editor.html`` — copied verbatim so
# the client-side editor behaves identically. No Django template variables.
_PROPERTY_EDITOR_STATIC = raw(
    """
<template id="property-row-template">
    <div class="property-row d-flex flex-column gap-2 p-2 border rounded bg-body-tertiary">
        <div class="d-flex flex-column flex-sm-row gap-2">
            <div class="flex-grow-1">
                <input type="text"
                       class="form-control form-control-sm property-label"
                       placeholder="Label (e.g., Boon)">
            </div>
            <div class="flex-shrink-0">
                <button type="button"
                        class="btn btn-outline-danger btn-sm remove-property-btn">
                    <i class="bi-trash"></i>
                </button>
            </div>
        </div>
        <div>
            <input type="text"
                   class="form-control form-control-sm property-description"
                   placeholder="Description (optional)">
        </div>
    </div>
</template>
<script>
document.addEventListener('DOMContentLoaded', function() {
    const schemaList = document.getElementById('property-schema-list');
    const addBtn = document.getElementById('add-property-btn');
    const jsonField = document.getElementById('property-schema-json');
    const template = document.getElementById('property-row-template');

    // Generate a short random suffix for key uniqueness
    function randomSuffix() {
        return Math.random().toString(36).substring(2, 6);
    }

    // Parse initial schema from the hidden field
    let schema = [];
    try {
        schema = JSON.parse(jsonField.value || '[]');
    } catch (e) {
        console.error('Failed to parse property schema:', e);
        schema = [];
    }

    // Render existing properties — pass the stable key so it is preserved on rename
    schema.forEach(prop => addPropertyRow(prop.label, prop.description || '', prop.key || ''));

    // Add new property button handler
    addBtn.addEventListener('click', function() {
        addPropertyRow('', '', '');
        // Focus the new label input
        const rows = schemaList.querySelectorAll('.property-row');
        const lastRow = rows[rows.length - 1];
        if (lastRow) {
            lastRow.querySelector('.property-label').focus();
        }
        updateJsonField();
    });

    function addPropertyRow(label, description, existingKey) {
        const row = template.content.cloneNode(true);
        const labelInput = row.querySelector('.property-label');
        const descInput = row.querySelector('.property-description');
        const removeBtn = row.querySelector('.remove-property-btn');
        const rowDiv = row.querySelector('.property-row');

        labelInput.value = label || '';
        descInput.value = description || '';

        // Store the stable key on the DOM element so it survives label renames.
        // New rows get a random key immediately to avoid locking a key based on
        // a partial label (updateJsonField fires on every keystroke).
        rowDiv.dataset.stableKey = existingKey || ('prop_' + randomSuffix() + randomSuffix());

        // Update JSON on input changes
        labelInput.addEventListener('input', updateJsonField);
        descInput.addEventListener('input', updateJsonField);

        // Remove button handler
        removeBtn.addEventListener('click', function() {
            this.closest('.property-row').remove();
            updateJsonField();
        });

        schemaList.appendChild(row);
    }

    function updateJsonField() {
        const rows = schemaList.querySelectorAll('.property-row');
        const newSchema = [];
        const usedKeys = new Set();

        rows.forEach(row => {
            const label = row.querySelector('.property-label').value.trim();
            const description = row.querySelector('.property-description').value.trim();
            if (label) {
                const key = row.dataset.stableKey;
                usedKeys.add(key);

                const prop = { key, label };
                if (description) {
                    prop.description = description;
                }
                newSchema.push(prop);
            }
        });

        jsonField.value = JSON.stringify(newSchema);
    }

    // Initial update to sync
    updateJsonField();
});
</script>
"""
)

# Static markup (templates + inline scripts) from
# ``core/campaign/includes/sub_asset_schema_editor.html`` — copied verbatim.
_SUB_ASSET_EDITOR_STATIC = raw(
    """
<template id="sub-asset-type-template">
    <div class="sub-asset-type-entry p-3 border rounded bg-body-tertiary">
        <div class="d-flex justify-content-between align-items-start mb-2">
            <strong class="sub-asset-type-title">New Sub-Asset Type</strong>
            <button type="button"
                    class="btn btn-outline-danger btn-sm remove-sub-asset-type-btn">
                <i class="bi-trash"></i>
            </button>
        </div>
        <div class="row g-2 mb-2">
            <div class="col-md-6">
                <label class="form-label fs-7">Label (singular)</label>
                <input type="text"
                       class="form-control form-control-sm sub-asset-label"
                       placeholder="e.g., Structure">
            </div>
            <div class="col-md-6">
                <label class="form-label fs-7">Label (plural)</label>
                <input type="text"
                       class="form-control form-control-sm sub-asset-label-plural"
                       placeholder="e.g., Structures">
            </div>
        </div>
        <div class="mb-2">
            <label class="form-label fs-7">Description (optional)</label>
            <input type="text"
                   class="form-control form-control-sm sub-asset-description"
                   placeholder="e.g., Buildings within the settlement">
        </div>
        <div class="mb-2">
            <label class="form-label fs-7">Properties</label>
            <div class="sub-asset-properties-list vstack gap-1">
                <!-- Property rows will be added here -->
            </div>
            <button type="button"
                    class="btn btn-outline-secondary btn-sm mt-1 add-sub-asset-property-btn">
                <i class="bi-plus"></i> Add Property
            </button>
        </div>
    </div>
</template>
<template id="sub-asset-property-template">
    <div class="sub-asset-property d-flex gap-2 align-items-center">
        <input type="text"
               class="form-control form-control-sm sub-asset-prop-label flex-grow-1"
               placeholder="Property label (e.g., Benefit)">
        <button type="button"
                class="btn btn-outline-danger btn-sm remove-sub-asset-property-btn">
            <i class="bi-x"></i>
        </button>
    </div>
</template>
<script>
document.addEventListener('DOMContentLoaded', function() {
    const schemaList = document.getElementById('sub-asset-schema-list');
    const addTypeBtn = document.getElementById('add-sub-asset-type-btn');
    const jsonField = document.getElementById('sub-asset-schema-json');
    const typeTemplate = document.getElementById('sub-asset-type-template');
    const propTemplate = document.getElementById('sub-asset-property-template');

    // Generate a short random suffix for key uniqueness
    function randomSuffix() {
        return Math.random().toString(36).substring(2, 6);
    }

    // Parse initial schema from the hidden field
    let schema = {};
    try {
        schema = JSON.parse(jsonField.value || '{}');
    } catch (e) {
        console.error('Failed to parse sub-asset schema:', e);
        schema = {};
    }

    // Render existing sub-asset types — pass the stable key so it is preserved on rename
    Object.entries(schema).forEach(([key, def]) => {
        addSubAssetTypeEntry(key, def.label, def.label_plural, def.description, def.property_schema || []);
    });

    // Add new sub-asset type button handler
    addTypeBtn.addEventListener('click', function() {
        addSubAssetTypeEntry('', '', '', '', []);
        updateJsonField();
    });

    function addSubAssetTypeEntry(existingKey, label, labelPlural, description, properties) {
        const entry = typeTemplate.content.cloneNode(true);
        const labelInput = entry.querySelector('.sub-asset-label');
        const labelPluralInput = entry.querySelector('.sub-asset-label-plural');
        const descInput = entry.querySelector('.sub-asset-description');
        const propertiesList = entry.querySelector('.sub-asset-properties-list');
        const addPropBtn = entry.querySelector('.add-sub-asset-property-btn');
        const removeBtn = entry.querySelector('.remove-sub-asset-type-btn');
        const titleEl = entry.querySelector('.sub-asset-type-title');
        const entryDiv = entry.querySelector('.sub-asset-type-entry');

        labelInput.value = label || '';
        labelPluralInput.value = labelPlural || '';
        descInput.value = description || '';

        // Store the stable key on the DOM element so it survives label renames.
        // New entries get a random key immediately to avoid locking a key based on
        // a partial label (updateJsonField fires on every keystroke).
        entryDiv.dataset.stableKey = existingKey || ('type_' + randomSuffix() + randomSuffix());

        // Update title dynamically
        function updateTitle() {
            titleEl.textContent = labelInput.value || 'New Sub-Asset Type';
        }

        // Add existing properties — pass the stable key for each property
        properties.forEach(prop => addPropertyRow(propertiesList, prop.label || '', prop.key || ''));

        // Event listeners
        labelInput.addEventListener('input', function() {
            updateTitle();
            updateJsonField();
        });
        labelPluralInput.addEventListener('input', updateJsonField);
        descInput.addEventListener('input', updateJsonField);

        addPropBtn.addEventListener('click', function() {
            addPropertyRow(propertiesList, '', '');
            updateJsonField();
        });

        removeBtn.addEventListener('click', function() {
            this.closest('.sub-asset-type-entry').remove();
            updateJsonField();
        });

        schemaList.appendChild(entry);
        updateTitle();
    }

    function addPropertyRow(container, label, existingKey) {
        const row = propTemplate.content.cloneNode(true);
        const labelInput = row.querySelector('.sub-asset-prop-label');
        const removeBtn = row.querySelector('.remove-sub-asset-property-btn');
        const rowDiv = row.querySelector('.sub-asset-property');

        labelInput.value = label || '';

        // Store the stable key on the DOM element so it survives label renames.
        // New rows get a random key immediately to avoid locking a key based on
        // a partial label (updateJsonField fires on every keystroke).
        rowDiv.dataset.stableKey = existingKey || ('prop_' + randomSuffix() + randomSuffix());

        labelInput.addEventListener('input', updateJsonField);

        removeBtn.addEventListener('click', function() {
            this.closest('.sub-asset-property').remove();
            updateJsonField();
        });

        container.appendChild(row);
    }

    function updateJsonField() {
        const entries = schemaList.querySelectorAll('.sub-asset-type-entry');
        const newSchema = {};
        const usedTypeKeys = new Set();

        entries.forEach(entry => {
            const label = entry.querySelector('.sub-asset-label').value.trim();
            const labelPlural = entry.querySelector('.sub-asset-label-plural').value.trim();
            const description = entry.querySelector('.sub-asset-description').value.trim();

            if (label) {
                const key = entry.dataset.stableKey;
                usedTypeKeys.add(key);

                const propertyRows = entry.querySelectorAll('.sub-asset-property');
                const propertySchema = [];
                const usedPropKeys = new Set();

                propertyRows.forEach(row => {
                    const propLabel = row.querySelector('.sub-asset-prop-label').value.trim();
                    if (propLabel) {
                        const propKey = row.dataset.stableKey;
                        usedPropKeys.add(propKey);

                        propertySchema.push({
                            key: propKey,
                            label: propLabel
                        });
                    }
                });

                newSchema[key] = {
                    label: label,
                    label_plural: labelPlural || label + 's',
                    description: description,
                    property_schema: propertySchema
                };
            }
        });

        jsonField.value = JSON.stringify(newSchema);
    }

    // Initial update to sync
    updateJsonField();
});
</script>
"""
)


def _property_schema_editor(form_obj: Any) -> Node:
    """Port of ``core/campaign/includes/property_schema_editor.html``."""
    field = form_obj["property_schema_json"]
    return fragment[
        div[
            label(class_="form-label")[
                "Properties",
                i(
                    class_="bi-info-circle text-secondary",
                    data_bs_toggle="tooltip",
                    data_bs_title="Define properties that assets of this type can have (e.g., Boon, Income, Location)",
                ),
            ],
            small(class_="form-text text-secondary d-block mb-2")[
                "Define the properties that can be set on assets of this type."
            ],
            div(id="property-schema-list", class_="vstack gap-2 mb-2")[
                raw("<!-- Property rows will be added here by JavaScript -->")
            ],
            button(
                type="button",
                id="add-property-btn",
                class_="btn btn-outline-secondary btn-sm",
            )[i(class_="bi-plus-lg"), " Add Property"],
            field,
            div(class_="invalid-feedback d-block")[field.errors]
            if field.errors
            else None,
        ],
        _PROPERTY_EDITOR_STATIC,
    ]


def _sub_asset_schema_editor(form_obj: Any) -> Node:
    """Port of ``core/campaign/includes/sub_asset_schema_editor.html``."""
    field = form_obj["sub_asset_schema_json"]
    return fragment[
        div(class_="mt-4 border-top pt-4")[
            label(class_="form-label")[
                "Sub-Asset Types",
                i(
                    class_="bi-info-circle text-secondary",
                    data_bs_toggle="tooltip",
                    data_bs_title="Define types of sub-assets that can be added to assets of this type (e.g., Structures for Settlements)",
                ),
            ],
            small(class_="form-text text-secondary d-block mb-2")[
                "Define sub-assets that can be added to assets of this type. Each sub-asset type can have its own properties."
            ],
            div(id="sub-asset-schema-list", class_="vstack gap-3 mb-2")[
                raw("<!-- Sub-asset type entries will be added here by JavaScript -->")
            ],
            button(
                type="button",
                id="add-sub-asset-type-btn",
                class_="btn btn-outline-secondary btn-sm",
            )[i(class_="bi-plus-lg"), " Add Sub-Asset Type"],
            field,
            div(class_="invalid-feedback d-block")[field.errors]
            if field.errors
            else None,
        ],
        _SUB_ASSET_EDITOR_STATIC,
    ]


@register_page("core/campaign/campaign_asset_type_edit.html")
def campaign_asset_type_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    asset_type = context["asset_type"]
    request = context["request"]

    body = form(
        action=reverse(
            "core:campaign-asset-type-edit", args=[campaign.id, asset_type.id]
        ),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        FormField(form_obj["name_singular"]),
        FormField(form_obj["name_plural"]),
        FormField(form_obj["description"]),
        _property_schema_editor(form_obj),
        _sub_asset_schema_editor(form_obj),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")["Update Asset Type"],
            a(
                href=reverse("core:campaign-assets", args=[campaign.id]),
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(
            context,
            url=reverse("core:campaign-assets", args=[campaign.id]),
            text="Back to Assets",
        ),
        PageShell(
            h1(class_="h3")["Edit Asset Type"],
            h2(class_="h5 text-secondary")[asset_type.name_singular],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Edit Asset Type - {asset_type.name_singular}", content=content)
