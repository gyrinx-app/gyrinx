import { useState } from "react";
import {
    ActionBar,
    Badge,
    Button,
    FilterMenu,
    Link,
    RangeMenu,
    SearchBar,
    Toggle,
    UserLink,
    type BadgeMark,
    type FilterOption,
} from "../../ui";

type Gang = {
    pk: string;
    name: string;
    href: string;
    unlimited: boolean;
    budgetHref: string;
    /** The owner's username, which the player filter matches. */
    owner: string;
    /** The owner as the arbitrator's rows name them; absent for a player. */
    ownerLink: { name: string; href: string; badge: string | null } | null;
    wealth: number;
    /** Lower-case name and owner, which the search matches. */
    search: string;
    playing: boolean;
};

export type CampaignGangPickerProps = {
    gangs: Gang[];
    badges: Record<string, BadgeMark>;
    playerOptions: FilterOption[];
    /** The richest gang's wealth: the top of the wealth range. */
    wealthCeiling: number;
};

// A native range reaches only multiples of its step, so the top rounds up
// to one; otherwise the richest gang could not be brought back in.
const WEALTH_STEP = 50;

/**
 * The gangs a campaign can take, narrowed by name, player, wealth and
 * whether they already play. Each row's Add submits the surrounding form.
 */
export function CampaignGangPicker(props: CampaignGangPickerProps) {
    const wealthTop =
        Math.ceil(props.wealthCeiling / WEALTH_STEP) * WEALTH_STEP;
    const [query, setQuery] = useState("");
    const [people, setPeople] = useState<string[] | null>(null);
    const [wealth, setWealth] = useState<[number, number]>([0, wealthTop]);
    const [hidePlaying, setHidePlaying] = useState(true);
    const needle = query.trim().toLowerCase();
    const shown = props.gangs.filter(
        (gang) =>
            !(hidePlaying && gang.playing) &&
            (people === null || people.includes(gang.owner)) &&
            gang.wealth >= wealth[0] &&
            gang.wealth <= wealth[1] &&
            (!needle || gang.search.includes(needle)),
    );
    const total = props.gangs.length;

    return (
        <>
            <SearchBar value={query} onChange={setQuery} label="Search gangs" />
            <ActionBar surface={false} spaced={false}>
                {props.playerOptions.length > 0 && (
                    <FilterMenu
                        label="Player"
                        options={props.playerOptions}
                        onApply={setPeople}
                    />
                )}
                {props.wealthCeiling > 0 && (
                    <RangeMenu
                        label="Wealth"
                        min={0}
                        max={wealthTop}
                        step={WEALTH_STEP}
                        suffix="¢"
                        atMaxLabel="Any"
                        value={wealth}
                        onChange={setWealth}
                    />
                )}
                <Toggle
                    label="Hide gangs already in a campaign"
                    checked={hidePlaying}
                    onCheckedChange={setHidePlaying}
                />
            </ActionBar>
            <p className="text-sm text-muted">
                <span className="font-semibold text-ink-900 tabular-nums dark:text-ink-100">
                    {shown.length}
                </span>{" "}
                of {total} gang{total === 1 ? "" : "s"}
            </p>
            <ul className="flex flex-col">
                {shown.map((gang) => (
                    <li
                        key={gang.pk}
                        className="flex items-center gap-3 border-b border-box-border/50 py-2 last:border-b-0"
                    >
                        <div className="min-w-0 flex-1">
                            <Link
                                href={gang.href}
                                tone="current"
                                className="text-base font-semibold"
                            >
                                {gang.name}
                            </Link>
                            {gang.ownerLink && (
                                <span className="ml-1 text-sm text-muted">
                                    <UserLink
                                        name={gang.ownerLink.name}
                                        href={gang.ownerLink.href}
                                        badge={
                                            gang.ownerLink.badge
                                                ? props.badges[
                                                      gang.ownerLink.badge
                                                  ]
                                                : null
                                        }
                                    />
                                </span>
                            )}
                            {gang.unlimited && (
                                <>
                                    <p className="mt-1 text-sm text-muted">
                                        Unlimited credits: credit balances are
                                        not tracked.
                                    </p>
                                    {gang.budgetHref && (
                                        <Link
                                            href={gang.budgetHref}
                                            className="text-sm"
                                        >
                                            Review credits budget
                                        </Link>
                                    )}
                                </>
                            )}
                        </div>
                        {gang.playing && (
                            <span className="shrink-0">
                                <Badge color="ink">In a campaign</Badge>
                            </span>
                        )}
                        <span className="shrink-0 text-sm tabular-nums text-muted">
                            {gang.wealth}¢
                        </span>
                        {!gang.playing && (
                            <Button
                                type="submit"
                                name="gang"
                                value={gang.pk}
                                size="sm"
                                variant="success"
                                className="shrink-0"
                            >
                                Add
                            </Button>
                        )}
                    </li>
                ))}
            </ul>
            {shown.length === 0 && (
                <p className="py-6 text-center text-sm text-muted">
                    No gangs match that.
                </p>
            )}
        </>
    );
}
