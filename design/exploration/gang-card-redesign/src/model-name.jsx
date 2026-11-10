import React, { useLayoutEffect, useRef, useState } from "react";
import { Cat, Skull, HeartPulse, LockKeyhole, Wrench } from "lucide-react";
import { Icon } from "./controls.jsx";

const statusIcons = {
    Dead: Skull,
    "In recovery": HeartPulse,
    Captured: LockKeyhole,
};

export function OwnerIcon({ owner }) {
    return (
        <span className="gang-pet-owner" title={`Attached to ${owner}`}>
            <Icon icon={Cat} size={13} />
            <span className="cm-sr">Attached to {owner}</span>
        </span>
    );
}

export function ModelProfile({ model, profileRef }) {
    const showType = model.type && model.type !== model.name;
    if (!showType && !model.status) return null;
    return (
        <div className="gang-profile" ref={profileRef}>
            {showType && (
                <span className="gang-profile-type" title={model.type}>
                    {model.type}
                </span>
            )}
            {model.status && (
                <span className="gang-status" data-status={model.status}>
                    <Icon
                        icon={statusIcons[model.status] || Wrench}
                        size={12}
                    />
                    {model.status}
                </span>
            )}
        </div>
    );
}

export function ModelName({ model, pet, owner }) {
    const copyRef = useRef(null),
        headingRef = useRef(null),
        profileRef = useRef(null);
    const [layout, setLayout] = useState({
        split: model.name.length,
        reserve: 0,
    });
    const characters = Array.from(model.name);
    const wrapped = layout.split < characters.length;

    useLayoutEffect(() => {
        const context = document.createElement("canvas").getContext("2d");
        if (!context) return;
        let cancelled = false;
        const fit = () => {
            if (cancelled) return;
            const width = copyRef.current.clientWidth;
            if (!width) return;
            context.font = getComputedStyle(headingRef.current).font;
            const reserve = profileRef.current
                ? profileRef.current.offsetWidth + 6
                : 0;
            const name = Array.from(model.name);
            let split = name.length;
            // Measure only the first line. CSS truncates the remaining text beside the profile.
            if (
                context.measureText(model.name).width + (pet ? 19 : 0) >
                    width &&
                width - reserve >
                    context.measureText("…").width + (pet ? 19 : 0)
            ) {
                let low = 0,
                    high = name.length;
                while (low < high) {
                    const middle = Math.ceil((low + high) / 2);
                    if (
                        context.measureText(name.slice(0, middle).join(""))
                            .width <= width
                    )
                        low = middle;
                    else high = middle - 1;
                }
                split = Math.max(1, low);
                for (let index = split - 1; index > 0; index--) {
                    if (/\s/.test(name[index])) {
                        split = index + 1;
                        break;
                    }
                }
            }
            setLayout((previous) =>
                previous.split === split &&
                Math.abs(previous.reserve - reserve) < 0.5
                    ? previous
                    : { split, reserve },
            );
        };
        const observer = new ResizeObserver(fit);
        observer.observe(copyRef.current);
        if (profileRef.current) observer.observe(profileRef.current);
        fit();
        document.fonts.ready.then(fit);
        return () => {
            cancelled = true;
            observer.disconnect();
        };
    }, [model.name, model.type, model.status, pet]);

    return (
        <div
            className="gang-name-copy"
            ref={copyRef}
            data-wrapped={wrapped}
            style={{ "--name-profile-reserve": `${layout.reserve}px` }}
        >
            <h2 title={model.name} ref={headingRef}>
                <span className="gang-name-line">
                    <span className="gang-name-part">
                        {characters.slice(0, layout.split).join("")}
                    </span>
                    {pet && !wrapped && <OwnerIcon owner={owner} />}
                </span>
                {wrapped && (
                    <span className="gang-name-line gang-name-continuation">
                        <span className="gang-name-part">
                            {characters.slice(layout.split).join("")}
                        </span>
                        {pet && <OwnerIcon owner={owner} />}
                    </span>
                )}
            </h2>
            <ModelProfile model={model} profileRef={profileRef} />
        </div>
    );
}
