import { useEffect, useId, useRef, useState } from "react";
import { fieldErrors } from "../../http/command";
import {
    Button,
    CheckboxCard,
    Dialog,
    EquipmentChoices,
    Field,
    FieldDescription,
    FieldErrors,
    FormActions,
    NativeSelect,
    RadioCard,
    RadioCards,
    Tally,
    useWorkflowForm,
} from "../../ui";
import {
    blankValues,
    type EquipDraft,
    type EquipOutcome,
    type EquipProps,
} from "./types";
import { isEquipOutcome, isEquipPage } from "./validate";

function keys(raw: string): string[] {
    try {
        const value: unknown = JSON.parse(raw);
        return Array.isArray(value) &&
            value.every((key) => typeof key === "string")
            ? value
            : [];
    } catch {
        return [];
    }
}
function replacementPrice(
    dialog: NonNullable<EquipDraft["dialog"]>,
    selected: string[],
) {
    const preview = dialog.pricePreview;
    if (!preview) return null;
    const named = dialog.choices
        .flatMap((group) => group.options)
        .filter((option) => selected.includes(option.key))
        .map((option) => option.setKey);
    const remaining = [...named];
    const taken: Array<{ setKey: string; price: number }> = [];
    for (const group of preview.resolution) {
        let current = group.options.filter((option) =>
            remaining.includes(option.setKey),
        );
        for (const option of current) {
            const index = remaining.indexOf(option.setKey);
            if (index < 0) return null;
            remaining.splice(index, 1);
        }
        if (group.choose !== "any" && current.length > 1) return null;
        if (!current.length && group.choose === "one")
            current = group.options.slice(0, 1);
        taken.push(...current);
    }
    if (remaining.length) return null;
    const sets = new Set(taken.map((option) => option.setKey));
    if (
        sets.size === preview.held.length &&
        preview.held.every((key) => sets.has(key))
    )
        return 0;
    const refunded = [
        ...new Map(
            preview.refunds
                .filter((group) => !sets.has(group.setKey))
                .flatMap((group) =>
                    group.entries.map(
                        (entry) => [entry.key, entry.paid] as const,
                    ),
                ),
        ).values(),
    ].reduce((sum, paid) => sum + paid, 0);
    return (
        taken.reduce((sum, option) => sum + option.price, 0) -
        preview.before -
        refunded
    );
}
export function Command({
    page,
    draft,
    onSettled,
    onPage,
    onDismiss,
    onFrozen,
    onQueueBlocked,
    queueNotice,
}: {
    page: EquipProps;
    draft: EquipDraft | null;
    onSettled: (outcome: EquipOutcome) => void;
    onPage: (page: EquipProps) => void;
    onDismiss: () => void;
    onFrozen: (frozen: boolean) => void;
    onQueueBlocked: () => void;
    queueNotice: string;
}) {
    const element = useRef<HTMLFormElement>(null);
    const started = useRef(false);
    const resolved = useRef<EquipOutcome | null>(null);
    const currentValues = useRef(draft?.values ?? blankValues(page));
    const id = useId();
    const [destination, setDestination] = useState<"model" | "stash" | null>(
        null,
    );
    const form = useWorkflowForm({
        values: draft?.values ?? blankValues(page),
        errors: {},
        commandHref: page.commandHref,
        csrfToken: page.csrfToken,
        recoveryKey: page.recoveryKey,
        optionalRecoveryFields: ["display_details", "change", "dismissed"],
        interpret(status, data) {
            if (status === 200 && isEquipOutcome(data)) {
                if (data.requestKey !== currentValues.current.request_key)
                    return null;
                if (data.confirmation) {
                    const carry = new URLSearchParams(data.confirmation.carry);
                    if (
                        !carry.get("request_key") ||
                        carry.get("request_key") === data.requestKey
                    )
                        return null;
                    const revised = new Set([
                        "request_key",
                        "rate",
                        "confirmed",
                        "personal_activity",
                        "display_name",
                        "display_details",
                        "change",
                    ]);
                    if (
                        Object.entries(currentValues.current).some(
                            ([name, value]) =>
                                !revised.has(name) && carry.get(name) !== value,
                        )
                    )
                        return null;
                }
                resolved.current = data;
                return { kind: "completed" };
            }
            if (
                (status === 409 || status === 422) &&
                fieldErrors(data.errors)
            ) {
                if (data.page !== undefined) {
                    if (!isEquipPage(data.page)) return null;
                    onPage(data.page);
                }
                return { kind: "invalid", errors: data.errors };
            }
            return null;
        },
        onComplete() {
            if (resolved.current) onSettled(resolved.current);
        },
    });
    const { values, setValues, frozen, pending, uncertain } = form;
    useEffect(() => {
        if (destination && values.to === destination && !frozen) {
            element.current?.requestSubmit();
            setDestination(null);
        }
    }, [destination, values.to, frozen]);
    currentValues.current = values;
    useEffect(() => {
        onFrozen(frozen);
    }, [frozen, onFrozen]);
    useEffect(() => {
        if (values.action === "tally" && (uncertain || form.hasErrors))
            onQueueBlocked();
    }, [values.action, uncertain, form.hasErrors, onQueueBlocked]);
    useEffect(() => {
        if (draft?.auto && !started.current && !uncertain) {
            started.current = true;
            element.current?.requestSubmit();
        }
    }, [draft?.auto, uncertain]);
    if (!values.action) return null;
    const matchesDraft = draft?.values.request_key === values.request_key;
    const dialog = matchesDraft ? draft?.dialog : null;
    const question = matchesDraft ? draft?.question : null;
    const recovered = !matchesDraft || (uncertain && !dialog && !question);
    const actionLabel =
        {
            buy: "Buy",
            sell: "Sell",
            refund: "Refund",
            remove: "Remove",
            reassign: "Move",
            rechoose: "Change options",
            accessorise: "Add an accessory",
            tally: "Change counter",
        }[values.action] || "Change";
    const selection = keys(values.selection);
    const difference =
        dialog?.kind === "rechoose"
            ? replacementPrice(dialog, selection)
            : null;
    const label =
        question?.confirm_label ||
        dialog?.submit_label ||
        (values.action === "buy" ? "Buy" : "Save");
    const canSubmit = uncertain || !dialog || !!dialog.submit_label;
    const change = (name: keyof typeof values, value: string) =>
        setValues((previous) => ({ ...previous, [name]: value }));
    const hasStashDestination =
        dialog?.kind === "reassign" &&
        !!page.model &&
        !!dialog.models.length &&
        !dialog.weapons?.length;
    const submitTo = (to: "model" | "stash") => {
        change("to", to);
        setDestination(to);
    };
    let details = keys(values.display_details);
    if (dialog) {
        details = [dialog.lead];
        if (dialog.kind === "rechoose")
            details.push(
                ...dialog.choices
                    .flatMap((group) => group.options)
                    .filter((option) => selection.includes(option.key))
                    .map((option) => option.name),
            );
        if (dialog.kind === "accessorise") {
            const accessory = dialog.accessories?.find(
                (accessory) => accessory.pk === values.accessory,
            );
            if (accessory)
                details.push(`${accessory.name} — ${accessory.price}¢`);
        }
        if (values.to === "weapon")
            details.push(
                `To: ${dialog.weapons?.find((weapon) => weapon.pk === values.weapon)?.label || "selected weapon"}`,
            );
        if (values.to === "model")
            details.push(
                `To: ${dialog.models.find((model) => model.key === values.miniature)?.name || "selected model"}`,
            );
        if (dialog.kind === "reassign" && values.to === "stash")
            details.push("To: stash");
    }
    if (
        values.action === "tally" &&
        matchesDraft &&
        !uncertain &&
        !form.hasErrors
    )
        return (
            <form
                ref={element}
                onSubmit={form.save}
                data-equip-command
                data-busy="off"
            >
                <input
                    type="hidden"
                    name="csrfmiddlewaretoken"
                    value={page.csrfToken}
                />
                {Object.entries(values).map(([name, value]) => (
                    <input key={name} type="hidden" name={name} value={value} />
                ))}
                <p role="status" className="text-sm text-muted">
                    Saving counter change…
                </p>
            </form>
        );
    return (
        <Dialog
            title={
                uncertain
                    ? `Confirm earlier change: ${values.display_name || "equipment"}`
                    : recovered
                      ? `Review earlier change: ${values.display_name || "equipment"}`
                      : question?.title ||
                        dialog?.title ||
                        `${values.action === "buy" ? "Buy" : "Change"} ${values.display_name}`
            }
            lead={question?.lead}
            onSubmit={(event) => {
                if (hasStashDestination && !uncertain && !destination) {
                    event.preventDefault();
                    submitTo("model");
                } else {
                    void form.save(event);
                }
            }}
            pending={frozen}
            onDismiss={() => {
                if (!frozen) onDismiss();
            }}
            formProps={{
                ref: element,
                action: page.commandHref,
                method: "post",
            }}
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={page.csrfToken}
            />
            {Object.entries(values).map(([name, value]) => (
                <input
                    key={name}
                    type="hidden"
                    name={name}
                    value={
                        name === "display_details"
                            ? JSON.stringify(details)
                            : value
                    }
                />
            ))}
            {form.hasErrors && (
                <div
                    ref={form.summary}
                    role="alert"
                    tabIndex={-1}
                    aria-label="Equipment errors"
                >
                    <FieldErrors
                        errors={[
                            ...Object.values(form.errors).flat(),
                            ...(form.notice ? [form.notice] : []),
                        ]}
                    />
                </div>
            )}
            {queueNotice && <p role="alert">{queueNotice}</p>}
            <fieldset disabled={frozen} className="min-w-0 space-y-4">
                {recovered && (
                    <>
                        <p>
                            {uncertain
                                ? "Retry the same change to confirm its result."
                                : "Review the earlier change before retrying it. Cancel to discard this draft."}
                        </p>
                        <Tally
                            facts={[
                                {
                                    label: "Action",
                                    value: actionLabel,
                                    sub: "",
                                    ruled: false,
                                    strong: false,
                                },
                                {
                                    label:
                                        values.action === "tally"
                                            ? "Counter"
                                            : "Equipment",
                                    value: values.display_name,
                                    sub: "",
                                    ruled: false,
                                    strong: true,
                                },
                                ...(values.action === "buy"
                                    ? [
                                          {
                                              label: "Equipment payment",
                                              value:
                                                  values.paid === ""
                                                      ? "Current quote"
                                                      : `${values.paid}¢`,
                                              sub: "",
                                              ruled: false,
                                              strong: false,
                                          },
                                          {
                                              label: "Rating",
                                              value:
                                                  values.rate === "paid"
                                                      ? "Match payment"
                                                      : "Full rating",
                                              sub: "",
                                              ruled: false,
                                              strong: false,
                                          },
                                      ]
                                    : []),
                                ...(values.action === "sell"
                                    ? [
                                          {
                                              label: "Accessories",
                                              value:
                                                  values.accessories === "sell"
                                                      ? "Sell with the equipment"
                                                      : "Keep in the stash",
                                              sub: "",
                                              ruled: false,
                                              strong: false,
                                          },
                                      ]
                                    : []),
                            ]}
                        />
                        {details.length > 0 && (
                            <ul className="list-disc space-y-1 pl-5 text-sm">
                                {details.map((detail, index) => (
                                    <li key={index}>{detail}</li>
                                ))}
                            </ul>
                        )}
                    </>
                )}

                {question && (
                    <>
                        <h3 className="font-semibold">{question.heading}</h3>
                        <p>{question.body}</p>
                        {question.aside && (
                            <p>
                                <strong>{question.aside.lead}</strong>{" "}
                                {question.aside.rest}
                            </p>
                        )}
                        <Tally facts={question.facts} />
                        {question.checkbox && (
                            <>
                                <CheckboxCard
                                    label={question.checkbox.label}
                                    checked={
                                        values.rate === question.checkbox.value
                                    }
                                    checkboxDescribedBy={id}
                                    onCheckedChange={(checked) =>
                                        change(
                                            "rate",
                                            checked
                                                ? question.checkbox!.value
                                                : "",
                                        )
                                    }
                                />
                                <FieldDescription id={id}>
                                    {question.checkbox.description}
                                </FieldDescription>
                            </>
                        )}
                    </>
                )}
                {dialog && (
                    <>
                        <p>{dialog.lead}</p>
                        {dialog.kind === "rechoose" && (
                            <>
                                <EquipmentChoices
                                    groups={dialog.choices}
                                    selected={selection}
                                    label={dialog.name}
                                    onChange={(selected) =>
                                        change(
                                            "selection",
                                            JSON.stringify(selected),
                                        )
                                    }
                                />
                                <p role="status">
                                    {difference === null
                                        ? "Price preview unavailable."
                                        : difference > 0
                                          ? `Options charge ${difference}¢`
                                          : difference < 0
                                            ? `Options refund ${-difference}¢`
                                            : "No price change"}
                                </p>
                            </>
                        )}
                        {dialog.kind === "sell" && dialog.keepable && (
                            <RadioCards
                                legend={`Accessories: ${dialog.keepable}`}
                            >
                                <RadioCard
                                    name="ui-accessories"
                                    value="stash"
                                    label={dialog.keep_label!}
                                    description={dialog.keep_detail}
                                    checked={values.accessories === "stash"}
                                    onChange={() =>
                                        change("accessories", "stash")
                                    }
                                />
                                <RadioCard
                                    name="ui-accessories"
                                    value="sell"
                                    label={dialog.sell_all_label!}
                                    description={dialog.sell_all_detail}
                                    checked={values.accessories === "sell"}
                                    onChange={() =>
                                        change("accessories", "sell")
                                    }
                                />
                            </RadioCards>
                        )}
                        {dialog.kind === "accessorise" &&
                            (dialog.accessories?.length ? (
                                <Field
                                    label="Accessory"
                                    htmlFor={`${id}-accessory`}
                                >
                                    <NativeSelect
                                        id={`${id}-accessory`}
                                        aria-label="Accessory"
                                        value={values.accessory}
                                        onChange={(event) =>
                                            change(
                                                "accessory",
                                                event.target.value,
                                            )
                                        }
                                    >
                                        {dialog.accessories.map((accessory) => (
                                            <option
                                                key={accessory.pk}
                                                value={accessory.pk}
                                            >
                                                {accessory.name} —{" "}
                                                {accessory.price}¢
                                            </option>
                                        ))}
                                    </NativeSelect>
                                </Field>
                            ) : null)}
                        {(dialog.kind === "reassign" ||
                            dialog.kind === "fit") &&
                            (dialog.weapons?.length ? (
                                <Field label="Weapon" htmlFor={`${id}-weapon`}>
                                    <NativeSelect
                                        id={`${id}-weapon`}
                                        aria-label="Weapon"
                                        value={values.weapon}
                                        onChange={(event) =>
                                            change("weapon", event.target.value)
                                        }
                                    >
                                        {dialog.weapons.map((weapon) => (
                                            <option
                                                key={weapon.pk}
                                                value={weapon.pk}
                                            >
                                                {weapon.label}
                                            </option>
                                        ))}
                                    </NativeSelect>
                                </Field>
                            ) : dialog.kind === "fit" ? null : dialog.models
                                  .length ? (
                                <Field label="To" htmlFor={`${id}-model`}>
                                    <NativeSelect
                                        id={`${id}-model`}
                                        aria-label="To"
                                        value={values.miniature}
                                        onChange={(event) =>
                                            change(
                                                "miniature",
                                                event.target.value,
                                            )
                                        }
                                    >
                                        {dialog.models.map((model) => (
                                            <option
                                                key={model.key}
                                                value={model.key}
                                            >
                                                {model.name}
                                            </option>
                                        ))}
                                    </NativeSelect>
                                </Field>
                            ) : (
                                <p>
                                    There is no model to move this equipment to.
                                </p>
                            ))}
                    </>
                )}
                {!recovered && !question && !dialog && (
                    <p>
                        {pending
                            ? "Saving…"
                            : "Retry this change to confirm its result."}
                    </p>
                )}
            </fieldset>
            <FormActions>
                {hasStashDestination && (
                    <Button disabled={frozen} onClick={() => submitTo("stash")}>
                        To the stash
                    </Button>
                )}
                {canSubmit && (
                    <Button
                        type="submit"
                        variant={
                            dialog?.submit_variant === "danger" ||
                            (recovered &&
                                ["sell", "refund", "remove"].includes(
                                    values.action,
                                ))
                                ? "danger"
                                : "success"
                        }
                        disabled={pending}
                    >
                        {pending
                            ? "Saving…"
                            : uncertain
                              ? "Retry change"
                              : recovered
                                ? "Retry earlier change"
                                : label}
                    </Button>
                )}
                <Button variant="ghost" disabled={frozen} onClick={onDismiss}>
                    Cancel
                </Button>
            </FormActions>
            {(uncertain || form.notice) && (
                <div className="flex flex-wrap gap-3">
                    <Button
                        size="sm"
                        disabled={pending}
                        onClick={() => {
                            if (element.current)
                                form.recoverAt(
                                    window.location.href,
                                    element.current,
                                );
                        }}
                    >
                        Reload page
                    </Button>
                    <Button
                        size="sm"
                        disabled={pending}
                        onClick={() => {
                            if (element.current)
                                form.recoverAt(
                                    page.signInHref,
                                    element.current,
                                );
                        }}
                    >
                        Sign in
                    </Button>
                </div>
            )}
        </Dialog>
    );
}
