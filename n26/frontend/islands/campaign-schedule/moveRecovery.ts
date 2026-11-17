import type { DropIntent } from "./types";

export type RetainedMove = DropIntent & { href: string; recoveryKey: string };
export function moveRecoveryKey(scheduleHref: string) {
    return `schedule-move:${scheduleHref}`;
}
export function restoreMove(key: string): RetainedMove | null {
    try {
        const value = JSON.parse(sessionStorage.getItem(key) ?? "null");
        if (
            value &&
            typeof value.sourceId === "string" &&
            typeof value.href === "string" &&
            typeof value.recoveryKey === "string" &&
            typeof value.revision === "number" &&
            value.destination &&
            typeof value.destination === "object" &&
            !Array.isArray(value.destination) &&
            Object.values(value.destination).every(
                (item) => typeof item === "string",
            )
        )
            return value;
    } catch {
        /* A malformed marker cannot resume a command. */
    }
    return null;
}
export function clearMove(key: string) {
    try {
        sessionStorage.removeItem(key);
    } catch {
        /* The command receipt still prevents duplicate writes. */
    }
}
