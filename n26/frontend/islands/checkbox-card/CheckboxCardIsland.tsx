import { memo, useLayoutEffect, useRef, useState } from "react";
import { CheckboxCard } from "../../ui";

export type CheckboxCardIslandProps = {
    name: string;
    value: string;
    checked: boolean;
    label: string;
    description: string;
    className: string;
    /** The server-drawn checkbox had focus when the island replaced it. */
    restoreFocus?: boolean;
    /** Header slot, detached from the fallback before React cleared the host. */
    metaNodes?: ChildNode[];
    /** Body slot, detached the same way so nested controls keep their values. */
    bodyNodes?: ChildNode[];
};

const AdoptedNodes = memo(function AdoptedNodes({
    nodes,
}: {
    nodes: ChildNode[];
}) {
    const ref = useRef<HTMLSpanElement>(null);
    useLayoutEffect(() => {
        const parent = ref.current;
        if (!parent) return;
        for (const node of nodes) parent.appendChild(node);
    }, [nodes]);
    return <span ref={ref} className="contents" />;
});

export function CheckboxCardIsland({
    name,
    value,
    checked: initiallyChecked,
    label,
    description,
    className,
    restoreFocus = false,
    metaNodes = [],
    bodyNodes = [],
}: CheckboxCardIslandProps) {
    const frame = useRef<HTMLDivElement>(null);
    const [checked, setChecked] = useState(initiallyChecked);
    useLayoutEffect(() => {
        if (!restoreFocus) return;
        frame.current
            ?.querySelector<HTMLInputElement>("label input[type='checkbox']")
            ?.focus();
    }, [restoreFocus]);
    return (
        <div ref={frame} className="contents">
            <CheckboxCard
                checked={checked}
                onCheckedChange={setChecked}
                label={label}
                description={description || undefined}
                className={className}
                name={name}
                value={value}
                meta={
                    metaNodes.length ? (
                        <AdoptedNodes nodes={metaNodes} />
                    ) : undefined
                }
            >
                {bodyNodes.length ? <AdoptedNodes nodes={bodyNodes} /> : null}
            </CheckboxCard>
        </div>
    );
}
