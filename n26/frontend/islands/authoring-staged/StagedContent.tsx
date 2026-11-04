import { useEffect, useState } from "react";
import {
    ActionBar,
    Button,
    Dialog,
    FieldErrors,
    FormActions,
    Link,
    StagedBadge,
    Table,
} from "../../ui";

type StagedRow = {
    pk: string;
    label: string;
    qualifier: string;
    url: string;
    notes: string[];
    deleteUrl: string;
};

export type StagedContentProps = {
    groups: { label: string; model: string; rows: StagedRow[] }[];
    csrfToken: string;
    action: string;
    singleAction: string;
    selected: string[];
    errors: string[];
};

export function StagedContent(props: StagedContentProps) {
    const rows = props.groups.flatMap((group) =>
        group.rows.map((row) => ({
            ...row,
            kind: group.label,
            id: `${group.model}:${row.pk}`,
        })),
    );
    const [selected, setSelected] = useState(
        () =>
            new Set(
                props.selected.filter((id) =>
                    rows.some((row) => row.id === id),
                ),
            ),
    );
    const [confirming, setConfirming] = useState(false);
    const [pending, setPending] = useState(false);
    useEffect(() => {
        function restored(event: PageTransitionEvent) {
            if (event.persisted) {
                setPending(false);
                setConfirming(false);
            }
        }
        window.addEventListener("pageshow", restored);
        return () => window.removeEventListener("pageshow", restored);
    }, []);
    const chosen = rows.filter((row) => selected.has(row.id));
    const csrf = (
        <input
            type="hidden"
            name="csrfmiddlewaretoken"
            value={props.csrfToken}
        />
    );

    return (
        <div className="space-y-6">
            {props.errors.length > 0 && (
                <div role="alert">
                    <FieldErrors errors={props.errors} />
                </div>
            )}
            {rows.length ? (
                <>
                    <ActionBar
                        trailing={
                            <Button
                                variant="primary"
                                disabled={!chosen.length}
                                onClick={() => setConfirming(true)}
                            >
                                Put selected live
                            </Button>
                        }
                    >
                        <span role="status" className="text-sm text-muted">
                            {chosen.length} selected · {rows.length}{" "}
                            {rows.length === 1 ? "thing" : "things"} staged
                        </span>
                    </ActionBar>
                    {props.groups.map((group) => (
                        <section
                            key={group.model}
                            aria-label={group.label}
                            className="space-y-4"
                        >
                            <h2 className="text-lg font-semibold text-ink-900 dark:text-ink-100">
                                {group.label}
                            </h2>
                            <Table>
                                <tbody>
                                    {group.rows.map((row) => {
                                        const id = `${group.model}:${row.pk}`;
                                        const name = `${row.label}${row.qualifier ? ` — ${row.qualifier}` : ""}`;
                                        return (
                                            <tr key={id}>
                                                <td className="w-0 pr-0">
                                                    <input
                                                        type="checkbox"
                                                        aria-label={`Select ${name}`}
                                                        className="size-4 accent-[var(--color-accent)] focus-ring"
                                                        checked={selected.has(
                                                            id,
                                                        )}
                                                        onChange={(event) => {
                                                            const checked =
                                                                event.target
                                                                    .checked;
                                                            setSelected(
                                                                (previous) => {
                                                                    const next =
                                                                        new Set(
                                                                            previous,
                                                                        );
                                                                    if (checked)
                                                                        next.add(
                                                                            id,
                                                                        );
                                                                    else
                                                                        next.delete(
                                                                            id,
                                                                        );
                                                                    return next;
                                                                },
                                                            );
                                                        }}
                                                    />
                                                </td>
                                                <td className="whitespace-nowrap">
                                                    {row.url ? (
                                                        <Link href={row.url}>
                                                            {row.label}
                                                        </Link>
                                                    ) : (
                                                        row.label
                                                    )}
                                                    {row.qualifier &&
                                                        ` — ${row.qualifier}`}{" "}
                                                    <StagedBadge />
                                                </td>
                                                <td className="w-full text-muted">
                                                    {row.notes.join(" · ")}
                                                </td>
                                                <td className="whitespace-nowrap text-right">
                                                    <div className="flex items-center justify-end gap-3">
                                                        {row.deleteUrl && (
                                                            <Link
                                                                href={
                                                                    row.deleteUrl
                                                                }
                                                                tone="danger"
                                                                className="text-sm"
                                                            >
                                                                Delete…
                                                            </Link>
                                                        )}
                                                        <form
                                                            method="post"
                                                            action={
                                                                props.singleAction
                                                            }
                                                        >
                                                            {csrf}
                                                            <input
                                                                type="hidden"
                                                                name="act"
                                                                value="put_live"
                                                            />
                                                            <input
                                                                type="hidden"
                                                                name="model"
                                                                value={
                                                                    group.model
                                                                }
                                                            />
                                                            <input
                                                                type="hidden"
                                                                name="pk"
                                                                value={row.pk}
                                                            />
                                                            <Button
                                                                type="submit"
                                                                size="sm"
                                                                variant="ghost"
                                                            >
                                                                Put live
                                                            </Button>
                                                        </form>
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </Table>
                        </section>
                    ))}
                </>
            ) : (
                <p className="text-sm text-muted">
                    Nothing is staged. New content is staged when you create it
                    with the Staged switch on, or import it with “Stage new
                    content” switched on.
                </p>
            )}
            {confirming && (
                <Dialog
                    title="Put selected content live?"
                    lead="Players will be able to select this content."
                    pending={pending}
                    onDismiss={() => setConfirming(false)}
                    onSubmit={(event) => {
                        if (pending) {
                            event.preventDefault();
                            return;
                        }
                        event.currentTarget.action = props.action;
                        event.currentTarget.method = "post";
                        setPending(true);
                    }}
                >
                    {csrf}
                    <ul className="max-h-80 space-y-2 overflow-y-auto text-sm">
                        {chosen.map((row) => (
                            <li key={row.id}>
                                <input
                                    type="hidden"
                                    name="selection"
                                    value={row.id}
                                />
                                {row.label}
                                {row.qualifier && ` — ${row.qualifier}`}{" "}
                                <span className="text-muted">({row.kind})</span>
                            </li>
                        ))}
                    </ul>
                    <FormActions>
                        <Button
                            variant="ghost"
                            disabled={pending}
                            onClick={() => setConfirming(false)}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            variant="success"
                            disabled={pending}
                        >
                            Put {chosen.length} live
                        </Button>
                    </FormActions>
                </Dialog>
            )}
        </div>
    );
}
