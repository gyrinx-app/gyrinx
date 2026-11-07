import { type FormEvent, useEffect, useRef, useState } from "react";
import { CommandError, postForm } from "../../http/command";
import {
    Breadcrumbs,
    Button,
    ButtonLink,
    Field,
    FieldErrors,
    FormActions,
    FormSection,
    Input,
    WorkflowPage,
} from "../../ui";

type Errors = Record<string, string[]>;
type Current = { name: string; income: number | null };
export interface EditHoldingProps {
    heading: string;
    holdingName: string;
    campaignName: string;
    campaignHref: string;
    campaignsHref: string;
    detailHref: string;
    catalogueName: string;
    catalogueIncome: number;
    values: { name: string; income: string; snapshot: string };
    fields: Record<"name" | "income", { label: string; help: string }>;
    errors: Errors;
    conflict: Current | null;
    back: string;
    action: string;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
}
function currentValues(value: unknown): value is Current {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const data = value as Record<string, unknown>;
    return (
        typeof data.name === "string" &&
        (data.income === null || Number.isInteger(data.income))
    );
}

function recover(key: string): URLSearchParams | null {
    try {
        const stored = sessionStorage.getItem(key);
        if (!stored) return null;
        const data = new URLSearchParams(stored);
        return ["name", "income", "snapshot"].every((name) => data.has(name))
            ? data
            : null;
    } catch {
        return null;
    }
}

function clearRecovery(key: string) {
    try {
        sessionStorage.removeItem(key);
    } catch {
        /* Repeating a stored submission does not apply it twice. */
    }
}

function fieldErrors(value: unknown): value is Errors {
    return (
        !!value &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.values(value).every(
            (errors) =>
                Array.isArray(errors) &&
                errors.every((error) => typeof error === "string"),
        )
    );
}

export function EditHolding(
    props: EditHoldingProps & {
        onNavigate?: (url: string) => void;
        onReload?: () => void;
    },
) {
    const [recovery] = useState(() => recover(props.recoveryKey));
    const [values, setValues] = useState(
        recovery
            ? {
                  name: recovery.get("name")!,
                  income: recovery.get("income")!,
                  snapshot: recovery.get("snapshot")!,
              }
            : props.values,
    );
    const [conflict, setConflict] = useState(recovery ? null : props.conflict);
    const [errors, setErrors] = useState<Errors>(recovery ? {} : props.errors);
    const [pending, setPending] = useState(false);
    const [uncertain, setUncertain] = useState(!!recovery);
    const [notice, setNotice] = useState(
        recovery
            ? "An earlier save has not been confirmed. Retry it before making another change."
            : "",
    );
    const inFlight = useRef(false);
    const saved = useRef(false);
    const unknownOutcome = useRef(!!recovery);
    const submitted = useRef<URLSearchParams | null>(recovery);
    const summary = useRef<HTMLDivElement>(null);
    const [failure, setFailure] = useState(0);
    useEffect(() => {
        const restore = (event: PageTransitionEvent) => {
            if (event.persisted && saved.current) {
                (props.onReload ?? (() => window.location.reload()))();
            }
        };
        window.addEventListener("pageshow", restore);
        return () => window.removeEventListener("pageshow", restore);
    }, [props.onReload]);
    useEffect(() => {
        if (failure) summary.current?.focus();
    }, [failure]);
    useEffect(() => {
        if (!uncertain && !pending) return;
        const warn = (event: BeforeUnloadEvent) => {
            if (unknownOutcome.current) {
                event.preventDefault();
                event.returnValue = true;
            }
        };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [uncertain, pending]);

    async function save(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (inFlight.current || conflict) return;
        inFlight.current = true;
        unknownOutcome.current = true;
        setPending(true);
        setNotice("");
        if (!uncertain) {
            submitted.current = new URLSearchParams();
            new FormData(event.currentTarget).forEach((value, name) =>
                submitted.current!.append(name, String(value)),
            );
            submitted.current.delete("csrfmiddlewaretoken");
        }
        try {
            try {
                sessionStorage.setItem(
                    props.recoveryKey,
                    submitted.current!.toString(),
                );
            } catch {
                throw new CommandError(
                    "Your browser could not keep this save for recovery. Allow this site to store data, then try again.",
                    "rejected",
                );
            }
            const body = new URLSearchParams(submitted.current!);
            body.set("csrfmiddlewaretoken", props.csrfToken);
            const { status, data } = await postForm(
                props.commandHref,
                body,
                props.csrfToken,
            );
            if (status === 200 && typeof data.nextUrl === "string") {
                saved.current = true;
                unknownOutcome.current = false;
                clearRecovery(props.recoveryKey);
                setUncertain(false);
                (props.onNavigate ?? ((url) => window.location.assign(url)))(
                    data.nextUrl,
                );
                return;
            }
            if (
                status === 409 &&
                data.code === "revision_conflict" &&
                currentValues(data.current) &&
                fieldErrors(data.errors)
            ) {
                setConflict(data.current);
                setErrors(data.errors);
                setUncertain(true);
                unknownOutcome.current = false;
            } else if (status === 422 && fieldErrors(data.errors)) {
                setErrors(data.errors);
                if (uncertain) {
                    unknownOutcome.current = true;
                    setNotice(
                        "The earlier save is still unconfirmed. Keep this form open until you can retry.",
                    );
                } else {
                    clearRecovery(props.recoveryKey);
                    unknownOutcome.current = false;
                    setUncertain(false);
                }
            } else {
                throw new CommandError(
                    "The save could not be confirmed. Retry this save before making another change.",
                    "unknown",
                );
            }
        } catch (error) {
            const problem =
                error instanceof CommandError
                    ? error
                    : new CommandError(
                          "The save could not be confirmed. Retry this save before making another change.",
                          "unknown",
                      );
            setNotice(problem.message);
            // An earlier uncertain write remains unresolved even if a retry is rejected.
            unknownOutcome.current = uncertain || problem.outcome === "unknown";
            if (!unknownOutcome.current) clearRecovery(props.recoveryKey);
            setUncertain(unknownOutcome.current);
        } finally {
            inFlight.current = false;
            setPending(false);
            setFailure((n) => n + 1);
        }
    }
    function reviewCurrent() {
        try {
            sessionStorage.removeItem(props.recoveryKey);
        } catch {
            setNotice(
                "Your browser could not clear this draft. Check this site’s storage settings, then try again.",
            );
            return;
        }
        unknownOutcome.current = false;
        (props.onNavigate ?? ((url) => window.location.replace(url)))(
            props.action,
        );
    }
    const hasErrors =
        !!notice || Object.values(errors).some((e) => e.length > 0);
    return (
        <WorkflowPage
            title={props.heading}
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: "Campaigns", href: props.campaignsHref },
                        { label: props.campaignName, href: props.campaignHref },
                        { label: props.holdingName, href: props.detailHref },
                        { label: "Edit" },
                    ]}
                />
            }
            method="post"
            action={props.action}
            onSubmit={save}
            aria-busy={pending}
            footer={
                <FormActions>
                    {conflict ? (
                        <Button
                            type="button"
                            variant="primary"
                            onClick={reviewCurrent}
                        >
                            Review current asset
                        </Button>
                    ) : (
                        <Button
                            type="submit"
                            variant="success"
                            disabled={pending}
                        >
                            {pending
                                ? "Saving…"
                                : uncertain
                                  ? "Retry save"
                                  : "Save"}
                        </Button>
                    )}
                    <ButtonLink href={props.back} variant="ghost">
                        Cancel
                    </ButtonLink>
                </FormActions>
            }
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={props.csrfToken}
            />
            <input type="hidden" name="snapshot" value={values.snapshot} />
            {hasErrors && (
                <div
                    ref={summary}
                    tabIndex={-1}
                    role="alert"
                    aria-label="Save errors"
                >
                    <FieldErrors
                        errors={[
                            ...(errors.__all__ ?? []),
                            ...(errors.snapshot ?? []),
                            ...(notice ? [notice] : []),
                        ]}
                    />
                    {!notice &&
                        !errors.__all__?.length &&
                        !errors.snapshot?.length && (
                            <p>Check the highlighted fields.</p>
                        )}
                </div>
            )}
            {conflict && (
                <div
                    role="region"
                    aria-label="Current asset details"
                    className="space-y-1"
                >
                    <p>Current name: {conflict.name || props.catalogueName}.</p>
                    <p>
                        Current income override:{" "}
                        {conflict.income === null
                            ? "None (uses catalogue income)"
                            : `${conflict.income}¢`}
                        .
                    </p>
                </div>
            )}
            <fieldset
                disabled={pending || uncertain || !!conflict}
                className="contents"
            >
                <FormSection title="Details">
                    <p className="text-sm text-muted">
                        Catalogue entry: {props.catalogueName} · Income:{" "}
                        {props.catalogueIncome}¢.
                    </p>
                    <Field
                        label={props.fields.name.label}
                        description={props.fields.name.help}
                        descriptionPlacement="before"
                        htmlFor="asset-name"
                        errors={errors.name}
                    >
                        <Input
                            name="name"
                            maxLength={200}
                            autoComplete="off"
                            value={values.name}
                            onChange={(e) =>
                                setValues({ ...values, name: e.target.value })
                            }
                        />
                    </Field>
                    <Field
                        label={props.fields.income.label}
                        description={props.fields.income.help}
                        descriptionPlacement="before"
                        htmlFor="asset-income"
                        errors={errors.income}
                    >
                        <Input
                            name="income"
                            type="number"
                            min={0}
                            max={2147483647}
                            inputMode="numeric"
                            rightAddon="¢"
                            value={values.income}
                            onChange={(e) =>
                                setValues({ ...values, income: e.target.value })
                            }
                        />
                    </Field>
                </FormSection>
            </fieldset>
        </WorkflowPage>
    );
}
