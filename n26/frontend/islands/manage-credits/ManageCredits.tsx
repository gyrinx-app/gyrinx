import {
    type ComponentProps,
    type FormEvent,
    useEffect,
    useRef,
    useState,
} from "react";
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
    RadioCard,
    RadioCards,
    UserLink,
    WorkflowPage,
} from "../../ui";

type Errors = Record<string, string[]>;
export interface ManageCreditsProps {
    gangName: string;
    balance: number;
    gangHref: string;
    owner: ComponentProps<typeof UserLink>;
    historyHref: string;
    directions: Array<{ value: string; label: string; description: string }>;
    values: {
        direction: string;
        amount: string | number;
        note: string;
        request_key: string;
    };
    errors: Errors;
    noteHelp: string;
    back: string;
    action: string;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
}

function recover(key: string): URLSearchParams | null {
    try {
        const stored = sessionStorage.getItem(key);
        if (!stored) return null;
        const data = new URLSearchParams(stored);
        return ["direction", "amount", "note", "request_key", "back"].every(
            (name) => data.has(name),
        )
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
        /* A retained receipt can still be retried safely. */
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

export function ManageCredits(
    props: ManageCreditsProps & { onNavigate?: (url: string) => void },
) {
    const [recovery] = useState(() => recover(props.recoveryKey));
    const [values, setValues] = useState(
        recovery
            ? {
                  direction: recovery.get("direction")!,
                  amount: recovery.get("amount")!,
                  note: recovery.get("note")!,
                  request_key: recovery.get("request_key")!,
              }
            : props.values,
    );
    const [balance, setBalance] = useState(props.balance);
    const [errors, setErrors] = useState(props.errors);
    const [pending, setPending] = useState(false);
    const [uncertain, setUncertain] = useState(!!recovery);
    const [notice, setNotice] = useState(
        recovery
            ? "An earlier save has not been confirmed. Retry it before making another change."
            : "",
    );
    const inFlight = useRef(false);
    const unknownOutcome = useRef(!!recovery);
    const submitted = useRef<URLSearchParams | null>(recovery);
    const summary = useRef<HTMLDivElement>(null);
    const [failure, setFailure] = useState(0);
    useEffect(() => {
        if (failure) summary.current?.focus();
    }, [failure]);
    useEffect(() => {
        if (!uncertain && !pending) return;
        const warn = (event: BeforeUnloadEvent) => {
            if (unknownOutcome.current) event.preventDefault();
        };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [uncertain, pending]);

    async function save(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (inFlight.current) return;
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
                    "Your browser could not keep this save for recovery. Allow session storage before saving.",
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
                unknownOutcome.current = false;
                clearRecovery(props.recoveryKey);
                setUncertain(false);
                (props.onNavigate ?? ((url) => window.location.assign(url)))(
                    data.nextUrl,
                );
                return;
            }
            if (
                (status === 422 || status === 409) &&
                fieldErrors(data.errors) &&
                typeof data.balance === "number"
            ) {
                setErrors(data.errors);
                setBalance(data.balance);
                clearRecovery(props.recoveryKey);
                unknownOutcome.current = false;
                setUncertain(false);
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
    const hasErrors =
        !!notice || Object.values(errors).some((e) => e.length > 0);
    return (
        <WorkflowPage
            title="Manage credits"
            lead={`${props.gangName} has ${balance}¢.`}
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: <UserLink {...props.owner} /> },
                        { label: props.gangName, href: props.gangHref },
                        { label: "Manage credits" },
                    ]}
                />
            }
            actions={
                props.historyHref ? (
                    <ButtonLink href={props.historyHref} size="sm">
                        Credit history
                    </ButtonLink>
                ) : undefined
            }
            method="post"
            action={props.action}
            onSubmit={save}
            aria-busy={pending}
            footer={
                <FormActions>
                    <Button type="submit" variant="success" disabled={pending}>
                        {pending
                            ? "Saving…"
                            : uncertain
                              ? "Retry save"
                              : "Save"}
                    </Button>
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
            <input type="hidden" name="back" value={props.back} />
            <input
                type="hidden"
                name="request_key"
                value={values.request_key}
            />
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
                            ...(errors.request_key ?? []),
                            ...(notice ? [notice] : []),
                        ]}
                    />
                    {!notice &&
                        !errors.__all__?.length &&
                        !errors.request_key?.length && (
                            <p>Check the highlighted fields.</p>
                        )}
                </div>
            )}
            <fieldset disabled={pending || uncertain} className="contents">
                <FormSection title="The change">
                    <RadioCards
                        legend="Add or remove *"
                        min="12rem"
                        errors={errors.direction}
                    >
                        {props.directions.map((choice) => (
                            <RadioCard
                                key={choice.value}
                                name="direction"
                                {...choice}
                                checked={values.direction === choice.value}
                                onChange={() =>
                                    setValues({
                                        ...values,
                                        direction: choice.value,
                                    })
                                }
                            />
                        ))}
                    </RadioCards>
                    <Field
                        label="Credits *"
                        htmlFor="credits-amount"
                        errors={errors.amount}
                    >
                        <Input
                            name="amount"
                            type="number"
                            min="1"
                            max="1000000"
                            inputMode="numeric"
                            required
                            value={values.amount}
                            onChange={(e) =>
                                setValues({ ...values, amount: e.target.value })
                            }
                            rightAddon={
                                <span
                                    className="text-sm text-muted"
                                    aria-hidden="true"
                                >
                                    ¢
                                </span>
                            }
                        />
                    </Field>
                    <Field
                        label="Note"
                        htmlFor="credits-note"
                        description={props.noteHelp}
                        descriptionPlacement="before"
                        errors={errors.note}
                    >
                        <Input
                            name="note"
                            maxLength={255}
                            autoComplete="off"
                            value={values.note}
                            onChange={(e) =>
                                setValues({ ...values, note: e.target.value })
                            }
                        />
                    </Field>
                </FormSection>
            </fieldset>
        </WorkflowPage>
    );
}
