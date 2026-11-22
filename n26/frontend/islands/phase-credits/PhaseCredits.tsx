import { useState } from "react";
import {
    Alert,
    Breadcrumbs,
    Button,
    Card,
    Field,
    Input,
    NativeSelect,
    RadioCards,
    RadioCard,
    WorkflowLayout,
    useWorkflowForm,
    FormSection,
} from "../../ui";

type Award = {
    entry: string;
    name: string;
    cycle: string;
    terms: string;
    eligible: boolean;
    receipt: {
        amount: number;
        adjustment: string;
        actor: string;
        rolls: number[];
        note: string;
        method: string;
    } | null;
};
export type PhaseCreditsProps = {
    awards: Award[];
    gang: string;
    campaign: string;
    campaignHref: string;
    arbitrator: boolean;
    payments: { id: string; label: string }[];
    action: string;
    recoveryKey: string;
    csrfToken: string;
};

const paymentHelp =
    "Link the original payment to this award. The gang keeps its current balance.";

function AwardForm({ award, page }: { award: Award; page: PhaseCreditsProps }) {
    const form = useWorkflowForm({
        values: {
            method: award.eligible ? "collect" : "grant",
            note: "",
            payment: "",
            entry: award.entry,
        },
        errors: {},
        commandHref: page.action,
        csrfToken: page.csrfToken,
        recoveryKey: page.recoveryKey + ":" + award.entry,
        interpret(status, data) {
            if (status === 200 && data.saved === true)
                return { kind: "completed" };
            if (status === 422 && typeof data.error === "string")
                return { kind: "invalid", errors: { __all__: [data.error] } };
            return null;
        },
    });
    const { values, setValues, pending } = form;
    const [noteOpen, setNoteOpen] = useState(Boolean(values.note));
    const method = values.method;
    const verb =
        method === "paid"
            ? "Mark as already paid"
            : method === "grant"
              ? `Grant ${award.name} credits`
              : `Collect ${award.name} credits`;
    const noteField = (
        <Field
            label={method === "collect" ? "Note" : "Reason"}
            htmlFor={award.entry + "-note"}
        >
            <Input
                name="note"
                value={values.note}
                onChange={(e) => setValues({ ...values, note: e.target.value })}
                maxLength={255}
                required={method !== "collect"}
            />
        </Field>
    );
    const paid = method === "paid";
    return (
        <form onSubmit={form.save} className="space-y-3">
            <input type="hidden" name="entry" value={award.entry} />
            <input type="hidden" name="method" value={method} />
            {(!paid || (page.payments.length <= 3 && !values.payment)) && (
                <input type="hidden" name="payment" value="" />
            )}
            {!page.arbitrator && <input type="hidden" name="note" value="" />}
            {page.arbitrator && (
                <fieldset className="space-y-3" disabled={form.frozen}>
                    {!award.eligible && !paid && (
                        <p className="text-sm text-muted">
                            Record why {page.gang} should receive this award.
                        </p>
                    )}
                    {paid && page.payments.length <= 3 && (
                        <RadioCards
                            legend="Previous credit adjustment"
                            description={paymentHelp}
                        >
                            {page.payments.map((p) => (
                                <RadioCard
                                    key={p.id}
                                    name="payment"
                                    value={p.id}
                                    label={p.label}
                                    checked={values.payment === p.id}
                                    onChange={() =>
                                        setValues({ ...values, payment: p.id })
                                    }
                                />
                            ))}
                        </RadioCards>
                    )}
                    {paid && page.payments.length > 3 && (
                        <Field
                            label="Previous credit adjustment"
                            htmlFor={award.entry + "-payment"}
                            description={
                                page.payments.find(
                                    (p) => p.id === values.payment,
                                )?.label ?? paymentHelp
                            }
                        >
                            <NativeSelect
                                name="payment"
                                required
                                value={values.payment}
                                onChange={(e) =>
                                    setValues({
                                        ...values,
                                        payment: e.target.value,
                                    })
                                }
                            >
                                <option value="">Select a payment</option>
                                {page.payments.map((p) => (
                                    <option key={p.id} value={p.id}>
                                        {p.label}
                                    </option>
                                ))}
                            </NativeSelect>
                        </Field>
                    )}
                    {method === "collect" ? (
                        <details
                            open={noteOpen}
                            onToggle={(event) =>
                                setNoteOpen(event.currentTarget.open)
                            }
                        >
                            <summary className="w-fit cursor-pointer text-sm font-medium text-muted">
                                Add a note
                            </summary>
                            <div className="mt-2">{noteField}</div>
                        </details>
                    ) : (
                        noteField
                    )}
                </fieldset>
            )}
            {form.hasErrors && (
                <div ref={form.summary} tabIndex={-1}>
                    <Alert tone="error" dismissible={false}>
                        {form.errors.__all__?.join(" ")} {form.notice}
                    </Alert>
                </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
                <Button
                    type="submit"
                    variant="success"
                    busy={pending}
                    disabled={pending}
                >
                    {form.uncertain ? "Retry save" : verb}
                </Button>
                {page.arbitrator && page.payments.length > 0 && (
                    <Button
                        variant="ghost"
                        disabled={form.frozen}
                        onClick={() =>
                            setValues({
                                ...values,
                                method: paid
                                    ? award.eligible
                                        ? "collect"
                                        : "grant"
                                    : "paid",
                            })
                        }
                    >
                        {paid ? "Cancel" : "Already paid?"}
                    </Button>
                )}
            </div>
        </form>
    );
}

function Receipt({
    award,
}: {
    award: Award & { receipt: NonNullable<Award["receipt"]> };
}) {
    const { receipt } = award;
    const action =
        receipt.method === "paid"
            ? "Payment linked"
            : receipt.method === "grant"
              ? "Granted"
              : "Collected";
    const roll = receipt.rolls
        .flatMap((count, i) =>
            count ? [count === 1 ? String(i + 1) : `${count} × ${i + 1}`] : [],
        )
        .join(", ");
    return (
        <div className="min-w-0 space-y-2 border-t border-box-border pt-3 text-sm">
            <p>
                {action}
                {receipt.actor && ` by ${receipt.actor}`}
            </p>
            {roll && (
                <p>
                    {award.terms} · Rolled {roll}
                </p>
            )}
            {receipt.adjustment && (
                <p>
                    <span className="font-medium">Credit adjustment</span> ·{" "}
                    {receipt.adjustment}
                </p>
            )}
            {receipt.note && (
                <p className="break-words">
                    <span className="font-medium">Note</span> · {receipt.note}
                </p>
            )}
        </div>
    );
}

export function PhaseCredits(page: PhaseCreditsProps) {
    const pending = page.awards.filter((a) => !a.receipt);
    const receipts = page.awards.filter(
        (a): a is Award & { receipt: NonNullable<Award["receipt"]> } =>
            a.receipt !== null,
    );
    function heading(award: Award) {
        return (
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <div className="min-w-0">
                    <h3 className="break-words text-base font-semibold">
                        {award.name}
                    </h3>
                    <p className="text-sm text-muted">{award.cycle}</p>
                </div>
                <span className="text-lg font-semibold tabular-nums">
                    {award.receipt ? `${award.receipt.amount}¢` : award.terms}
                </span>
            </div>
        );
    }
    return (
        <WorkflowLayout
            footer={null}
            title="Phase credits"
            lead={page.gang}
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: page.campaign, href: page.campaignHref },
                        { label: "Phase credits" },
                    ]}
                />
            }
        >
            {pending.length > 0 && (
                <FormSection title="Open awards">
                    {pending.map((award) => (
                        <Card key={award.entry}>
                            <div className="space-y-3">
                                {heading(award)}
                                <AwardForm page={page} award={award} />
                            </div>
                        </Card>
                    ))}
                </FormSection>
            )}
            {receipts.length > 0 && (
                <FormSection title="Receipts">
                    {receipts.map((award) => (
                        <Card key={award.entry}>
                            <div className="space-y-3">
                                {heading(award)}
                                <Receipt award={award} />
                            </div>
                        </Card>
                    ))}
                </FormSection>
            )}
            {!page.awards.length && (
                <p className="text-muted">
                    Phase awards appear here when {page.gang} takes part in a
                    phase with entry credits.
                </p>
            )}
        </WorkflowLayout>
    );
}
