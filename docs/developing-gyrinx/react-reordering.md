# Reordering in React

Import `ReorderScope`, `ReorderItem` and `ReorderDropLine` from the optional
`n26/frontend/ui/reorder` entry.
The live examples are at `/n26/design/react/reorder/`. Pattern steps in campaign
schedule settings use the same controls for a local form draft.

## Ownership

The adapter owns pointer and touch activation, keyboard movement, cancellation,
focus and announcements. It uses dnd kit behind the shared UI boundary. Its
keyboard controls choose discrete insertion boundaries rather than pixel offsets.
Only the handle starts a drag; inputs, selects and links stay ordinary controls.

The caller owns stable IDs, allowed destinations, order and saving. A drag emits
one `{ itemId, targetId }` command on drop. It never rearranges the caller's DOM or
changes data while previewing a destination. Escape, Tab, leaving the handle or a
changed list cancels the keyboard move. A changed list or disabled scope also
stops an active pointer drag.

Keep existing non-drag move controls as a fallback. Server-backed consumers must
still validate every move and retain uncertain commands through their workflow's
normal recovery mechanism. For a drop, submit directly from the overview with
`useWorkflowForm.submit(body)`; keep errors and retry controls inline. Do not open
an editing dialog or navigate to its URL as a transport for the command. Persist
only the resume marker and business command, then reload credentials from the
server when resuming. Do not pass a persistence promise as if the adapter
owned its success or error handling. Disable the scope while preparing or saving
a command, and render the confirmed order from the authoritative response.

## Describe the boundaries

Supply `targets` in timeline order, with a readable label for every boundary.
Each source provides its current `origin` boundary and a list of allowed target
IDs. Exclude its current position, the boundary immediately after itself and any
other no-op or forbidden destination. Keep origin descriptors in the ordered list
even when they are off-screen, so Up and Down can locate the source correctly.
Only render drop lines for destinations actually visible on this page.

Use occurrence IDs for repeated groups; a shared definition ID cannot identify a
particular appearance. Empty groups need a start boundary. Do not infer that the
first visible row of a paginated list is the start of its group.

```tsx
<ReorderScope
    sources={sources}
    targets={targets}
    disabled={saving}
    onMove={({ itemId, targetId }) => move(itemId, targetId)}
>
    {rows.map((row) => (
        <ReorderItem id={row.id} key={row.id}>
            {({ ref, handle, active }) => (
                <section ref={ref} className={active ? "relative opacity-40" : "relative"}>
                    <ReorderDropLine id={row.beforeTarget} align="start" />
                    {handle}
                    {row.name}
                </section>
            )}
        </ReorderItem>
    ))}
</ReorderScope>
```

`ReorderItem` adds no wrapper. Attach its ref to the actual row or group and put
its handle inside that element. Use its `active` value to fade the lifted source,
so the source and pointer overlay are visually distinct.
A source with no allowed destinations gets no handle. A disabled scope retains
disabled handles so the layout stays stable.

A drop line takes no layout height. Position it at the intended boundary in a
`relative` container. The default `align="center"` places its hit area on both
sides of the boundary. Inside a table's scroll wrapper, use `align="start"` at a
row's top and `align="end"` at its bottom: these keep the hit area inside the row
and avoid creating vertical overflow. Use a separate zero-height, aria-hidden
boundary row with one positioned cell spanning all columns. Remove its padding
and border, then put the drop line inside that cell. Do not anchor absolute drop
targets to `tr`: Safari can position them against the page instead of the row.
Keep the line outside the draggable row so fading the source does not fade its
neighbouring insertion boundary. Never put a `div` directly under `tbody` or `tr`.

## Verify a consumer

Exercise pointer, touch and keyboard moves with the real rendered data, including
an empty group and a protected row. Space or Enter picks up and drops; Up, Down,
Home and End choose a destination; Escape cancels; Tab leaves without moving.
Check focus after a cross-group remount and after cancelling to another input.
Confirm long labels fit on a phone, controls remain usable, and dragging does not
scroll a table internally or change its row heights.

For saved data, also test a refused move, a stale baseline, an unknown write and
reload recovery. A drag preview must not save generated rows or bypass permissions.
