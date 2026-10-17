# Configure the built-in Trading Post action

## Intended behaviour

Authors can open **Content library → Actions → Built-in actions → Visit Trading Post**
and choose **Gang types excluded by default** from the library's gang types.
The selection uses content references, so adding or renaming a gang type needs
no application change. Unselected and newly added types show the action normally.
The initial configuration excludes Spyre Hunters.

For an excluded gang, the usual visit setup links disappear. The owner can open
**More actions → Other actions** to reach Visit Trading Post deliberately. The
visit page explains that the action is not normally used by this gang type.
This is guidance, not a permission restriction: owners can still start a visit
with a custom amount. Existing visits always retain their management and finish
controls, even after an author changes the configuration. Non-owners gain no
write access.

Spyrer models contribute no TP through the standard Leader and Champion
modifiers. Other Leaders contribute 2 and other Champions 1; a model holding
both ranks contributes 2. Founding and hire-time grants, equipment access,
purchase accounting and historical visit balances retain their existing rules.

## Implementation

1. Add a small library configuration model for code-backed actions, with a
   protected identity and a many-to-many selection of excluded gang types.
   It is global application configuration rather than assignable, staged or
   pack-owned game content. Only the Trading Post visit is supported.
2. Add an authoring verb, spec and generated form. Link its staff-only page
   from the existing Actions listing. Offer library gang types, retain selected
   archived types for editing, and prevent campaign-private content being
   selected. Do not offer creation, deletion or renaming of built-in actions.
3. Add one relevance reader used by the normal visit links and edit tabs.
   Add an owner-only Other actions page. Keep the existing visit operation,
   activity lifecycle and TP form as the execution path, including custom TP.
4. Seed the initial Spyre Hunters exclusion and add a negated Spyrer condition
   to the standard Leader/Champion contribution modifiers in a data migration.
   Preserve all existing conditions, including Champion's Leader exclusion.
   Fresh Foundations creation must produce the same defaults, while rerunning
   Foundations must preserve an author's visibility settings. Import clearing
   preserves configured gang types and subtype references held by retained
   contribution modifiers.
5. Add an author-facing recipe covering configuration, new gang types,
   exceptions, existing visits and contribution modifiers. Describe the
   built-in action configuration in Core Concepts.

## Verification

- Exercise staff access, saving and clearing selections, new library gang
  types, selected archived content, and rejected private campaign references.
- Verify an excluded owner sees Other actions, can start a custom visit, can
  manage and finish it after configuration changes, and a stranger cannot.
- Check ordinary and Spyrer Leader/Champion contributions through real content
  and gang operations, including dual ranks and existing modifier conditions.
- Verify Foundations reruns preserve authored configuration; test the migration
  against a realistic local database and independently inspect the results.
- Inspect authoring and player pages in desktop and phone layouts, light and
  dark themes. Check SQL query growth as the gang-type list grows.
- Run formatting, focused tests, migration checks and required static checks;
  open a ready PR and complete its CI and review cycle.

## Boundaries

This deliberately keeps the Trading Post visit as a built-in action. It does
not expand fighter Action Flow records to gang subjects or add a generic
modifier-based availability engine. A later integration can consume the same
content references without changing a player's open visits.
