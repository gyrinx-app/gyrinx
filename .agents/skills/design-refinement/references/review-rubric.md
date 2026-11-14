# Structural and detail review rubric

Use the rows relevant to the page, with measured evidence and task context.
These are diagnostic questions, not a scorecard.

| Lens | Inspect | Typical correction | Protect |
| --- | --- | --- | --- |
| Useful density | Header height; repeated card padding; content visible before scroll; empty tracks | Remove nested containers; use compact repeated entries; reduce repeated gaps using existing spacing | Reading measure, grouping, touch targets and focus rings |
| Reading order | First three things noticed at full size and in monochrome | Emphasise the task content; quiet secondary metadata and toolbar chrome | Status and warnings needed to decide |
| Vertical rhythm | Successive block starts and gap patterns; heading-to-content distance | Reuse a small set of spacing tokens; make group breaks larger than internal gaps | Natural variable row heights and text wrapping |
| Alignment | Shared left/right edges, columns, value anchors, icon/text baselines | Consolidate nesting; align repeated values; reuse grid tracks or the existing row primitive | Independent regions and optical icon adjustments |
| Typography | Computed size, weight, line height and colour of comparable roles | Restore the heading/body/metadata roles; remove stray semibold/bold; use tabular numbers for comparison | Readability, semantic heading order and contrast |
| Disclosure | Frequency, prerequisites, clarity of the reveal label, open-state usability | Move occasional explanation to help; keep the immediate decision inline | Common tasks, errors, consequences and accessible names |
| Component fit | Repeated local markup versus gallery primitive; resolved CSS versus declared classes | Use the existing component or add a justified shared variant | Behaviour, permissions and edition boundaries |
| Copy | Entry label, heading, explanation, action and result read together | State the domain noun and actual outcome; remove redundant instruction | Specific reasons for empty/unavailable/read-only states |

## Interpret measurements

A large blank region can be purposeful breathing room or the consequence of
reserved space for content. Check a representative state before removing it.
Compare the same content at the same viewport. Useful measurements include
header-to-first-content distance, repeated entry height, rows visible in a
viewport, and left-edge deltas between elements intended to align.

Separate observations (the title begins 12px inside the list's text edge)
from judgments (this extra inset obscures their grouping). Relate a proposed
change to that judgment, not to a universal target whitespace percentage.
Never optimise for maximum occupancy or assume a multiple-of-eight rule is
more authoritative than the edition's actual spacing and type tokens.

The vertical rhythm is a sequence of meaningful gaps and line boxes. Vertical
column guides help shared horizontal positions; horizontal guides help block
starts and repeated spacing. A text baseline depends on font metrics: bounding
box tops from the helper are not measured glyph baselines. Inspect line height
and browser typography tools before claiming baseline alignment.

## Research basis

The workflow adapts established techniques to Gyrinx. The adaptation, three
passes and completion criteria are local guidance, not an external standard.

- [Jon Moore: Blockframing (2017)](https://medium.com/ux-power-tools/blockframing-and-31-free-sketch-ready-layouts-using-auto-layout-by-anima-app-1be039007ecf)
  abstracts interfaces into functional regions to discuss layout and resizing.
  We use it to diagnose page structure and then repeated content units.
- [NN/g: Visual Design Glossary](https://www.nngroup.com/articles/visual-design-cheat-sheet/)
  defines visual hierarchy, visual weight, whitespace and the squint test.
  Reduced detail helps inspect composition; it cannot establish task importance.
- [NN/g: Proximity Principle](https://www.nngroup.com/articles/gestalt-proximity/)
  explains how distance conveys grouping and how responsive layouts can break it.
- [NN/g: Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/)
  separates frequent needs from specialised options and stresses clear reveal
  controls. Moving everything into a menu would defeat that purpose.

No external framework is required for the included browser helper. It reads
browser geometry rather than guessing boxes from image pixels. It is a
review aid, not a skeleton loader, automatic redesign or accessibility audit.
