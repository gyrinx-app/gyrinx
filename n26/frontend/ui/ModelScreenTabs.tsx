import cotton from "../generated/cotton.json";

export type ModelScreenTab = { label: string; href: string; current: boolean };

export function ModelScreenTabs({
    tabs,
    className = "mt-3",
}: {
    tabs: ModelScreenTab[];
    className?: string;
}) {
    return (
        <nav aria-label="This model's screens" className={className}>
            <div className={cotton.modelCard.tabStrip}>
                {tabs.map((tab) => (
                    <a
                        key={tab.href}
                        href={tab.href}
                        aria-current={tab.current ? "page" : undefined}
                        className={
                            cotton.modelCard.tab[
                                String(tab.current) as "true" | "false"
                            ]
                        }
                    >
                        <span className="truncate">{tab.label}</span>
                    </a>
                ))}
                <span aria-hidden="true" className={cotton.modelCard.tabEnd} />
            </div>
        </nav>
    );
}
