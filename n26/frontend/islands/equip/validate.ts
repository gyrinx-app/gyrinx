import { isEquipmentModel } from "../../ui";
import type { EquipOutcome, EquipProps, EquipQuestion } from "./types";
const object = (value: unknown): value is Record<string, unknown> =>
    !!value && typeof value === "object" && !Array.isArray(value);
const strings = (value: unknown): value is string[] =>
    Array.isArray(value) && value.every((item) => typeof item === "string");
const number = (value: unknown): value is number =>
    typeof value === "number" && Number.isFinite(value);
function svg(value: unknown, depth = 0): boolean {
    return (
        depth < 20 &&
        object(value) &&
        typeof value.tag === "string" &&
        object(value.props) &&
        Object.values(value.props).every(
            (value) => typeof value === "string",
        ) &&
        (value.children === undefined ||
            (Array.isArray(value.children) &&
                value.children.every(
                    (child) =>
                        typeof child === "string" || svg(child, depth + 1),
                )))
    );
}
function sameOrigin(value: string) {
    try {
        return (
            new URL(value, window.location.href).origin ===
            window.location.origin
        );
    } catch {
        return false;
    }
}
function choices(value: unknown) {
    return (
        Array.isArray(value) &&
        value.every(
            (group) =>
                object(group) &&
                ["one", "any", "one-or-none"].includes(String(group.choose)) &&
                Array.isArray(group.options) &&
                group.options.every(
                    (option) =>
                        object(option) &&
                        typeof option.key === "string" &&
                        typeof option.name === "string" &&
                        typeof option.setKey === "string" &&
                        number(option.price) &&
                        number(option.surcharge) &&
                        typeof option.checked === "boolean",
                ),
        )
    );
}
function actions(value: unknown) {
    return (
        Array.isArray(value) &&
        value.every(
            (action) =>
                object(action) &&
                [action.label, action.target, action.tone].every(
                    (value) => typeof value === "string",
                ),
        )
    );
}
function part(value: unknown): boolean {
    return (
        object(value) &&
        [value.id, value.name].every((text) => typeof text === "string") &&
        number(value.rating) &&
        actions(value.actions)
    );
}
function purchase(value: unknown): boolean {
    return (
        object(value) &&
        [value.key, value.name].every((text) => typeof text === "string") &&
        number(value.price) &&
        (value.tradePoints === null || number(value.tradePoints)) &&
        typeof value.exclusive === "boolean" &&
        Array.isArray(value.notes) &&
        value.notes.every(
            (note) =>
                object(note) &&
                typeof note.text === "string" &&
                typeof note.level === "string",
        )
    );
}
function entry(value: unknown): boolean {
    return (
        object(value) &&
        [value.key, value.name].every((text) => typeof text === "string") &&
        number(value.basePrice) &&
        number(value.count) &&
        typeof value.expanded === "boolean" &&
        (value.purchase === null ||
            (purchase(value.purchase) &&
                object(value.purchase) &&
                choices(value.purchase.choices) &&
                Array.isArray(value.purchase.parts) &&
                value.purchase.parts.every(purchase))) &&
        Array.isArray(value.copies) &&
        value.copies.every(
            (copy) =>
                part(copy) &&
                object(copy) &&
                strings(copy.chosen) &&
                (copy.accessorise === null || actions([copy.accessorise])) &&
                Array.isArray(copy.parts) &&
                copy.parts.every(part),
        )
    );
}
export function isEquipPage(value: unknown): value is EquipProps {
    if (
        !object(value) ||
        (value.model !== undefined &&
            value.model !== null &&
            !isEquipmentModel(value.model))
    )
        return false;
    const texts = [
        "gangName",
        "gangHref",
        "scope",
        "scopeLabel",
        "section",
        "owned",
        "listingHref",
        "requestKey",
        "csrfToken",
        "action",
        "displayHref",
        "commandHref",
        "recoveryKey",
        "signInHref",
        "tradePointsHref",
    ];
    if (
        !texts.every((name) => typeof value[name] === "string") ||
        !object(value.owner) ||
        !object(value.figures) ||
        !Array.isArray(value.figures.items) ||
        !object(value.figures.roster)
    )
        return false;
    if (
        typeof value.owner.name !== "string" ||
        (value.owner.href !== undefined && typeof value.owner.href !== "string")
    )
        return false;
    if (
        value.owner.badge !== null &&
        value.owner.badge !== undefined &&
        (!object(value.owner.badge) ||
            typeof value.owner.badge.label !== "string" ||
            !svg(value.owner.badge.svg))
    )
        return false;
    if (
        ![
            value.listingHref,
            value.action,
            value.commandHref,
            value.displayHref,
            value.signInHref,
        ].every((url) => typeof url === "string" && sameOrigin(url))
    )
        return false;
    if (
        !value.figures.items.every(
            (item) =>
                object(item) &&
                [
                    item.short,
                    item.label,
                    item.value,
                    item.absent,
                    item.href,
                ].every((text) => typeof text === "string"),
        )
    )
        return false;
    const roster = value.figures.roster;
    if (
        !number(roster.count) ||
        !number(roster.rating) ||
        !Array.isArray(roster.groups) ||
        !roster.groups.every(
            (group) =>
                object(group) &&
                typeof group.profile === "string" &&
                typeof group.category === "string" &&
                number(group.count),
        ) ||
        !Array.isArray(roster.models) ||
        !roster.models.every(
            (model) =>
                object(model) &&
                typeof model.name === "string" &&
                number(model.rating),
        )
    )
        return false;
    if (
        !strings(value.categories) ||
        !strings(value.categoryOptions) ||
        ![value.priceFloor, value.priceCeiling, value.tradePointsCeiling].every(
            number,
        ) ||
        ![
            value.hasTradePoints,
            value.postIsShut,
            value.foundingBlocksVisit,
            value.visitingTradingPost,
        ].every((flag) => typeof flag === "boolean")
    )
        return false;
    if (
        !Array.isArray(value.scopeTabs) ||
        !value.scopeTabs.every(
            (tab) =>
                object(tab) &&
                [tab.key, tab.label, tab.title, tab.href].every(
                    (text) => typeof text === "string",
                ) &&
                typeof tab.current === "boolean",
        )
    )
        return false;
    if (
        !Array.isArray(value.messages) ||
        !value.messages.every(
            (message) =>
                object(message) &&
                typeof message.text === "string" &&
                ["info", "success", "warning", "error"].includes(
                    String(message.tone),
                ),
        )
    )
        return false;
    if (
        !Array.isArray(value.sections) ||
        !value.sections.every(
            (section) =>
                object(section) &&
                typeof section.name === "string" &&
                Array.isArray(section.categories) &&
                section.categories.every(
                    (category) =>
                        object(category) &&
                        typeof category.name === "string" &&
                        Array.isArray(category.entries) &&
                        category.entries.every(entry),
                ),
        )
    )
        return false;
    if (value.dialog !== null) {
        const dialog = value.dialog;
        if (
            !object(dialog) ||
            ![
                dialog.assignment,
                dialog.kind,
                dialog.title,
                dialog.lead,
                dialog.name,
                dialog.cancel_url,
                dialog.submit_label,
                dialog.submit_variant,
                dialog.remove_note,
            ].every((text) => typeof text === "string") ||
            !choices(dialog.choices) ||
            !Array.isArray(dialog.models) ||
            !dialog.models.every(
                (model) =>
                    object(model) &&
                    typeof model.key === "string" &&
                    typeof model.name === "string",
            )
        )
            return false;
        if (
            dialog.weapons !== undefined &&
            (!Array.isArray(dialog.weapons) ||
                !dialog.weapons.every(
                    (weapon) =>
                        object(weapon) &&
                        typeof weapon.pk === "string" &&
                        typeof weapon.label === "string",
                ))
        )
            return false;
        if (
            dialog.accessories !== undefined &&
            (!Array.isArray(dialog.accessories) ||
                !dialog.accessories.every(
                    (accessory) =>
                        object(accessory) &&
                        typeof accessory.pk === "string" &&
                        typeof accessory.name === "string" &&
                        number(accessory.price),
                ))
        )
            return false;
        if (dialog.pricePreview !== null) {
            const preview = dialog.pricePreview;
            if (
                !object(preview) ||
                !number(preview.before) ||
                !strings(preview.held) ||
                !Array.isArray(preview.refunds) ||
                !preview.refunds.every(
                    (group) =>
                        object(group) &&
                        typeof group.setKey === "string" &&
                        Array.isArray(group.entries) &&
                        group.entries.every(
                            (entry) =>
                                object(entry) &&
                                typeof entry.key === "string" &&
                                number(entry.paid),
                        ),
                ) ||
                !Array.isArray(preview.resolution) ||
                !preview.resolution.every(
                    (group) =>
                        object(group) &&
                        typeof group.choose === "string" &&
                        Array.isArray(group.options) &&
                        group.options.every(
                            (option) =>
                                object(option) &&
                                typeof option.setKey === "string" &&
                                number(option.price),
                        ),
                )
            )
                return false;
        }
    }
    return true;
}
function isQuestion(value: unknown): value is EquipQuestion {
    return (
        object(value) &&
        [
            value.title,
            value.lead,
            value.heading,
            value.body,
            value.confirm_label,
            value.confirm_field,
            value.confirm_value,
        ].every((text) => typeof text === "string") &&
        Array.isArray(value.carry) &&
        value.carry.every((field) => strings(field) && field.length === 2) &&
        Array.isArray(value.facts) &&
        value.facts.every(
            (fact) =>
                object(fact) &&
                [fact.label, fact.value, fact.sub].every(
                    (text) => typeof text === "string",
                ) &&
                typeof fact.ruled === "boolean" &&
                typeof fact.strong === "boolean",
        ) &&
        (value.aside === null ||
            (object(value.aside) &&
                typeof value.aside.lead === "string" &&
                typeof value.aside.rest === "string")) &&
        (value.checkbox === null ||
            (object(value.checkbox) &&
                [
                    value.checkbox.name,
                    value.checkbox.value,
                    value.checkbox.label,
                    value.checkbox.description,
                ].every((text) => typeof text === "string") &&
                typeof value.checkbox.checked === "boolean"))
    );
}
export function isEquipOutcome(value: unknown): value is EquipOutcome {
    return (
        object(value) &&
        typeof value.requestKey === "string" &&
        isEquipPage(value.page) &&
        ((value.outcome === "completed" && value.confirmation === null) ||
            (value.outcome === "confirmation" &&
                isQuestion(value.confirmation)))
    );
}
