# C0 sweep — content fix list (2026-08-01)

565 statline-less ContentFighters × 12 columns = 6,780 values.
ok 6,121 · blank 481 (Stash templates — legitimate) · format-variant 162 · malformed 11 · dash 5

## Malformed values — fix these 10 in admin (1 is legitimate)

- **Caryatid** (Non-gang, 1 fighters using) — `toughness` = `W` → likely 3 — check the book (W is a column-slip from Wounds?)
  https://gyrinx.app/admin/content/contentfighter/0816359c-911e-4172-91be-2b4e34306d5b/change/
- **Cawdor Way-Brethren** (Cawdor (HoF), 1 fighters using) — `movement` = `6*` → 6" — the * is probably a rulebook footnote marker
  https://gyrinx.app/admin/content/contentfighter/c5629878-478d-4db8-9597-96078c7b0174/change/
- **Czarn the Cyberoth** (Non-gang (Outlaw), 1 fighters using) — `intelligence` = `7_` → 7+ (stray underscore)
  https://gyrinx.app/admin/content/contentfighter/623b8423-4d6d-4846-8335-92ca0fb4900c/change/
- **Data-scrivener** (Non-gang (Law abiding), 1 fighters using) — `leadership` = `*+` → check the book — *+ is unreadable
  https://gyrinx.app/admin/content/contentfighter/ce64a9d6-2209-4473-887e-59bc5ae9c2f5/change/
- **Ferryman Rig-hand M4** (Abyssal Ferrymen, 1 fighters using) — `movement` = `4+` → 4" (wrong suffix)
  https://gyrinx.app/admin/content/contentfighter/1b825a3d-d52e-4178-b99c-4dcc41f65ed8/change/
- **Genestealer** (Malstrain, 3 fighters using) — `attacks` = `3+` → 3 (attacks is a plain count, not a roll)
  https://gyrinx.app/admin/content/contentfighter/e9b484bd-5ca7-46f8-83f6-cb6e58d37b6d/change/
- **Heretek** (Non-gang (Outlaw), 1 fighters using) — `movement` = `5+` → 5" (wrong suffix)
  https://gyrinx.app/admin/content/contentfighter/8cda44aa-4e3e-4355-b7b8-55d81f8b7d13/change/
- **Mirror Mask** (Alliances, 2 fighters using) — `movement` = `5+` → 5" (wrong suffix)
  https://gyrinx.app/admin/content/contentfighter/89ab0406-3ccc-48ca-b684-50c9b501188a/change/
- **Palanite Companion** (Alliances, 2 fighters using) — `movement` = `5+` → 5" (wrong suffix)
  https://gyrinx.app/admin/content/contentfighter/5cc6ec8b-ca09-4817-a79a-fe011a0cec60/change/
- **Pit Fighter** (Alliances, 1 fighters using) — `movement` = `%"` → check the book — %" is unreadable
  https://gyrinx.app/admin/content/contentfighter/a3575831-a3fb-4a1c-943e-290d98b0a16b/change/
- **Wilcox ‘Wild Snake’ Cinderjack** (Orlock (HoI), 0 fighters using) — `movement` = `D6+1"` → LEAVE AS IS — D6+1" is a real random-movement value
  https://gyrinx.app/admin/content/contentfighter/f0333ab9-3578-4ef5-83d6-43c1fe40a1ca/change/

## Format-variant values — 162 across these templates

Suffix-less target rolls and distances (`4` for `4+`, `5` for `5"`). Cards
currently display the suffix-less form, so fixing is a visible cosmetic
correction. Too many for hand-editing — proposed as a small preview-first
backfill instead (purely mechanical: add the suffix the ContentStat flags say).

- **Arachnotek Golem** (Van Saar (HoA), 1 using): movement `5`→`5"`, weapon_skill `3`→`3+`, ballistic_skill `3`→`3+`, initiative `3`→`3+`
  https://gyrinx.app/admin/content/contentfighter/7613d994-0f0e-4e6a-b94f-554851dd7a7d/change/
- **Badzone Captain** (Badzone Enforcers (WD), 1 using): initiative `4`→`4+`
  https://gyrinx.app/admin/content/contentfighter/5c21b6d9-81f2-40d4-b6dc-de03b05d7c15/change/
- **Badzone Patrolman** (Badzone Enforcers (WD), 1 using): initiative `4`→`4+`
  https://gyrinx.app/admin/content/contentfighter/b0027578-3b53-42de-bfc7-d45b12bfabe1/change/
- **Badzone Patrolman Specialist** (Badzone Enforcers (WD), 1 using): initiative `4`→`4+`
  https://gyrinx.app/admin/content/contentfighter/a9047fdf-2a5d-4b82-a9d9-8a3f40e08294/change/
- **Badzone Sergeant** (Badzone Enforcers (WD), 1 using): initiative `4`→`4+`
  https://gyrinx.app/admin/content/contentfighter/cbec07ac-1aa7-4c17-813b-d4e89f5f891d/change/
- **Bigby Crumb** (Non-gang, 1 using): movement `4`→`4"`, weapon_skill `5`→`5+`, ballistic_skill `4`→`4+`, initiative `2`→`2+`, leadership `7`→`7+`, cool `7`→`7+`, willpower `8`→`8+`, intelligence `5`→`5+`
  https://gyrinx.app/admin/content/contentfighter/354abf4b-fcbc-4fa4-9365-c16cb7867937/change/
- **Cawdor Road Preacher** (Cawdor (HoF), 1 using): ballistic_skill `4`→`4+`, leadership `7`→`7+`, cool `7`→`7+`, willpower `7`→`7+`, intelligence `7`→`7+`
  https://gyrinx.app/admin/content/contentfighter/6afd7fa2-01b0-4ba4-90bf-f3233b9777b2/change/
- **Cyniss** (Escher (HoB), 0 using): movement `5`→`5"`, weapon_skill `4`→`4+`, ballistic_skill `4`→`4+`, initiative `3`→`3+`, leadership `6`→`6+`, cool `5`→`5+`, willpower `6`→`6+`, intelligence `6`→`6+`
  https://gyrinx.app/admin/content/contentfighter/2f24705a-1e90-4a55-b167-7e92d1b74bf7/change/
- **D060-K13** (Orlock (HoI), 0 using): movement `5`→`5"`, weapon_skill `3`→`3+`, ballistic_skill `4`→`4+`, initiative `4`→`4+`, leadership `8`→`8+`, cool `6`→`6+`, willpower `7`→`7+`, intelligence `8`→`8+`
  https://gyrinx.app/admin/content/contentfighter/41a8c3ac-be88-42b7-8bcb-7f708c8e6df0/change/
- **Deacon Malakev** (Cawdor (HoF), 1 using): movement `4`→`4"`, weapon_skill `5`→`5+`, ballistic_skill `6`→`6+`, initiative `5`→`5+`, leadership `7`→`7+`, cool `6`→`6+`, willpower `7`→`7+`, intelligence `8`→`8+`
  https://gyrinx.app/admin/content/contentfighter/0000aa43-fc02-4fab-a537-3ba8ca84026a/change/
- **Doctor Arachnos** (Non-gang, 1 using): movement `5`→`5"`, weapon_skill `4`→`4+`, ballistic_skill `4`→`4+`, initiative `3`→`3+`, leadership `8`→`8+`, cool `7`→`7+`, willpower `7`→`7+`, intelligence `6`→`6+`
  https://gyrinx.app/admin/content/contentfighter/e64048f9-a183-4914-ba8f-de36e24045e8/change/
- **Enlisted Hive Scum** (Badzone Enforcers (WD), 1 using): initiative `4`→`4+`
  https://gyrinx.app/admin/content/contentfighter/7a0ab5aa-e851-4372-915b-fd5da3aeda4c/change/
- **Grub Targeson** (Non-gang (Law abiding), 1 using): movement `4`→`4"`, weapon_skill `4`→`4+`, ballistic_skill `3`→`3+`, initiative `4`→`4+`, leadership `8`→`8+`, cool `8`→`8+`, willpower `8`→`8+`, intelligence `6`→`6+`
  https://gyrinx.app/admin/content/contentfighter/73bdbb5c-aa69-4224-81a9-a95386011bf3/change/
- **Klovis the Redeemer** (Cawdor (HoF), 1 using): movement `5`→`5"`, weapon_skill `3`→`3+`, ballistic_skill `6`→`6+`, initiative `3`→`3+`, leadership `7`→`7+`, cool `5`→`5+`, willpower `6`→`6+`, intelligence `8`→`8+`
  https://gyrinx.app/admin/content/contentfighter/1c59cf16-530c-45e5-ac03-9170dd5ad79a/change/
- **Lady Credo** (Alliances, 1 using): movement `5`→`5"`
  https://gyrinx.app/admin/content/contentfighter/5d4808a2-6f7f-4b05-944a-348bb2f9e86f/change/
- **Macula, Cyber-Mastiff** (Orlock (HoI), 0 using): movement `5`→`5"`, weapon_skill `3`→`3+`, initiative `4`→`4+`, leadership `7`→`7+`, cool `6`→`6+`, willpower `8`→`8+`, intelligence `9`→`9+`
  https://gyrinx.app/admin/content/contentfighter/9d3e1271-a378-48ea-8b00-6b68f7d5fd52/change/
- **Macula, Cyber-Mastiff** (Orlock (GotU), 1 using): movement `5`→`5"`, weapon_skill `3`→`3+`, initiative `4`→`4+`, leadership `7`→`7+`, cool `6`→`6+`, willpower `8`→`8+`, intelligence `9`→`9+`
  https://gyrinx.app/admin/content/contentfighter/6ef5283d-8eb8-46db-accf-da1cbbf8df2f/change/
- **Mad Dog Mono** (Non-gang (Law abiding), 1 using): movement `5`→`5"`, weapon_skill `3`→`3+`, ballistic_skill `4`→`4+`, initiative `3`→`3+`, leadership `8`→`8+`, cool `7`→`7+`, willpower `8`→`8+`, intelligence `8`→`8+`
  https://gyrinx.app/admin/content/contentfighter/1b586b2b-a2f0-4c0d-8023-d17f5c167a19/change/
- **Margo Merdena** (Orlock (HoI), 0 using): movement `5`→`5"`, weapon_skill `2`→`2+`, ballistic_skill `3`→`3+`, initiative `2`→`2+`, leadership `5`→`5+`, cool `6`→`6+`, willpower `6`→`6+`, intelligence `7`→`7+`
  https://gyrinx.app/admin/content/contentfighter/ac78410f-9517-4f16-b73b-e19e74d42674/change/
- **Necrana** (Escher (HoB), 0 using): movement `5`→`5"`, weapon_skill `2`→`2+`, ballistic_skill `4`→`4+`, initiative `4`→`4+`, leadership `8`→`8+`, cool `4`→`4+`, willpower `7`→`7+`, intelligence `7`→`7+`
  https://gyrinx.app/admin/content/contentfighter/555ead15-5c01-42c5-8610-a87c2cdfd376/change/
- **Old Three-Eyes** (Goliath (HoC), 0 using): movement `4`→`4"`, weapon_skill `2`→`2+`, initiative `5`→`5+`, leadership `8`→`8+`, cool `4`→`4+`, willpower `6`→`6+`, intelligence `10`→`10+`
  https://gyrinx.app/admin/content/contentfighter/e6ca651f-cfc5-4ccd-8a55-7a1c96828b07/change/
- **Pyrocaen Lord** (Alliances, 2 using): movement `4`→`4"`
  https://gyrinx.app/admin/content/contentfighter/05540302-6717-417e-b1fe-d7b5748f65fa/change/
- **Ragnir Gunnstein** (Non-gang, 1 using): movement `3`→`3"`, weapon_skill `4`→`4+`, ballistic_skill `3`→`3+`, initiative `5`→`5+`, leadership `9`→`9+`, cool `7`→`7+`, willpower `6`→`6+`, intelligence `7`→`7+`
  https://gyrinx.app/admin/content/contentfighter/6b4bd417-3973-4fa8-b01c-0e7ac433b253/change/
- **Rattus Tatterskin** (Cawdor (HoF), 1 using): movement `5`→`5"`, weapon_skill `4`→`4+`, ballistic_skill `4`→`4+`, initiative `4`→`4+`, leadership `8`→`8+`, cool `5`→`5+`, willpower `6`→`6+`, intelligence `9`→`9+`
  https://gyrinx.app/admin/content/contentfighter/6d460dcd-a6e1-4cd0-baa0-38ab773b7a0e/change/
- **Redemptionist Road Preacher** (Cawdor (HoF), 1 using): ballistic_skill `4`→`4+`, leadership `8`→`8+`, cool `6`→`6+`, willpower `6`→`6+`, intelligence `9`→`9+`
  https://gyrinx.app/admin/content/contentfighter/1ea62244-7260-4386-b33a-45990e05b447/change/
- **Servant of the Silent Ones** (Delaque (HoS), 1 using): movement `8`→`8"`, weapon_skill `4`→`4+`, ballistic_skill `4`→`4+`, initiative `4`→`4+`, leadership `7`→`7+`, cool `4`→`4+`, willpower `5`→`5+`, intelligence `7`→`7+`
  https://gyrinx.app/admin/content/contentfighter/58a187de-effc-4435-ab8b-19a729d077c6/change/
- **Slate Merdena** (Orlock (HoI), 1 using): movement `5`→`5"`, weapon_skill `2`→`2+`, ballistic_skill `3`→`3+`, initiative `3`→`3+`, leadership `4`→`4+`, cool `5`→`5+`, willpower `4`→`4+`, intelligence `5`→`5+`
  https://gyrinx.app/admin/content/contentfighter/4419f533-b58d-44a5-af17-459776da90e1/change/
- **Tess ‘Arc Up’** (Goliath (HoC), 1 using): movement `6`→`6"`, weapon_skill `4`→`4+`, ballistic_skill `4`→`4+`, initiative `2`→`2+`, leadership `8`→`8+`, cool `5`→`5+`, willpower `7`→`7+`, intelligence `7`→`7+`
  https://gyrinx.app/admin/content/contentfighter/06f8e66b-dbd0-4af5-b4af-149b96cfcead/change/
