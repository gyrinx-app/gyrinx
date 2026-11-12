import { Icon, MenuButton, MenuLink } from "../../ui";

export type ProfileSortProps = {
    choices: { label: string; href: string; current: boolean }[];
};

export function ProfileSort({ choices }: ProfileSortProps) {
    const selected = choices.find((choice) => choice.current);
    return (
        <MenuButton
            label="Sort gangs"
            size="sm"
            trigger={
                <span className="inline-flex items-center gap-2">
                    <span>{selected?.label}</span>
                    <Icon name="chevron-down" />
                </span>
            }
        >
            {choices.map((choice) => (
                <MenuLink key={choice.href} href={choice.href}>
                    <span className="flex items-center justify-between gap-3">
                        {choice.label}
                        {choice.current && (
                            <Icon name="check" label="Selected" />
                        )}
                    </span>
                </MenuLink>
            ))}
        </MenuButton>
    );
}
