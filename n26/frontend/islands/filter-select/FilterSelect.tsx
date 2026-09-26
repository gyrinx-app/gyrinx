import {
    useEffect,
    useId,
    useLayoutEffect,
    useRef,
    useState,
    type KeyboardEvent,
} from "react";
import { Icon, Input } from "../../ui";

type SelectOption = {
    value: string;
    label: string;
    selected: boolean;
    disabled: boolean;
};

export type FilterSelectProps = {
    name: string;
    id: string;
    multiple: boolean;
    required: boolean;
    disabled: boolean;
    attrs: Record<string, string>;
    options: SelectOption[];
    placeholder: string;
    empty: string;
};

export function FilterSelect({
    name,
    id,
    multiple,
    required,
    disabled,
    attrs,
    options,
    placeholder,
    empty,
}: FilterSelectProps) {
    const generatedId = useId();
    const listId = `${generatedId}-list`;
    const root = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const search = useRef<HTMLInputElement>(null);
    const select = useRef<HTMLSelectElement>(null);
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState("");
    const [active, setActive] = useState(-1);
    const [selected, setSelected] = useState(
        () =>
            new Set(
                options.flatMap((option, index) =>
                    option.selected ? [index] : [],
                ),
            ),
    );

    function syncSelect(indices: Set<number>) {
        if (!select.current) return;
        Array.from(select.current.options).forEach((option, index) => {
            option.selected = indices.has(index);
        });
    }

    useLayoutEffect(() => syncSelect(selected), [selected]);

    useEffect(() => {
        if (!open) return;
        const frame = requestAnimationFrame(() => search.current?.focus());

        function dismiss(event: MouseEvent) {
            if (!root.current?.contains(event.target as Node)) close(false);
        }

        function escape(event: globalThis.KeyboardEvent) {
            if (event.key === "Escape") close(true);
        }

        document.addEventListener("click", dismiss);
        document.addEventListener("keydown", escape);
        return () => {
            cancelAnimationFrame(frame);
            document.removeEventListener("click", dismiss);
            document.removeEventListener("keydown", escape);
        };
    }, [open]);

    useLayoutEffect(() => {
        if (active < 0) return;
        root.current
            ?.querySelector<HTMLElement>('[data-active="true"]')
            ?.scrollIntoView?.({ block: "nearest" });
    }, [active]);

    const wanted = query.trim().toLowerCase();
    const filtered = options
        .map((option, index) => ({ ...option, index }))
        .filter(
            (option) =>
                !option.disabled &&
                (!wanted || option.label.toLowerCase().includes(wanted)),
        );
    const chosen = options.filter(
        (option, index) => selected.has(index) && option.value,
    );
    const summary = chosen.map((option) => option.label).join(", ");
    const writtenPlaceholder = options.find(
        (option) => !option.value && option.disabled,
    )?.label;

    function show() {
        if (!disabled) setOpen(true);
    }

    function close(focusTrigger: boolean) {
        setOpen(false);
        setQuery("");
        setActive(-1);
        if (focusTrigger) trigger.current?.focus();
    }

    function choose(index: number) {
        const next = new Set(selected);
        if (multiple) {
            if (next.has(index)) next.delete(index);
            else next.add(index);
        } else {
            next.clear();
            next.add(index);
        }
        syncSelect(next);
        setSelected(next);
        select.current?.dispatchEvent(new Event("change", { bubbles: true }));
        if (!multiple) close(true);
    }

    function move(step: number) {
        if (!filtered.length) {
            setActive(-1);
            return;
        }
        const at = filtered.findIndex((option) => option.index === active);
        const to =
            at < 0
                ? step > 0
                    ? 0
                    : filtered.length - 1
                : (at + step + filtered.length) % filtered.length;
        setActive(filtered[to].index);
    }

    function searchKeys(event: KeyboardEvent<HTMLInputElement>) {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            move(event.key === "ArrowDown" ? 1 : -1);
        } else if (event.key === "Enter") {
            event.preventDefault();
            if (active >= 0) choose(active);
        } else if (event.key === "Escape") {
            event.stopPropagation();
            if (query) {
                setQuery("");
                setActive(-1);
            } else {
                close(true);
            }
        } else if (event.key === "Tab") {
            close(false);
        }
    }

    return (
        <div ref={root} className="relative">
            <select
                ref={select}
                {...attrs}
                hidden
                name={name}
                multiple={multiple}
                required={required}
                disabled={disabled}
                aria-hidden="true"
                tabIndex={-1}
            >
                {options.map((option, index) => (
                    <option
                        key={index}
                        value={option.value}
                        disabled={option.disabled}
                    >
                        {option.label}
                    </option>
                ))}
            </select>
            <button
                ref={trigger}
                id={id || generatedId}
                type="button"
                disabled={disabled}
                aria-haspopup="listbox"
                aria-expanded={open}
                aria-controls={open ? listId : undefined}
                onClick={() => (open ? close(false) : show())}
                onKeyDown={(event) => {
                    if (event.key !== "ArrowDown") return;
                    event.preventDefault();
                    show();
                }}
                className="relative w-full appearance-none rounded-control border border-ink-300 bg-[var(--color-input-bg)] px-3 py-2 pr-10 text-left text-sm shadow-[var(--shadow-input)] transition-colors focus-ring disabled:opacity-50 dark:border-ink-700"
            >
                <span
                    className={`block truncate ${
                        chosen.length
                            ? "text-ink-900 dark:text-ink-100"
                            : "text-ink-400 dark:text-ink-500"
                    }`}
                >
                    {chosen.length
                        ? summary
                        : writtenPlaceholder || "Nothing chosen"}
                </span>
                <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-ink-400">
                    <Icon name="chevron-down" />
                </span>
            </button>
            {open && (
                <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-box border border-box-border bg-white shadow-lg dark:bg-ink-900">
                    <div className="border-b border-box-border p-2">
                        <div className="relative">
                            <span className="pointer-events-none absolute inset-y-0 left-3 z-10 flex items-center text-ink-400">
                                <Icon name="search" />
                            </span>
                            <Input
                                ref={search}
                                type="search"
                                value={query}
                                placeholder={placeholder}
                                aria-label={placeholder}
                                autoComplete="off"
                                role="combobox"
                                aria-expanded={open}
                                aria-controls={listId}
                                aria-activedescendant={
                                    active >= 0
                                        ? `${generatedId}-option-${active}`
                                        : undefined
                                }
                                className="!pl-9"
                                onChange={(event) => {
                                    setQuery(event.target.value);
                                    setActive(-1);
                                }}
                                onKeyDown={searchKeys}
                            />
                        </div>
                    </div>
                    <div
                        id={listId}
                        role="listbox"
                        aria-multiselectable={multiple || undefined}
                        className="max-h-72 overflow-y-auto py-1"
                    >
                        {filtered.map((option) => (
                            <div
                                key={option.index}
                                id={`${generatedId}-option-${option.index}`}
                                role="option"
                                data-active={option.index === active}
                                aria-selected={selected.has(option.index)}
                                onClick={() => choose(option.index)}
                                onMouseMove={() => setActive(option.index)}
                                className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm text-ink-900 dark:text-ink-100 ${
                                    option.index === active
                                        ? "bg-ink-100 dark:bg-ink-800"
                                        : ""
                                }`}
                            >
                                <span className="flex size-4 shrink-0 items-center text-accent-text">
                                    {selected.has(option.index) && (
                                        <Icon name="check" />
                                    )}
                                </span>
                                <span className="min-w-0 flex-1 truncate">
                                    {option.label}
                                </span>
                            </div>
                        ))}
                        {!filtered.length && (
                            <p className="px-3 py-4 text-center text-sm text-muted">
                                {empty}
                            </p>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
