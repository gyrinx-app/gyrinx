import {
    Info,
    TriangleAlert,
    MessageCircleQuestionMark,
    FileDown,
    LibraryBig,
    MailPen,
    Lightbulb,
    CircleCheck,
    BookOpen,
    ArrowDownWideNarrow,
    Lighthouse,
} from "lucide-react";
import cotton from "./cotton.json";
import schema from "./callout-schema.json";
import iconNames from "./lucide-icons.json";
import { cleanRich } from "./rich-body";
export const icons = {
    info: Info,
    "triangle-alert": TriangleAlert,
    "message-circle-question-mark": MessageCircleQuestionMark,
    "file-down": FileDown,
    "library-big": LibraryBig,
    "mail-pen": MailPen,
    lightbulb: Lightbulb,
    "circle-check": CircleCheck,
    "book-open": BookOpen,
    "arrow-down-wide-narrow": ArrowDownWideNarrow,
    lighthouse: Lighthouse,
};
export const hasIcon = (name) => Object.hasOwn(iconNames, name);
export const types = [
    ["info", "Information", "triangle-alert", "Warning", "Focus topic"],
    [
        "expanding-info",
        "Expanding information",
        "arrow-down-wide-narrow",
        "Info",
        "Focus topic",
    ],
    [
        "carousel",
        "FAQ carousel",
        "message-circle-question-mark",
        "FAQ",
        "Getting started",
    ],
    ["download", "Download", "file-down", "File", "Text file"],
    [
        "link-cluster",
        "Related links",
        "library-big",
        "Read more",
        "Related reading",
    ],
    ["mail-link", "Email", "mail-pen", "Get in touch", "Design systems"],
    [
        "example",
        "Expandable example",
        "lighthouse",
        "Need help?",
        "Focus topic",
    ],
];
export function freshCallout(type) {
    const row = types.find((row) => row[0] === type) || types[0];
    return {
        type: row[0],
        colour: "default",
        icon: row[2],
        label: row[3],
        eyebrow: row[4],
        striped: false,
        glow: false,
        body:
            type === "link-cluster"
                ? ""
                : type === "example"
                  ? "Here is a concise worked example. Start with the central idea, show one concrete application, and end with the result the reader should expect."
                  : "Write the callout text here.",
        detail: "Add the additional information revealed when this callout expands.",
        bodyRich: null,
        detailRich: null,
        href: "",
        recipient: "",
        links: [{ id: "link-0", label: "Related reading", href: "" }],
        slides: [
            {
                bodyRich: null,
                eyebrow: "Getting started",
                body: "How do I get started? Pick a topic and follow its setup guide.",
            },
            {
                bodyRich: null,
                eyebrow: "Customization",
                body: "Can I customize the component? Change its theme, label, icon, eyebrow and content.",
            },
            {
                bodyRich: null,
                eyebrow: "Accessibility",
                body: "Swipe, scroll, use the chevrons or choose a square position control.",
            },
            {
                bodyRich: null,
                eyebrow: "Support",
                body: "Where can I find help? Contact support.",
            },
        ],
    };
}
function cleanString(value, limit = 12000) {
    return typeof value === "string" ? value.slice(0, limit) : "";
}
export function normalizeCallout(raw) {
    if (!raw || !types.some((row) => row[0] === raw.type))
        throw Error("Unknown callout type");
    const base = freshCallout(raw.type);
    const seen = new Set();
    const linkID = (value, index) => {
        let id = cleanString(value, 100) || `link-${index}`;
        while (seen.has(id)) id += `-${index}`;
        seen.add(id);
        return id;
    };
    return {
        ...base,
        colour:
            raw.colour === "default" ||
            cotton.colours.some((c) => c.name.toLowerCase() === raw.colour)
                ? raw.colour
                : "default",
        icon: hasIcon(raw.icon) ? raw.icon : base.icon,
        striped: raw.striped === true,
        glow: raw.glow === true,
        label: cleanString(raw.label, schema.textLimits.label),
        eyebrow: cleanString(raw.eyebrow, schema.textLimits.eyebrow),
        body: cleanString(raw.body, schema.textLimits.body),
        detail: cleanString(raw.detail, schema.textLimits.detail),
        bodyRich: cleanRich(raw.bodyRich),
        detailRich: cleanRich(raw.detailRich),
        href: cleanString(raw.href, schema.textLimits.href),
        recipient: cleanString(raw.recipient, schema.textLimits.recipient),
        links: (Array.isArray(raw.links) ? raw.links : base.links)
            .slice(0, schema.collections.links.limit)
            .map((link, index) => ({
                id: linkID(link?.id, index),
                label: cleanString(
                    link?.label,
                    schema.collections.links.fields.label,
                ),
                href: cleanString(
                    link?.href,
                    schema.collections.links.fields.href,
                ),
            })),
        slides: (Array.isArray(raw.slides) && raw.slides.length
            ? raw.slides
            : base.slides
        )
            .slice(0, schema.collections.slides.limit)
            .map((slide) => ({
                eyebrow: cleanString(
                    slide?.eyebrow,
                    schema.collections.slides.fields.eyebrow,
                ),
                body: cleanString(
                    slide?.body,
                    schema.collections.slides.fields.body,
                ),
                bodyRich: cleanRich(slide?.bodyRich),
            })),
    };
}

// Keep portable settings concise: only persist fields relevant to this kind of block.
export function serializeCallout(config) {
    const fields = [
        "type",
        "colour",
        "icon",
        "label",
        "eyebrow",
        "striped",
        "glow",
    ];
    if (config.type === "carousel") fields.push("slides");
    else fields.push("body", "bodyRich");
    if (config.type === "expanding-info") fields.push("detail", "detailRich");
    if (config.type === "download") fields.push("href");
    if (config.type === "mail-link") fields.push("recipient");
    if (config.type === "link-cluster") fields.push("links");
    return JSON.stringify(
        Object.fromEntries(
            fields
                .filter((key) => config[key] != null)
                .map((key) => [key, config[key]]),
        ),
    );
}
