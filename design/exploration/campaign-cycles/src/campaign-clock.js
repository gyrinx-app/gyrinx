// Calendar recurrences use the campaign's time zone, independently of the browser.
export const defaultAutoCycles = () => ({
    frequency: "weekly",
    weeks: 1,
    weekday: 1,
    monthDay: 1,
    time: "00:00",
    timeZone: "America/Mexico_City",
});
const formatters = new Map();
function parts(instant, timeZone) {
    if (!formatters.has(timeZone)) {
        if (formatters.size === 8)
            formatters.delete(formatters.keys().next().value);
        formatters.set(
            timeZone,
            new Intl.DateTimeFormat("en-CA", {
                timeZone,
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hourCycle: "h23",
            }),
        );
    }
    return Object.fromEntries(
        formatters
            .get(timeZone)
            .formatToParts(instant)
            .filter((p) => p.type !== "literal")
            .map((p) => [p.type, Number(p.value)]),
    );
}
const wall = (p) =>
    Date.UTC(
        p.year,
        p.month - 1,
        p.day,
        p.hour || 0,
        p.minute || 0,
        p.second || 0,
    );
function instantFor(day, config) {
    const [hour, minute] = config.time.split(":").map(Number);
    const target = Date.UTC(
        day.getUTCFullYear(),
        day.getUTCMonth(),
        day.getUTCDate(),
        hour,
        minute,
    );
    const offsets = new Set(
        [-86400000, 0, 86400000].map((offset) => {
            const probe = target + offset;
            return wall(parts(probe, config.timeZone)) - probe;
        }),
    );
    const candidates = [...offsets].map((offset) => target - offset);
    // First occurrence on a repeated clock hour; shift forward through a skipped hour.
    const exact = candidates.filter(
        (at) => wall(parts(at, config.timeZone)) === target,
    );
    if (exact.length) return Math.min(...exact);
    return candidates
        .filter((at) => wall(parts(at, config.timeZone)) > target)
        .sort((a, b) => a - b)[0];
}
const weekCount = (config) =>
    config.frequency === "fortnightly" ? 2 : (config.weeks ?? 1);
export function validateAutoCycles(config) {
    if (
        !config ||
        !["weekly", "fortnightly", "monthly"].includes(config.frequency) ||
        (config.frequency !== "monthly" &&
            (!Number.isSafeInteger(weekCount(config)) ||
                weekCount(config) < 1 ||
                weekCount(config) > 520)) ||
        !Number.isInteger(config.weekday) ||
        config.weekday < 0 ||
        config.weekday > 6 ||
        !Number.isInteger(config.monthDay) ||
        config.monthDay < 1 ||
        config.monthDay > 31 ||
        !/^([01]\d|2[0-3]):[0-5]\d$/.test(config.time) ||
        typeof config.timeZone !== "string" ||
        !config.timeZone.trim()
    )
        throw new Error("Choose a valid cycle interval, day and time.");
    try {
        new Intl.DateTimeFormat("en", { timeZone: config.timeZone }).format();
    } catch {
        throw new Error(
            "Enter a valid time zone, such as America/Mexico_City.",
        );
    }
}
export function autoConfig(config) {
    return {
        frequency:
            config.frequency === "fortnightly" ? "weekly" : config.frequency,
        weeks: weekCount(config),
        weekday: config.weekday,
        monthDay: config.monthDay,
        time: config.time,
        timeZone: config.timeZone,
    };
}
export function nextAutomaticRun(config, after = Date.now(), previous = null) {
    validateAutoCycles(config);
    const local = parts(previous == null ? after : previous, config.timeZone);
    let day = new Date(Date.UTC(local.year, local.month - 1, local.day));
    if (config.frequency === "monthly") {
        let month = local.month - 1 + (previous == null ? 0 : 1);
        const candidate = () =>
            new Date(
                Date.UTC(
                    local.year,
                    month,
                    Math.min(
                        config.monthDay,
                        new Date(
                            Date.UTC(local.year, month + 1, 0),
                        ).getUTCDate(),
                    ),
                ),
            );
        day = candidate();
        if (instantFor(day, config) <= after) {
            month++;
            day = candidate();
        }
    } else {
        const interval = weekCount(config) * 7;
        day.setUTCDate(
            day.getUTCDate() +
                (previous == null
                    ? (config.weekday - day.getUTCDay() + 7) % 7
                    : interval),
        );
        if (instantFor(day, config) <= after)
            day.setUTCDate(
                day.getUTCDate() + (previous == null ? 7 : interval),
            );
    }
    return new Date(instantFor(day, config)).toISOString();
}
export function automaticChangeLabel(state, { showTimeZone = true } = {}) {
    const schedule = state.autoCycles;
    if (!schedule || state.ended || state.limit !== null || !state.pattern)
        return null;
    const date = new Intl.DateTimeFormat("en-GB", {
        timeZone: schedule.timeZone,
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
    }).format(new Date(schedule.nextAt));
    return `Next cycle begins ${date}${showTimeZone ? ` (${schedule.timeZone})` : ""}`;
}
