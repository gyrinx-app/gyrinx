import React from "react";
import templates from "./campaign-base.json";

const names = {
    class: "className",
    popovertarget: "popoverTarget",
    popovertargetaction: "popoverTargetAction",
    for: "htmlFor",
    tabindex: "tabIndex",
    viewbox: "viewBox",
    "stroke-width": "strokeWidth",
    "stroke-linecap": "strokeLinecap",
    "stroke-linejoin": "strokeLinejoin",
    "fill-rule": "fillRule",
    "clip-rule": "clipRule",
    "stroke-dasharray": "strokeDasharray",
    colspan: "colSpan",
    rowspan: "rowSpan",
    readonly: "readOnly",
    autofocus: "autoFocus",
    datetime: "dateTime",
};
const boolean = new Set([
    "disabled",
    "checked",
    "selected",
    "multiple",
    "required",
    "hidden",
    "readOnly",
    "autoFocus",
]);
const replace = (value, bindings) =>
    String(value).replace(/__([A-Z_]+)__/g, (_, key) =>
        String(bindings[key] ?? ""),
    );
function styles(value) {
    return Object.fromEntries(
        value
            .split(";")
            .filter((v) => v.includes(":"))
            .map((v) => {
                const at = v.indexOf(":");
                const key = v.slice(0, at).trim();
                return [
                    key.startsWith("--")
                        ? key
                        : key.replace(/-([a-z])/g, (_, letter) =>
                              letter.toUpperCase(),
                          ),
                    v.slice(at + 1).trim(),
                ];
            }),
    );
}
export function Cotton({
    name,
    bindings = {},
    slots = {},
    tree,
    rootProps = {},
}) {
    function draw(node, key) {
        if (typeof node === "string") return replace(node, bindings);
        if (node.attrs["data-campaign-slot"])
            return (
                <React.Fragment key={key}>
                    {slots[node.attrs["data-campaign-slot"]] ?? null}
                </React.Fragment>
            );
        if (
            node.tag === "script" ||
            node.tag === "noscript" ||
            "x-show" in node.attrs ||
            "x-cloak" in node.attrs ||
            node.attrs.role === "tooltip"
        )
            return null;
        const props = { key };
        for (const [attr, raw] of Object.entries(node.attrs)) {
            if (
                attr.startsWith("x-") ||
                attr.startsWith("@") ||
                attr.startsWith(":") ||
                attr.startsWith("hx-") ||
                attr.startsWith("on")
            )
                continue;
            const name = names[attr] || attr,
                value = replace(raw ?? "", bindings);
            if (name === "style") props.style = styles(value);
            else props[name] = boolean.has(name) ? true : value;
        }
        if (key === (name || "cotton")) Object.assign(props, rootProps);
        const children = node.children.map((child, i) =>
            draw(child, `${key}.${i}`),
        );
        return React.createElement(
            node.tag === "fragment" ? React.Fragment : node.tag,
            props,
            ...children,
        );
    }
    return draw(tree || templates[name], name || "cotton");
}
