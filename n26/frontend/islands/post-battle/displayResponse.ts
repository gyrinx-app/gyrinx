import type { ReportDisplay } from "./types";

type Check = (value: unknown) => boolean;
const text: Check = (value) => typeof value === "string";
const number: Check = (value) =>
    typeof value === "number" && Number.isFinite(value);
const boolean: Check = (value) => typeof value === "boolean";
const list =
    (check: Check): Check =>
    (value) =>
        Array.isArray(value) && value.every(check);
const record =
    (checks: Record<string, Check>): Check =>
    (value) =>
        !!value &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.entries(checks).every(([key, check]) =>
            check((value as Record<string, unknown>)[key]),
        );
const strings = (...names: string[]) =>
    Object.fromEntries(names.map((name) => [name, text]));
const numbers = (...names: string[]) =>
    Object.fromEntries(names.map((name) => [name, number]));
const booleans = (...names: string[]) =>
    Object.fromEntries(names.map((name) => [name, boolean]));
const option = record(strings("value", "label"));
const counter = record({
    ...strings(
        "id",
        "name",
        "prefix",
        "listName",
        "entered",
        "minusLabel",
        "plusLabel",
    ),
    ...numbers("before", "base", "after", "fromResults", "limit"),
    editable: boolean,
});
const effect = record({
    ...strings("id", "selected", "label", "name"),
    retainedOption: boolean,
    retainedChoices: list(record({ key: text, selected: list(text) })),
    questions: list(
        record({
            ...strings("key", "label"),
            ...booleans("multiple", "required"),
            selected: list(text),
            options: list(option),
        }),
    ),
});
const model = record({
    ...strings(
        "id",
        "name",
        "prefix",
        "profileName",
        "ownedBy",
        "xp",
        "xpHelp",
        "status",
        "statusLabel",
        "statusColour",
        "statusConflict",
        "finalStatusLabel",
        "finalStatusColour",
        "equipment",
        "equipmentLabel",
        "equipmentDisposition",
        "addEffectLabel",
        "note",
        "noteLabel",
        "noteHelp",
    ),
    ...numbers("xpBefore", "noteLimit"),
    ...booleans(
        "participated",
        "xpAvailable",
        "statusChanges",
        "equipmentApplies",
        "equipmentChanged",
        "counterEffects",
    ),
    statusOptions: list(option),
    equipmentNames: list(text),
    equipmentExclusions: list(text),
    effectGroups: list(record({ label: text, options: list(option) })),
    effects: list(effect),
    counters: list(counter),
    errors: list(text),
});
const display = record({
    ...strings(
        "reportId",
        "title",
        "lead",
        "receiptHref",
        "generation",
        "review",
        "savedAt",
    ),
    ...booleans(
        "participationConfirmed",
        "applied",
        "correcting",
        "showErrors",
    ),
    revision: number,
    breadcrumbs: list(
        record({
            label: text,
            href: (value) => value === undefined || text(value),
        }),
    ),
    toolbar: record(
        strings(
            "countOne",
            "countMany",
            "plusOne",
            "plusMany",
            "minusOne",
            "minusMany",
        ),
    ),
    models: list(model),
    mission: record({
        creditLines: list(
            record({
                ...strings("id", "amount", "reason", "removeLabel"),
                amountErrors: list(text),
                reasonErrors: list(text),
            }),
        ),
        ...booleans("canAddLine", "counterEffects"),
        totalText: text,
        counters: list(counter),
    }),
    territory: (value) =>
        value === null ||
        record({
            ...strings("name", "heading", "outcome", "currentHolder", "note"),
            applied: boolean,
        })(value),
    preview: record({
        rows: list(record(strings("id", "label", "value"))),
        models: list(
            record({ ...strings("id", "name", "error"), lines: list(text) }),
        ),
    }),
    errors: list(text),
});

/** Validate the complete renderer input before releasing a retained command. */
export function displayResponse(value: unknown): value is ReportDisplay {
    return display(value);
}
