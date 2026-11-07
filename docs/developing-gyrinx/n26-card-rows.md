# Card detail rows

Model cards and the gang sheet compose labelled facts through
`n26.core.rows.compose_rows`. HTML, print and text consume that projection.
Composition runs after the view links controls and hides dismissed offers;
`detail_rows` is a property, so it cannot retain an earlier visibility state.

## Default behaviour

One display owner gets one row for each heading. Matching collapses whitespace
and ignores case. It does not pluralise or infer meaning from a slot type.
The first contribution supplies the heading's spelling and position.

A row contains typed parts: names, gear, counters and choices. The parts retain
the original display objects. Two choices still have two keys and two controls.
Two counters still have two readings. Equal values remain present. Item stacking
and gameplay effect stacking are separate operations.

A carried copy is its own display owner. Choices on two identically named weapons
or pieces of gear stay beneath their respective copies. A model's own choice
cannot combine with a choice carried by its gear.

Authors need no grouping setting. Give choices the same displayed label when
they should share a heading. For example, recruitment, advancement and battle
slots labelled **Legendary name** share one row, while each acquisition retains
its own rating, history and chooser. No content conversion is needed.

## Adding a display fact

Declare a fixed assignable row on its render dataclass with `row_label` metadata.
Use `row_kind="gear"` for gear; named facts use `names`. Set `row_always=True`
only when the screen needs an empty placeholder. Open questions routed through
`QUESTION_BUCKETS` join the declared row automatically. Dynamic choice labels,
counter names and gear-category headings always enter the same composer.

A declared assignable field rendered elsewhere needs a `row_elsewhere` reason.
Subtypes belong in the model's type line; collections describe purchase access
on the equipment browser. These are placements outside the detail list.

For a genuinely separate heading within one owner, pass a `Separation` with a
stable key and a non-empty reason on its `Contribution`. This is a code-level
exception, not a routine authoring option. Keep a regression test for the reason
that the headings must remain separate.

`test_card_rows.py` discovers declared assignable rows and checks their projection
and picker wiring. `test_rows.py` discovers the supported part kinds and checks
HTML, print and text support. A new part kind must have all three presentations;
there is no unknown-kind fallback.
