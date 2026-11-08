import { useEffect, useId, useState } from "react";
import { fieldErrors } from "../../http/command";
import {
    Button,
    CheckboxCard,
    Dialog,
    Field,
    FieldDescription,
    FieldErrors,
    FormActions,
    Input,
    useWorkflowForm,
    type GangFiguresData,
} from "../../ui";
import type { HireProps } from "./types";

function record(value: unknown): value is Record<string, unknown> {
    return !!value && typeof value === "object" && !Array.isArray(value);
}
function figures(value: unknown): value is GangFiguresData {
    if (!record(value) || !Array.isArray(value.items) || !record(value.roster))
        return false;
    const roster = value.roster;
    return (
        value.items.every(
            (item) =>
                record(item) &&
                [
                    item.short,
                    item.label,
                    item.value,
                    item.absent,
                    item.href,
                ].every((text) => typeof text === "string"),
        ) &&
        typeof roster.count === "number" &&
        Number.isFinite(roster.count) &&
        typeof roster.rating === "number" &&
        Number.isFinite(roster.rating) &&
        Array.isArray(roster.groups) &&
        roster.groups.every(
            (group) =>
                record(group) &&
                typeof group.profile === "string" &&
                typeof group.category === "string" &&
                typeof group.count === "number",
        ) &&
        Array.isArray(roster.models) &&
        roster.models.every(
            (model) =>
                record(model) &&
                typeof model.name === "string" &&
                typeof model.rating === "number",
        )
    );
}
function names(raw: string): string[] {
    try {
        const parsed: unknown = JSON.parse(raw);
        return Array.isArray(parsed) &&
            parsed.every((name) => typeof name === "string")
            ? parsed
            : [];
    } catch {
        return [];
    }
}

export function Confirmation(
    props: HireProps & {
        onFigures: (data: GangFiguresData) => void;
        onNavigate?: (url: string) => void;
        onReload?: () => void;
    },
) {
    const nameId = useId();
    const paidId = useId();
    const rateHelpId = useId();
    const form = useWorkflowForm({
        ...props,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string") {
                try {
                    const target = new URL(data.nextUrl, window.location.href);
                    if (target.origin === window.location.origin)
                        return { kind: "saved", nextUrl: data.nextUrl };
                } catch {
                    return null;
                }
            }
            if (
                (status === 409 || status === 422) &&
                fieldErrors(data.errors) &&
                figures(data.figures)
            ) {
                props.onFigures(data.figures);
                return { kind: "invalid", errors: data.errors };
            }
            return null;
        },
    });
    const { values, setValues, errors, pending, uncertain, frozen } = form;
    const [pendingNotice, setPendingNotice] = useState("");
    const notice = form.notice || (pending ? pendingNotice : "");
    useEffect(() => {
        if (!pending) setPendingNotice(form.notice);
    }, [pending, form.notice]);
    const quote = Number.isFinite(Number(values.quoted))
        ? Number(values.quoted)
        : 0;
    const choices = names(values.choice_names);
    const profile = values.profile_name || "model";
    const rawPaid = values.paid.trim();
    const amount = /^-?[0-9]+$/.test(rawPaid) ? Number(rawPaid) : quote;
    const difference =
        rawPaid && amount !== quote
            ? `${amount > quote ? "+" : "−"}${Math.abs(amount - quote)}¢`
            : "";
    const topErrors = Object.entries(errors)
        .filter(([field]) => field !== "name" && field !== "paid")
        .flatMap(([, messages]) => messages);
    if (!props.confirmation && !uncertain && !(notice && values.profile))
        return null;
    const navigate =
        props.onNavigate ?? ((url: string) => window.location.assign(url));
    return (
        <Dialog
            title={
                uncertain
                    ? `Confirm earlier hire: ${profile}`
                    : `Hire ${profile}`
            }
            lead={`${quote}¢${choices.length ? ` — ${choices.join(", ")}` : ""}`}
            onSubmit={form.save}
            pending={pending}
            formProps={{ method: "post", action: props.action }}
            onDismiss={() => {
                if (!frozen) navigate(props.back);
            }}
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={props.csrfToken}
            />
            {Object.entries(values)
                .filter(([field]) => field !== "name" && field !== "paid")
                .map(([field, value]) => (
                    <input
                        key={field}
                        type="hidden"
                        name={field}
                        value={value}
                    />
                ))}
            {(form.hasErrors || notice) && (
                <div
                    ref={form.summary}
                    role="alert"
                    tabIndex={-1}
                    aria-label="Hire errors"
                >
                    <FieldErrors
                        errors={[...topErrors, ...(notice ? [notice] : [])]}
                    />
                    {!topErrors.length && !notice && (
                        <p>Check the highlighted fields.</p>
                    )}
                </div>
            )}
            <fieldset disabled={frozen} className="min-w-0 space-y-4">
                <Field
                    htmlFor={nameId}
                    label="Name"
                    description="Optional — you can name them later."
                    errors={errors.name}
                >
                    <Input
                        id={nameId}
                        name="name"
                        value={values.name}
                        autoComplete="off"
                        autoFocus
                        onChange={(event) =>
                            setValues({ ...values, name: event.target.value })
                        }
                    />
                </Field>
                <Field
                    htmlFor={paidId}
                    label="Price"
                    description={`Leave blank to pay the quoted ${quote}¢. Enter 0 for a free model.`}
                    errors={errors.paid}
                >
                    <Input
                        id={paidId}
                        type="number"
                        name="paid"
                        value={values.paid}
                        min={Math.min(0, quote)}
                        max={100000}
                        step={1}
                        inputMode="numeric"
                        rightAddon={
                            <span className="inline-block w-20 whitespace-nowrap text-right tabular-nums">
                                {difference ? `(${difference})` : "¢"}
                            </span>
                        }
                        onChange={(event) =>
                            setValues({ ...values, paid: event.target.value })
                        }
                    />
                </Field>
                {/* Always post rating mode so an unchecked draft survives recovery. */}
                <CheckboxCard
                    label="Match rating to price"
                    checked={values.rate === "paid"}
                    checkboxDescribedBy={rateHelpId}
                    onCheckedChange={(checked) =>
                        setValues({ ...values, rate: checked ? "paid" : "" })
                    }
                />
                <FieldDescription id={rateHelpId}>
                    Untick to keep the quoted rating of {quote}¢ when paying a
                    different price.
                </FieldDescription>
            </fieldset>
            <FormActions>
                <Button
                    type="submit"
                    variant="success"
                    disabled={pending}
                    busy={pending}
                >
                    {uncertain ? "Retry hire" : "Hire"}
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    disabled={frozen}
                    onClick={() => navigate(props.back)}
                >
                    Cancel
                </Button>
            </FormActions>
            {(uncertain || !!notice) && (
                <div className="flex flex-wrap gap-3">
                    <Button
                        type="button"
                        size="sm"
                        disabled={pending}
                        onClick={(event) => {
                            if (event.currentTarget.form)
                                form.recoverAt(
                                    window.location.href,
                                    event.currentTarget.form,
                                );
                        }}
                    >
                        Reload page
                    </Button>
                    <Button
                        type="button"
                        size="sm"
                        disabled={pending}
                        onClick={(event) => {
                            if (event.currentTarget.form)
                                form.recoverAt(
                                    props.signInHref,
                                    event.currentTarget.form,
                                );
                        }}
                    >
                        Sign in again
                    </Button>
                </div>
            )}
        </Dialog>
    );
}
