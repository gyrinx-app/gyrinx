# Changelog

All notable changes to the Gyrinx project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Recent Changes

### 2025-06-09

#### Features

- **XP Tracking**: Added experience point tracking for fighters in campaign mode (#256)
- **Campaign Info Compression**: Compressed campaign information display in list view for better readability (#269)
- **Campaign List Management**: Lists can now be added to in-progress campaigns with immediate cloning (#255)
- **CSRF Error Handling**: Improved handling of CSRF errors with graceful form redirects (#262)

#### Fixes

- **Build System**: Prevented concurrent builds to ensure sequential deployment (#261)
- **Test Triggers**: Fixed issues with test automation triggers (#260)
- Fixed formatting issues on main branch

#### Documentation

- Added note to CLAUDE.md memory for development guidance

### 2025-06-08

#### Features

- **Homepage Modules**: Added campaign gangs and campaigns modules to homepage (#254)
- **Fighter Injuries**: Implemented comprehensive support for fighter injuries in campaign mode (#232)
- **Campaign Action Visibility**: Linked campaign actions to lists for better visibility (#244)
- **Search Improvements**: Updated search functionality to use PostgreSQL SearchQuery with SearchVector (#247)
- **Campaign Reopening**: Added ability to reopen ended campaigns (#252)
- **Injury System Updates**: Enhanced injury system with default outcome and grouping (#248)
- **Campaign Action Filtering**: Added filtering capabilities to campaign action log (#242)
- **GitHub Secrets Management**: Added management command to update Claude secrets in GitHub (#239)

#### Fixes

- **Navigation**: Active campaign versions now link to gang instead of campaign (#241)
- **UI Messages**: Added messages block to base layout and removed duplicates (#240)
- **Clone Behavior**: Fixed missing clone behavior for psyker powers and house additional rules (#243)

#### Other

- Added Claude action instructions and safety features

### 2025-06-07

#### Features

- **Two-Factor Authentication**: Enabled TOTP-based two-factor authentication support (#229)
- **Campaign Colors**: Expanded campaign color options to 24 with helpful tooltips (#223)
- **Gang Theme Colors**: Added campaign gang theme color customization (#218)
- **Cost Override**: Added ability to override costs for gear assignments (#217)
- **Admin Tools**: Added bulk group management actions in admin interface (#231)

#### Fixes

- **Campaign Navigation**: Changed navigation flow from gang page to campaign when in a campaign context (#224)
- **Campaign Modules**: Reordered campaign page modules for better UX (#225)
- **Cloud Build**: Removed invalid queueTtl field from cloudbuild.yaml

#### Other

- Switched to Claude Max compatible action
- Added queueTtl to ensure cloud builds are queued sequentially (#230)

### 2025-06-06

#### Features

- **File Upload Support**: Added TinyMCE file upload with Google Cloud Storage and CDN support (#215)

#### Fixes

- Added missing basic image styles
- Fixed issues with CDN usage in uploads

#### Documentation

- Updated documentation for recent features (#214)

### 2025-06-05

#### Features

- **Automated Screenshots**: Added automated screenshot utility using Playwright (#208)
- **Resource Tracking**: Added campaign resource tracking system (#212)
- **List Status Modes**: Added list status modes for campaign management (#205)
- **Narrative Editing**: Added user-facing UI for list and fighter narrative editing (#206)
- **Asset Tracking**: Implemented campaign asset tracking system (#211)
- **Feature Toggles**: Added group-based feature toggles with Campaigns Alpha navigation (#213)

#### Fixes

- **Weapon Filtering**: Fixed weapon availability filtering bugs (#210)

#### UI/UX

- Improved campaign UI to match list view patterns (#207)

#### Documentation

- Added PR guidance to CLAUDE.md
- Updated Claude GitHub action to use Opus

### 2025-06-04

#### Features

- **Campaign Status**: Added campaign status tracking with lifecycle management (#203)

#### Dependencies

- Updated minor and patch dependencies across the project (#201, #204)

### 2025-05-31

#### Features

- **Campaign Actions**: Added campaign action logging with dice rolls (#200)

#### UI/UX

- Small UI tweaks for campaign view

### 2025-05-26

#### Fixes

- Removed broken CSP configuration
- Added gstatic.com to CSP for reCAPTCHA resources

---

_Last updated: 2025-06-09_
