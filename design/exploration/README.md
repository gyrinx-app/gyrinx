# Design explorations

Small, interactive prototypes for discussing product behaviour and the data structures behind it. Each exploration lives in its own directory so it can be opened, reviewed and revisited independently. An exploration may remain as a record after the application is built; its README states whether the prototype or the production implementation is current.

| Exploration | Purpose |
| --- | --- |
| [Fighter actions](fighter-actions/README.md) | n26 Suit Evolution, advancements, assignable actions, payments and earned allowances. |

For a new exploration:

1. Create a directory named after the subject, with an `index.html` entry point and a short `README.md`.
2. Explain what is being explored, how to open it, what is simulated and which decisions remain open.
3. Keep sources, generated previews and any build scripts together. Identify which files to edit and how to rebuild the rest. Use relative links.
4. Prefer a standalone page that opens locally. Document any dependencies if a server or build is needed.
5. Check the main interactions and both wide and narrow layouts. Label historical screenshots so they cannot be mistaken for the current design.

These are design tools. Production implementations should follow the application's architecture and component conventions.
