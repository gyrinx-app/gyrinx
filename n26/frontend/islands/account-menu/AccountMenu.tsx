import { Fragment } from "react";
import {
    CountBadge,
    MenuButton,
    MenuGroup,
    MenuLink,
    MenuSeparator,
    MenuSubmit,
    SiteNavAccount,
    siteNavAccountButton,
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
    /** Accessible button label before the unread count is appended. */
    label: string;
    unread: number;
    /** Pluralised unread count for the accessible button label. */
    unreadText: string;
    person: { name: string; badge: string | null };
    badges: Record<string, BadgeMark>;
    /** Entries and separators in server-provided order. */
    items: AccountMenuEntry[];
};

/**
 * Show account navigation, theme settings and sign-out controls for the
 * signed-in user.
 */
export function AccountMenu(props: AccountMenuProps) {
    const badge = props.person.badge ? props.badges[props.person.badge] : null;
    const name = <UserLink name={props.person.name} badge={badge} />;

    function draw(entry: AccountMenuEntry, key: number) {
        switch (entry.type) {
            case "person":
                // Display the name outside keyboard navigation; the
                // separate account link is selectable.
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
                    ? `${props.label} — ${props.unreadText}`
                    : props.label
            }
            title={props.label}
            className={siteNavAccountButton}
            trigger={<SiteNavAccount name={name} unread={props.unread} />}
        >
            {props.items.map((entry, key) => (
                <Fragment key={key}>{draw(entry, key)}</Fragment>
            ))}
        </MenuButton>
    );
}
