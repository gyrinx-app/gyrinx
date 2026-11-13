import { ButtonLink, Icon } from "../../ui";
import type { Phase } from "./types";

export function PhaseSettings({
    phases,
    addHref,
    disabled,
}: {
    phases: Phase[];
    addHref?: string;
    disabled: boolean;
}) {
    return (
        <section aria-labelledby="schedule-phases" className="space-y-3">
            <h2 id="schedule-phases" className="text-lg font-semibold">
                Phases
            </h2>
            {phases.length ? (
                <ul className="divide-y divide-box-border rounded-box border border-box-border">
                    {phases.map((phase) => (
                        <li
                            key={phase.id}
                            className="flex items-center justify-between gap-3 p-3"
                        >
                            <div className="min-w-0">
                                <h3 className="font-medium [overflow-wrap:anywhere]">
                                    {phase.name}
                                </h3>
                                <p className="text-xs text-muted">
                                    {phase.count}{" "}
                                    {phase.count === 1
                                        ? "saved cycle"
                                        : "saved cycles"}
                                </p>
                            </div>
                            <div className="flex shrink-0 gap-1">
                                {(
                                    [
                                        ["Edit", "pencil", phase.editHref],
                                        [
                                            "Duplicate",
                                            "copy",
                                            phase.duplicateHref,
                                        ],
                                        ["Delete", "trash-2", phase.deleteHref],
                                    ] as const
                                ).map(
                                    ([label, icon, href]) =>
                                        href && (
                                            <ButtonLink
                                                key={label}
                                                href={href}
                                                variant="ghost"
                                                size="xs"
                                                aria-disabled={disabled}
                                                tabIndex={
                                                    disabled ? -1 : undefined
                                                }
                                                onClick={(event) => {
                                                    if (disabled)
                                                        event.preventDefault();
                                                }}
                                                className={`aria-disabled:cursor-not-allowed aria-disabled:opacity-75 inline-flex! size-7! items-center justify-center p-0! ${label === "Delete" ? "text-danger" : ""}`}
                                                aria-label={`${label} ${phase.name}`}
                                                title={`${label} ${phase.name}`}
                                            >
                                                <Icon
                                                    name={icon}
                                                    className="size-3.5"
                                                />
                                            </ButtonLink>
                                        ),
                                )}
                            </div>
                        </li>
                    ))}
                </ul>
            ) : (
                <p className="text-sm text-muted">
                    No phases yet. Add a phase to plan cycles.
                </p>
            )}
            {addHref && (
                <ButtonLink
                    href={addHref}
                    variant="ghost"
                    size="sm"
                    className="aria-disabled:cursor-not-allowed aria-disabled:opacity-75"
                    aria-disabled={disabled}
                    tabIndex={disabled ? -1 : undefined}
                    onClick={(event) => {
                        if (disabled) event.preventDefault();
                    }}
                >
                    <Icon name="plus" /> Add phase
                </ButtonLink>
            )}
        </section>
    );
}
