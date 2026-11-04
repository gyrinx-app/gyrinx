import type { ComponentProps } from "react";
import { useQueryHref } from "../../runtime/useQueryHref";
import {
    ButtonLink,
    type ButtonLinkSize,
    type ButtonLinkVariant,
    Icon,
} from "../../ui";

export type ScenarioLinkProps = {
    url: string;
    label: string;
    ariaLabel: string;
    size: ButtonLinkSize;
    variant: ButtonLinkVariant;
    icon: ComponentProps<typeof Icon>["name"] | "";
    queryKeys: string[];
};

export function ScenarioLink(props: ScenarioLinkProps) {
    const href = useQueryHref(props.url, props.queryKeys);
    return (
        <ButtonLink
            href={href}
            size={props.size}
            variant={props.variant}
            aria-label={props.ariaLabel}
        >
            {props.icon ? (
                <span className="flex items-center justify-center gap-2">
                    <Icon name={props.icon} className="size-4" />
                    {props.label}
                </span>
            ) : (
                props.label
            )}
        </ButtonLink>
    );
}
