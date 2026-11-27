import { versionDate } from "./history-model.js";
export const base = "/history/";
export const viewerLink = (path) =>
    new URLSearchParams(location.search).get("viewer") === "mira"
        ? `${path}${path.includes("?") ? "&" : "?"}viewer=mira`
        : path;
export const zone = { timeZone: "America/Mexico_City" };
export const fullDate = versionDate;
export const localDate = (v) =>
    new Date(v).toLocaleDateString("en-CA", {
        ...zone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    });
export const dayName = (v) =>
    new Date(v).toLocaleDateString("en-GB", {
        ...zone,
        day: "numeric",
        month: "long",
        year: "numeric",
    });
export const clock = (v) =>
    new Date(v).toLocaleTimeString("en-GB", {
        ...zone,
        hour: "2-digit",
        minute: "2-digit",
    });
