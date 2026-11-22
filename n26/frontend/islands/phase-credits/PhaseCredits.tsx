import {
    Breadcrumbs,
    Button,
    Card,
    Field,
    Input,
    NativeSelect,
    WorkflowLayout,
    useWorkflowForm,
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
    csrfToken: string;
};

function AwardCard({ award, page }: { award: Award; page: PhaseCreditsProps }) {
    const receipt = award.receipt;
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
        recoveryKey: "phase-credits:" + page.action + ":" + award.entry,
        interpret(status, data) {
            if (status === 200 && data.saved === true)
                return { kind: "completed" };
            if (status === 422 && typeof data.error === "string")
                return { kind: "invalid", errors: { __all__: [data.error] } };
            return null;
        },
    });
    const { values, setValues, pending } = form;
    const method = values.method;
    const verb =
        method === "paid"
            ? "Mark as already paid"
            : method === "grant"
              ? `Grant ${award.name} credits`
              : `Collect ${award.name} credits`;
    return (
        <Card
            header={
                <h2>
                    {award.name} · {award.cycle}
                </h2>
            }
        >
            {receipt ? (
                <div className="space-y-1">
                    <p>
                        {receipt.method === "paid"
                            ? "Recorded as already paid"
                            : receipt.method === "grant"
                              ? "Granted"
                              : "Collected"}{" "}
                        · {receipt.amount}¢
                        {receipt.actor && ` · ${receipt.actor}`}
                    </p>
                    {receipt.rolls.length > 0 && (
                        <p>
                            {award.terms} · Rolled{" "}
                            {receipt.rolls
                                .flatMap((count, i) =>
                                    count === 0
                                        ? []
                                        : [
                                              count === 1
                                                  ? String(i + 1)
                                                  : `${count} × ${i + 1}`,
                                          ],
                                )
                                .join(", ")}
                        </p>
                    )}
                    {receipt.adjustment && (
                        <p>Credit adjustment · {receipt.adjustment}</p>
                    )}
                    {receipt.note && <p>{receipt.note}</p>}
                </div>
            ) : (
                <form onSubmit={form.save} className="space-y-3">
                    <input type="hidden" name="entry" value={award.entry} />
                    <input type="hidden" name="method" value={method} />
                    {method !== "paid" && (
                        <input type="hidden" name="payment" value="" />
                    )}
                    {!page.arbitrator && (
                        <input type="hidden" name="note" value="" />
                    )}
                    <p>Phase entry · {award.terms}</p>
                    {!award.eligible && (
                        <p>An arbitrator can grant this award with a note.</p>
                    )}
                    <fieldset disabled={form.frozen} className="space-y-3">
                        {page.arbitrator && page.payments.length > 0 && (
                            <Field
                                label="Action"
                                htmlFor={award.entry + "-method"}
                            >
                                <NativeSelect
                                    value={method}
                                    onChange={(e) =>
                                        setValues({
                                            ...values,
                                            method: e.target.value,
                                        })
                                    }
                                >
                                    <option
                                        value={
                                            award.eligible ? "collect" : "grant"
                                        }
                                    >
                                        {award.eligible
                                            ? "Collect credits"
                                            : "Grant credits"}
                                    </option>
                                    <option value="paid">
                                        Mark as already paid
                                    </option>
                                </NativeSelect>
                            </Field>
                        )}
                        {method === "paid" && (
                            <Field
                                label="Credit adjustment"
                                htmlFor={award.entry + "-payment"}
                            >
                                <NativeSelect
                                    required
                                    name="payment"
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
                        {page.arbitrator && (
                            <Field
                                label={
                                    method === "collect"
                                        ? "Note (optional)"
                                        : "Note"
                                }
                                htmlFor={award.entry + "-note"}
                            >
                                <Input
                                    name="note"
                                    value={values.note}
                                    onChange={(e) =>
                                        setValues({
                                            ...values,
                                            note: e.target.value,
                                        })
                                    }
                                    maxLength={255}
                                    required={method !== "collect"}
                                />
                            </Field>
                        )}
                    </fieldset>
                    {form.hasErrors && (
                        <div role="alert" tabIndex={-1} ref={form.summary}>
                            {form.errors.__all__?.join(" ")} {form.notice}
                        </div>
                    )}
                    <Button
                        type="submit"
                        variant="success"
                        busy={pending}
                        disabled={pending}
                    >
                        {form.uncertain ? "Retry save" : verb}
                    </Button>
                </form>
            )}
        </Card>
    );
}
export function PhaseCredits(page: PhaseCreditsProps) {
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
            {page.awards.length ? (
                page.awards.map((award) => (
                    <AwardCard key={award.entry} award={award} page={page} />
                ))
            ) : (
                <p>No phase credits are available for this gang.</p>
            )}
        </WorkflowLayout>
    );
}
