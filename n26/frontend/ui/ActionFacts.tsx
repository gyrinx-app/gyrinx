import type { ComponentProps, ReactNode } from "react";
import cotton from "../generated/cotton.json";
import { ButtonLink, FormSection, Icon, Tally } from "./index";

const recipe = cotton.actionFacts;
export function ActionDetail({ children }: { children: ReactNode }) {
    return <span className={recipe.detail}>{children}</span>;
}
export function ActionText({
    children,
    tone = "muted",
}: {
    children: ReactNode;
    tone?: "muted" | "note" | "strong";
}) {
    return (
        <p
            className={
                tone === "strong"
                    ? recipe.attemptValue
                    : tone === "note"
                      ? recipe.muted
                      : recipe.explanation
            }
        >
            {children}
        </p>
    );
}
export function ActionFooterLink({
    kind,
    className = "",
    ...props
}: ComponentProps<typeof ButtonLink> & { kind?: "back" | "danger" }) {
    return (
        <ButtonLink
            variant="ghost"
            {...props}
            className={`${kind ? recipe[kind] : ""} ${className}`}
        />
    );
}
export function ActionRollSummary({
    value,
    explanation,
}: {
    value?: number;
    explanation?: string;
}) {
    return (
        <>
            {value ? <p className={recipe.rollValue}>2D6: {value}</p> : null}
            {explanation && <p className={recipe.explanation}>{explanation}</p>}
        </>
    );
}
type Attempt = {
    roll: number;
    result_name: string | null;
    is_available: boolean;
    unavailable_reason: string | null;
};
export function ActionAttempts({ attempts }: { attempts: Attempt[] }) {
    return attempts.length ? (
        <ol className={recipe.attempts}>
            {attempts.map((attempt, index) => (
                <li key={index}>
                    <span className={recipe.attemptValue}>
                        D6: {attempt.roll}
                    </span>
                    {attempt.result_name && ` — ${attempt.result_name}`}
                    {!attempt.is_available && (
                        <p className={recipe.muted}>
                            {attempt.unavailable_reason}
                        </p>
                    )}
                </li>
            ))}
        </ol>
    ) : null;
}
type Facts = {
    stage: string;
    outcome: string;
    selection_summary?: string;
    show_outcome?: boolean;
    outcome_description?: string;
    reviewChoice: {
        label: string;
        title: string;
        description: string;
        meta: string;
    } | null;
    changes: {
        kind: string;
        name: string;
        before: number;
        after: number;
        removed_count: number;
        slot_type: string;
    }[];
    change_href?: string;
    correction?: boolean;
    retained_payment?: boolean;
    retained_roll?: boolean;
    receipt: { label: string; value: string }[];
    hold_reason?: string;
    allowanceThreshold: boolean;
    keeps_stashed_weapons?: boolean;
};
/** Prepared action facts using the same Cotton stages as the native call sites. */
export function ActionFacts({
    facts: f,
    modelName,
    frozen,
    onNavigate,
}: {
    facts: Facts;
    modelName: string;
    frozen: boolean;
    onNavigate: (href: string) => void;
}) {
    if (f.stage === "review")
        return (
            <FormSection title="Review">
                <div className={recipe.review}>
                    {f.show_outcome && (
                        <div className={recipe.outcome}>
                            <p className={recipe.caption}>Choice</p>
                            <h3 className={recipe.outcomeTitle}>{f.outcome}</h3>
                            {f.outcome_description && (
                                <p className={recipe.muted}>
                                    {f.outcome_description}
                                </p>
                            )}
                        </div>
                    )}
                    {f.reviewChoice && (
                        <div className={recipe.selection}>
                            <div className={recipe.selectionRow}>
                                <div className={recipe.selectionContent}>
                                    <p className={recipe.caption}>
                                        {f.reviewChoice.label}
                                    </p>
                                    <h3 className={recipe.title}>
                                        {f.reviewChoice.title}
                                    </h3>
                                    {f.reviewChoice.description && (
                                        <p className={recipe.description}>
                                            {f.reviewChoice.description}
                                        </p>
                                    )}
                                    {f.reviewChoice.meta && (
                                        <p className={recipe.muted}>
                                            {f.reviewChoice.meta}
                                        </p>
                                    )}
                                </div>
                                {f.change_href && (
                                    <ButtonLink
                                        href={f.change_href}
                                        variant="default"
                                        size="sm"
                                        aria-disabled={frozen}
                                        onClick={(event) => {
                                            event.preventDefault();
                                            if (!frozen)
                                                onNavigate(f.change_href!);
                                        }}
                                    >
                                        Change selection
                                    </ButtonLink>
                                )}
                            </div>
                        </div>
                    )}
                    {f.changes.length > 0 && (
                        <div className={recipe.changes}>
                            <p className={recipe.caption}>Changes</p>
                            {f.changes.map((change, index) => (
                                <p key={index}>
                                    {change.kind === "counter"
                                        ? `${change.name}: ${change.before} → ${change.after}`
                                        : change.removed_count
                                          ? `Remove ${change.removed_count} ${change.slot_type} choice${change.removed_count === 1 ? "" : "s"}.`
                                          : ""}
                                </p>
                            ))}
                        </div>
                    )}
                </div>
                {f.correction && f.retained_payment && (
                    <p className={recipe.retainedPayment}>
                        The original payment is retained.
                    </p>
                )}
                {f.correction && f.retained_roll && (
                    <p className={recipe.note}>
                        The recorded rolls are retained.
                    </p>
                )}
            </FormSection>
        );
    if (f.stage === "done")
        return (
            <FormSection title="Completed">
                <div className={recipe.completed}>
                    <div className={recipe.completedRow}>
                        <Icon
                            name="circle-check"
                            label="Completed"
                            className={recipe.completedIcon}
                        />
                        <div className={recipe.selectionContent}>
                            <p className={recipe.caption}>Choice</p>
                            <h3 className={recipe.title}>{f.outcome}</h3>
                            {f.selection_summary && (
                                <p>{f.selection_summary}</p>
                            )}
                        </div>
                    </div>
                </div>
                {f.receipt.length > 0 && (
                    <div className={recipe.result}>
                        <h3 className={recipe.resultTitle}>Result</h3>
                        <Tally
                            facts={f.receipt.map((row) => ({
                                ...row,
                                sub: "",
                                ruled: false,
                                strong: false,
                            }))}
                        />
                    </div>
                )}
            </FormSection>
        );
    if (f.stage === "on-hold")
        return (
            <FormSection title="On hold">
                <p>{f.hold_reason}</p>
                <p className={recipe.note}>
                    Recorded rolls and choices are kept.
                </p>
            </FormSection>
        );
    if (f.stage === "undo")
        return (
            <FormSection title="Undo advancement">
                <p className={recipe.title}>
                    Undo this advancement for {modelName}?
                </p>
                {f.selection_summary && (
                    <p className={recipe.undoSummary}>{f.selection_summary}</p>
                )}
                <p className={recipe.note}>
                    Its result, rating increase and any promotion will be
                    removed. The earned use will be waiting again, with its
                    recorded rolls and choices kept.
                </p>
                {f.allowanceThreshold && (
                    <p className={recipe.note}>
                        The earned use is available only while its rank
                        threshold is met.
                    </p>
                )}
                {f.keeps_stashed_weapons && (
                    <p className={recipe.note}>
                        Weapons moved to the stash stay there.
                    </p>
                )}
            </FormSection>
        );
    if (f.stage === "by-hand")
        return (
            <FormSection title="Mark as applied">
                <p className={recipe.title}>
                    Did you apply this result to {modelName} outside Gyrinx?
                </p>
                <p className={recipe.note}>
                    Gyrinx stops showing this earned use as available. Nothing
                    on the model changes. You can undo this from Action history.
                </p>
            </FormSection>
        );
    if (f.stage === "cancel")
        return (
            <FormSection title="Cancel flow">
                <div className={recipe.cancel}>
                    <p className={recipe.title}>Cancel this unfinished flow?</p>
                    <p className={recipe.note}>
                        Your saved choices will be discarded.
                    </p>
                </div>
            </FormSection>
        );
    return null;
}
