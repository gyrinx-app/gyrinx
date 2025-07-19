**:gyrinx: Development and Roadmap Update**

Here's what's been happening with Gyrinx since the last update:

:bar_chart: Campaign Improvements

- Asset & Resource Management: Remove campaign assets and resources when needed (#574)
- Campaign Filtering: Added filtering support to campaigns page (#542)
- Data Integrity: Fixed campaign list links and prevented assets being assigned before campaign start
  (#582, #532)
- Timestamp Updates: Campaign modified times now update properly (#560)

:dart: Fighter Enhancements

- Fighter Info Tabs: Added dot indicators showing when Info/Lore tabs have content (#553)
- House Flexibility: Underhive Outcasts can now hire from any house (#578)
- Equipment Restrictions: House-restricted gear now properly enforced (#510)
- Psyker Disciplines: Fixed disciplines for non-psyker fighters (#544)

:shield: User Experience & Accessibility

- Terms of Service: Added ToS agreement checkbox to signup (#585)
- Accessibility: Added aria-labels to icon-only buttons and links (#577)
- Analytics Dashboard: New admin dashboard for tracking usage (#575)
- Pagination Fixes: Fixed duplicate page params and reset on filter changes (#570, #528)
- Mobile Improvements: Fixed fighter stat table overflow (#538)

:wrench: Data Management & Fixes

- Equipment Cleanup: Merged duplicate armoured undersuit items (#583)
- Content Management: Improved local development data workflow (#499)
- House Grouping: Legacy houses now properly grouped in dropdowns (#507)
- Error Handling: Enhanced error pages and logging (#565)
- List Updates: Modified timestamps update when events are logged (#552)

:bug: Bug Fixes

- Generic Houses: Hidden from list creation (#545)
- Equipment Filters: Fixed category restrictions (#541)
- Battle Reports: Fixed campaign action creation (#533)
- List Cloning: Prevented duplicates and preserved privacy settings (#509, #504)
- Homepage Search: Better empty results handling (#506)
- Print Layout: Fixed stash card width (#555)

:construction_site: Under the Hood

- Migration Cleanup: Squashed migrations for better performance (#569, #572, #579)
- Test Improvements: Consolidated duplicate fixtures (#527)
- UUID Protection: Added validation for invalid UUIDs (#523)
- Dependency Updates: Regular security and patch updates
- Set up a web application firewall (WAF) to protect against common web threats, and in particular an ongoing attack against Gyrinx. This will help mitigate risks from SQL injection, cross-site scripting (XSS), and other vulnerabilities.

**Roadmap**

Here's what's planned at the moment:

- Vehicles — currently in progress
- Skill adding/editing revamp
- Modifications to assigned gear/weapons (no more remove-and-re-add)
- Improved display of wealth & other campaign info for gangs
- Print improvements
- Support for alliance delegations
- Special rule overrides

That's the latest from Gyrinx development! More features in the pipeline. :game_die::sparkles:
