import { useState } from "react";
import { Button, Card, Icon, Link } from "../../ui";

export type CampaignSetupProps = {
    storageKey: string;
    items: { label: string; href: string; complete: boolean }[];
};

export function CampaignSetup({ storageKey, items }: CampaignSetupProps) {
    const [dismissed, setDismissed] = useState(() => {
        try {
            return localStorage.getItem(storageKey) === "dismissed";
        } catch {
            return false;
        }
    });
    if (dismissed) return null;
    return (
        <Card>
            <section
                aria-label="Set up your campaign"
                className="relative grid gap-6 md:grid-cols-2"
            >
                <div>
                    <h2 className="mb-3 text-lg font-semibold">
                        Set up your campaign
                    </h2>
                    <ul className="space-y-2">
                        {items.map((item) => (
                            <li
                                key={item.label}
                                className="flex items-center gap-2 text-sm"
                            >
                                <Icon
                                    name={
                                        item.complete
                                            ? "circle-check"
                                            : "circle"
                                    }
                                    className={
                                        item.complete
                                            ? "size-4 shrink-0 text-accent"
                                            : "size-4 shrink-0 text-muted"
                                    }
                                    label={item.complete ? "Complete" : "To do"}
                                />
                                <Link
                                    href={item.href}
                                    tone={item.complete ? "current" : "accent"}
                                    className={
                                        item.complete ? "text-muted" : ""
                                    }
                                >
                                    {item.label}
                                </Link>
                            </li>
                        ))}
                    </ul>
                </div>
                <div className="space-y-2 pr-7 text-sm text-muted md:border-l md:border-box-border md:pl-6">
                    <h3 className="font-semibold text-ink-900 dark:text-ink-100">
                        Manage your campaign
                    </h3>
                    <p>
                        As arbitrator, you set the campaign rules and keep play
                        moving. Invite players to bring their gangs, organise
                        the schedule and prepare territories before play begins.
                    </p>
                    <p>
                        Use the campaign menu to change settings and open its
                        pages. Battles, territory changes and dice rolls appear
                        in the activity log.
                    </p>
                </div>
                <Button
                    size="xs"
                    variant="ghost"
                    className="absolute right-0 top-0 inline-flex! size-6! items-center justify-center p-0!"
                    aria-label="Dismiss setup checklist"
                    onClick={() => {
                        try {
                            localStorage.setItem(storageKey, "dismissed");
                        } catch {
                            /* Dismissal still works for this visit. */
                        }
                        setDismissed(true);
                    }}
                >
                    <Icon name="x" className="size-4" />
                </Button>
            </section>
        </Card>
    );
}
