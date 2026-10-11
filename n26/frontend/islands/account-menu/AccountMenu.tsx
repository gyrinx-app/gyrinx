import { Fragment } from "react";
import {
    CountBadge,
    Icon,
    MenuButton,
    MenuGroup,
    MenuLink,
    MenuSeparator,
    MenuSubmit,
    ThemeChoice,
    UserLink,
    type BadgeMark,
    type ThemeChoiceProps,
} from "../../ui";

type Tone = "default" | "danger";

export type AccountMenuEntry =
    | { type: "person" }
    | { type: "separator" }
    | {
          type: "link";
          label: string;
          href: string;
          tone?: Tone;
          count?: number;
          countLabel?: string;
      }
    | { type: "group"; label: string; items: AccountMenuEntry[] }
    | ({ type: "theme" } & ThemeChoiceProps)
    | {
          type: "form";
          label: string;
          action: string;
          fields: [string, string][];
          tone?: Tone;
      };

export type AccountMenuProps = {
    /** The button's name, before any unread count is added to it. */
    label: string;
    unread: number;
    person: { name: string; href: string; badge: string | null };
    badges: Record<string, BadgeMark>;
    /** In the order they are drawn; the server decides every break. */
    items: AccountMenuEntry[];
};

// <c-n26.site.nav> draws the same button until this mounts; change both.
const TRIGGER =
    "relative inline-flex cursor-pointer items-center gap-1.5 rounded-control px-2.5 py-1.5 text-sm font-medium text-ink-600 hover:bg-ink-100 focus-ring dark:text-ink-300 dark:hover:bg-ink-800";

/** The signed-in reader's menu: who they are, their doors and the way out. */
export function AccountMenu(props: AccountMenuProps) {
    const badge = props.person.badge ? props.badges[props.person.badge] : null;
    const name = <UserLink name={props.person.name} badge={badge} />;

    function draw(entry: AccountMenuEntry, key: number) {
        switch (entry.type) {
            case "person":
                // A line rather than a row: "Your account" below it is the door.
                return (
                    <div
                        key={key}
                        className="flex items-center gap-2 px-4 pt-2 pb-1 text-sm font-medium text-ink-900 dark:text-ink-100"
                    >
                        {name}
                    </div>
                );
            case "separator":
                return <MenuSeparator key={key} />;
            case "link":
                return (
                    <MenuLink key={key} href={entry.href} tone={entry.tone}>
                        {entry.label}
                        {entry.count ? (
                            <>
                                {" "}
                                <CountBadge
                                    count={entry.count}
                                    label={entry.countLabel}
                                />
                            </>
                        ) : null}
                    </MenuLink>
                );
            case "group":
                return (
                    <MenuGroup key={key} label={entry.label}>
                        {entry.items.map(draw)}
                    </MenuGroup>
                );
            case "theme": {
                const { type: _, ...theme } = entry;
                return <ThemeChoice key={key} {...theme} />;
            }
            case "form":
                return (
                    <MenuSubmit
                        key={key}
                        action={entry.action}
                        fields={entry.fields}
                        tone={entry.tone}
                    >
                        {entry.label}
                    </MenuSubmit>
                );
        }
    }

    return (
        <MenuButton
            label={
                props.unread
                    ? `${props.label} — ${props.unread} unread notifications`
                    : props.label
            }
            title={props.label}
            className={TRIGGER}
            trigger={
                <>
                    <span className="hidden max-w-40 truncate sm:inline">
                        {name}
                    </span>
                    <span className="n26-icon-only gap-0.5">
                        <Icon
                            name="ellipsis-vertical"
                            className="size-4"
                            strokeWidth={1.7}
                        />
                        <Icon
                            name="chevron-down"
                            className="size-3"
                            strokeWidth={2.5}
                        />
                    </span>
                    <CountBadge
                        count={props.unread}
                        className="absolute -top-0.5 -right-0.5"
                    />
                </>
            }
        >
            {props.items.map((entry, key) => (
                <Fragment key={key}>{draw(entry, key)}</Fragment>
            ))}
        </MenuButton>
    );
}
