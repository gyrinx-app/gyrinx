import cotton from "../generated/cotton.json";
import { QuickSwitcher } from "./QuickSwitcher";

export type TabLink = {
    label: string;
    href: string;
    current: boolean;
    title?: string;
};

export function TabLinks({
    tabs,
    label,
    className = "",
}: {
    tabs: TabLink[];
    label: string;
    className?: string;
}) {
    const recipe = cotton.tabLinks;
    const overflow = tabs.length > 2;
    const link = (tab: TabLink) => (
        <a
            key={tab.href}
            href={tab.href}
            title={tab.title && tab.title !== tab.label ? tab.title : undefined}
            aria-current={tab.current ? "page" : undefined}
            className={tab.current ? recipe.current : recipe.other}
        >
            <span className={recipe.label}>{tab.label}</span>
        </a>
    );
    return (
        <nav aria-label={label} className={className}>
            <div className={recipe.full}>
                {tabs.map(link)}
                <span aria-hidden="true" className={recipe.end} />
            </div>
            <div className={recipe.narrow}>
                {(overflow ? tabs.filter((tab) => tab.current) : tabs).map(
                    link,
                )}
                {overflow && (
                    <span className={recipe.overflow}>
                        <QuickSwitcher
                            heading={label}
                            menuLabel="Other tabs"
                            placeholder="Search tabs"
                            empty="No tabs match"
                            align="end"
                            triggerWords={`+${tabs.length - 1} more`}
                            items={tabs.filter((tab) => !tab.current)}
                        />
                    </span>
                )}
                <span aria-hidden="true" className={recipe.end} />
            </div>
        </nav>
    );
}
