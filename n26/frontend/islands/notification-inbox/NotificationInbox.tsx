import {
    createElement,
    useId,
    useRef,
    useState,
    useEffect,
    type CSSProperties,
    type ReactNode,
} from "react";
import {
    ActionBar,
    Badge,
    Button,
    ButtonLink,
    Field,
    Input,
    Link,
    NativeSelect,
} from "../../ui";

type RichNode =
    | string
    | {
          tag: string;
          attrs: Record<string, string | CSSProperties>;
          children: RichNode[];
      };
type Notification = {
    id: string;
    subject: string;
    content: RichNode[];
    sender: string;
    system: boolean;
    created: string;
    age: string;
    type: string;
    read: boolean;
    archived: boolean;
    openUrl: string;
    actions: Record<string, string>;
};
export type NotificationInboxProps = {
    rows: Notification[];
    filters: { bucket: string; status: string; type: string; q: string };
    typeChoices: Array<{ value: string; label: string }>;
    csrfToken: string;
    inboxUrl: string;
    bulkUrl: string;
    returnUrl: string;
    unreadCount: number;
    page: number;
    pages: number;
    previousUrl: string;
    nextUrl: string;
};
function richText(nodes: RichNode[]): ReactNode[] {
    return nodes.map((node, key) =>
        typeof node === "string"
            ? node
            : createElement(
                  node.tag,
                  { ...node.attrs, key },
                  ...richText(node.children),
              ),
    );
}

export function NotificationInbox(props: NotificationInboxProps) {
    const { filters, csrfToken, bulkUrl, inboxUrl } = props;
    const id = useId();
    const [rows, setRows] = useState(props.rows);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [unreadCount, setUnreadCount] = useState(props.unreadCount);
    const [pending, setPending] = useState(false);
    const locked = useRef(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const selectAll = useRef<HTMLInputElement>(null);
    const allSelected =
        rows.length > 0 && rows.every((row) => selected.has(row.id));
    useEffect(() => {
        if (selectAll.current)
            selectAll.current.indeterminate = selected.size > 0 && !allSelected;
    }, [selected, allSelected]);

    async function act(action: string, targets: Notification[], all = false) {
        if (locked.current) return;
        locked.current = true;
        setPending(true);
        setError("");
        setNotice("");
        const body = new URLSearchParams({
            action,
            next: props.returnUrl,
            ...filters,
        });
        if (all) {
            body.set("all", "1");
            body.set("bucket", "inbox");
            body.set("status", "unread");
            body.set("type", "");
            body.set("q", "");
        } else targets.forEach((row) => body.append("ids", row.id));
        try {
            const rowAction =
                targets.length === 1 &&
                ["read", "unread", "unarchive"].includes(action);
            const response = await fetch(
                rowAction ? targets[0].actions[action] : bulkUrl,
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRFToken": csrfToken,
                        Accept: "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    body,
                },
            );
            if (
                !response.ok ||
                response.redirected ||
                response.headers
                    .get("Content-Type")
                    ?.includes("application/json") !== true
            )
                throw new Error("request");
            await response.json();
            const affected = new Set(targets.map((row) => row.id));
            const reading = action === "read" || action === "mark_read";
            const unreading = action === "unread" || action === "mark_unread";
            const archiving = action === "archive" || action === "unarchive";
            const updated = rows.map((row) =>
                affected.has(row.id)
                    ? {
                          ...row,
                          read: reading ? true : unreading ? false : row.read,
                          archived: archiving
                              ? action === "archive"
                              : row.archived,
                      }
                    : row,
            );
            setRows(
                updated.filter((row) => {
                    if (affected.has(row.id) && action === "delete")
                        return false;
                    return (
                        row.archived === (filters.bucket === "archived") &&
                        (filters.status === "all" ||
                            row.read === (filters.status === "read"))
                    );
                }),
            );
            if (all && reading) setUnreadCount(0);
            else
                setUnreadCount((count) =>
                    Math.max(
                        0,
                        count +
                            targets.reduce((delta, row) => {
                                if (row.archived && action !== "unarchive")
                                    return delta;
                                if (
                                    !row.read &&
                                    (reading ||
                                        action === "archive" ||
                                        action === "delete")
                                )
                                    return delta - 1;
                                if (
                                    (row.read && unreading) ||
                                    (row.archived &&
                                        !row.read &&
                                        action === "unarchive")
                                )
                                    return delta + 1;
                                return delta;
                            }, 0),
                    ),
                );
            setSelected(new Set());
            setNotice("Notifications updated.");
        } catch {
            setError(
                "The notifications could not be updated. Reload the page or try again.",
            );
        } finally {
            locked.current = false;
            setPending(false);
        }
    }
    const selection = rows.filter((row) => selected.has(row.id));
    const bucketUrl = (bucket: string) =>
        `${inboxUrl}?${new URLSearchParams({ ...filters, bucket })}`;
    return (
        <div className="space-y-4" aria-busy={pending}>
            <ActionBar
                className="flex-wrap"
                trailing={
                    unreadCount > 0 && (
                        <Button
                            disabled={pending}
                            onClick={() =>
                                void act(
                                    "mark_read",
                                    rows.filter((row) => !row.archived),
                                    true,
                                )
                            }
                        >
                            Mark inbox read
                        </Button>
                    )
                }
            >
                <ButtonLink
                    href={bucketUrl("inbox")}
                    variant={filters.bucket === "inbox" ? "primary" : "default"}
                    aria-current={
                        filters.bucket === "inbox" ? "page" : undefined
                    }
                >
                    Inbox
                </ButtonLink>
                <ButtonLink
                    href={bucketUrl("archived")}
                    variant={
                        filters.bucket === "archived" ? "primary" : "default"
                    }
                    aria-current={
                        filters.bucket === "archived" ? "page" : undefined
                    }
                >
                    Archived
                </ButtonLink>
            </ActionBar>
            <form
                method="get"
                action={inboxUrl}
                className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem_10rem_auto] sm:items-end"
            >
                <input type="hidden" name="bucket" value={filters.bucket} />
                <Field htmlFor={`${id}-search`} label="Search notifications">
                    <Input type="search" name="q" defaultValue={filters.q} />
                </Field>
                <Field htmlFor={`${id}-status`} label="Status">
                    <NativeSelect name="status" defaultValue={filters.status}>
                        <option value="all">All</option>
                        <option value="unread">Unread</option>
                        <option value="read">Read</option>
                    </NativeSelect>
                </Field>
                <Field htmlFor={`${id}-type`} label="Type">
                    <NativeSelect name="type" defaultValue={filters.type}>
                        <option value="">All types</option>
                        {props.typeChoices.map((choice) => (
                            <option key={choice.value} value={choice.value}>
                                {choice.label}
                            </option>
                        ))}
                    </NativeSelect>
                </Field>
                <Button type="submit">Apply</Button>
            </form>
            {error && (
                <p
                    role="alert"
                    className="text-sm text-red-600 dark:text-red-400"
                >
                    {error}
                </p>
            )}
            {notice && (
                <p role="status" className="text-sm text-muted">
                    {notice}
                </p>
            )}
            {rows.length > 0 ? (
                <>
                    <div
                        role="group"
                        aria-label="Selected notifications"
                        className="flex flex-wrap items-center gap-3 rounded-box border border-box-border bg-box px-4 py-2"
                    >
                        <label className="flex items-center gap-2 text-sm">
                            <input
                                ref={selectAll}
                                type="checkbox"
                                checked={allSelected}
                                disabled={pending}
                                onChange={(event) =>
                                    setSelected(
                                        new Set(
                                            event.target.checked
                                                ? rows.map((row) => row.id)
                                                : [],
                                        ),
                                    )
                                }
                                className="size-4 accent-accent"
                            />
                            Select this page
                        </label>
                        <span className="text-sm text-muted">
                            {selected.size} selected
                        </span>
                        {(
                            [
                                ["mark_read", "Mark read"],
                                ["mark_unread", "Mark unread"],
                                ["archive", "Archive"],
                                ["delete", "Delete"],
                            ] as const
                        ).map(([action, label]) => (
                            <Button
                                key={action}
                                variant={
                                    action === "delete" ? "text-danger" : "text"
                                }
                                size="sm"
                                disabled={pending || selection.length === 0}
                                onClick={() => void act(action, selection)}
                            >
                                {label}
                            </Button>
                        ))}
                    </div>
                    <ul className="divide-y divide-box-border rounded-box border border-box-border bg-box">
                        {rows.map((row) => (
                            <li
                                key={row.id}
                                className={`flex gap-3 border-l-4 p-4 ${row.read ? "border-l-transparent" : "border-l-accent"}`}
                            >
                                <input
                                    type="checkbox"
                                    aria-label={`Select: ${row.subject}`}
                                    className="mt-1 size-4 shrink-0 accent-accent"
                                    checked={selected.has(row.id)}
                                    disabled={pending}
                                    onChange={(event) => {
                                        const next = new Set(selected);
                                        if (event.target.checked)
                                            next.add(row.id);
                                        else next.delete(row.id);
                                        setSelected(next);
                                    }}
                                />
                                <div className="min-w-0 flex-1 space-y-2">
                                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                                        <span>{row.sender}</span>
                                        <span aria-hidden="true">·</span>
                                        <time dateTime={row.created}>
                                            {row.age}
                                        </time>
                                        <Badge>{row.type}</Badge>
                                        {!row.read && <Badge>Unread</Badge>}
                                    </div>
                                    <h3 className="font-semibold">
                                        {row.openUrl ? (
                                            <Link href={row.openUrl}>
                                                {row.subject}
                                            </Link>
                                        ) : (
                                            row.subject
                                        )}
                                    </h3>
                                    {row.content.length > 0 && (
                                        <div className="rich-text break-words text-sm text-muted">
                                            {richText(row.content)}
                                        </div>
                                    )}
                                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                                        <Button
                                            variant="text"
                                            size="sm"
                                            disabled={pending}
                                            onClick={() =>
                                                void act(
                                                    row.read
                                                        ? "unread"
                                                        : "read",
                                                    [row],
                                                )
                                            }
                                        >
                                            {row.read
                                                ? "Mark unread"
                                                : "Mark read"}
                                        </Button>
                                        <Button
                                            variant="text"
                                            size="sm"
                                            disabled={pending}
                                            onClick={() =>
                                                void act(
                                                    row.archived
                                                        ? "unarchive"
                                                        : "archive",
                                                    [row],
                                                )
                                            }
                                        >
                                            {row.archived
                                                ? "Unarchive"
                                                : "Archive"}
                                        </Button>
                                        <Button
                                            variant="text-danger"
                                            size="sm"
                                            disabled={pending}
                                            onClick={() =>
                                                void act("delete", [row])
                                            }
                                        >
                                            Delete
                                        </Button>
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ul>
                </>
            ) : (
                <p className="py-8 text-center text-muted">
                    {props.rows.length > 0
                        ? "No notifications remain on this page."
                        : filters.q || filters.type || filters.status !== "all"
                          ? "No notifications match these filters."
                          : filters.bucket === "archived"
                            ? "No archived notifications yet."
                            : "No notifications yet."}
                </p>
            )}
            <nav
                aria-label="Notification pages"
                className="flex items-center justify-between gap-3"
            >
                <div>
                    {props.previousUrl && (
                        <ButtonLink href={props.previousUrl}>
                            Previous
                        </ButtonLink>
                    )}
                </div>
                <span className="text-sm text-muted">
                    Page {props.page} of {props.pages}
                </span>
                <div>
                    {props.nextUrl && (
                        <ButtonLink href={props.nextUrl}>Next</ButtonLink>
                    )}
                </div>
            </nav>
        </div>
    );
}
