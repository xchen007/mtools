# Jira Sync Command Center Design

## Goal

Reshape `/jira/sync/` into a compact command-center page that fits the key Jira sync controls and status information into a `1440x900` desktop viewport without requiring vertical page scroll on initial load.

The page should prioritize operational awareness and immediate actions over always-expanded configuration and history details.

## Scope

This design covers:

- the visible information architecture of `/jira/sync/`
- the server-rendered template structure in `templates/jira_workspace/sync.html`
- the `Recent Sync Runs` presentation split between summary and detailed history
- the `Profile Editor` placement and interaction model
- any CSS and JavaScript needed to support the new compact layout and details switching
- regression tests for the new page structure and critical hooks

This design does not cover:

- changes to Jira sync execution semantics
- changes to `SyncService`, background execution, or progress persistence
- new endpoints or new data-fetching APIs
- a no-scroll guarantee on mobile layouts

## Current State

The current `/jira/sync/` page stacks three large content bands:

- a first band with presets plus timeline/log side panels
- a second band with the full profile editor plus sync controls
- a third band with the full recent sync runs table

In practice, this means:

- the page is operationally complete, but not first-screen complete
- the user must scroll to see the full run history area
- configuration, status, logs, and historical detail all compete at the same hierarchy level
- the page shows too much expanded secondary information for a command-oriented sync surface

## Target UX

At `1440x900`, the initial viewport should expose all key and actionable information:

- current profile identity and key metadata
- sync controls
- latest sync status
- current progress if a run is queued or running
- a short recent runs summary
- a short recent logs summary
- a clear entry point to details

The page should not attempt to expose the full historical table and the full profile form simultaneously in the first viewport.

## Decisions

- Adopt a `Command Center` information architecture.
- Treat sync actions and sync status as first-class content.
- Treat profile editing and full run history as secondary content.
- Keep the existing back-end context contract:
  - `profiles`
  - `selected_profile`
  - `sync_runs`
  - `recent_operation_logs`
  - `has_active_sync`
  - `latest_failed_run`
  - existing blocker/progress state
- Reuse the existing data rather than adding new endpoints or service calls.
- Preserve the complete run history table and the complete profile editor, but move both into a secondary details area.

## Information Architecture

The page becomes a two-level surface.

### Level 1: First-Screen Command Center

This is the always-visible area on desktop.

It contains:

- `Current Profile`
  - selected profile name
  - profile type
  - last cursor
  - default marker if applicable
- `Sync Controls`
  - profile selector
  - `Run Incremental`
  - `Run Full`
- `Latest Status`
  - last run result
  - blocker summary if present
  - active progress bar and message if present
- `Recent Runs Summary`
  - the most recent 4-5 runs in a compact single-line summary format
- `Recent Logs Summary`
  - the most recent 4-5 logs in a compact summary format with links to detail pages

### Level 2: Details

This is the secondary content area.

It contains:

- `Run History`
  - the existing full `Recent Sync Runs` table
- `Profile Editor`
  - the existing full profile form

These are displayed behind tabs or an equivalent explicit details switch, with the details area collapsed by default on initial page load.

## Layout Model

The recommended desktop layout is `3 + 2 + 1`.

### Row 1

Three compact cards:

- `Current Profile`
- `Sync Controls`
- `Latest Status`

### Row 2

Two summary cards:

- `Recent Runs Summary`
- `Recent Logs Summary`

### Row 3

One collapsed details section:

- `Details`
  - tab: `Run History`
  - tab: `Profile Editor`

This keeps the first screen focused and avoids forcing large form fields or a wide run-history table into the primary viewport.

## Interaction Model

### Details Switching

- The details region is collapsed by default on initial render.
- Expanding the details region reveals tab-like controls:
  - `Run History`
  - `Profile Editor`
- Only one details panel is visible at a time.

### Run History

- `Run History` contains the existing full sync runs table.
- No data is removed from the detailed history view.
- This detailed view remains the place for column-level run inspection.

### Profile Editor

- `Profile Editor` contains the existing full form.
- Save behavior remains unchanged.
- Existing form submission flow remains unchanged.

### Latest Status

- If a sync is queued or running, the first-screen `Latest Status` card shows:
  - progress message
  - progress bar
  - queued/running state
- If there is an external blocker or recent failure, that status appears here instead of consuming a dedicated full-height panel.

### Recent Runs Summary

This is not the full table.

Each summary row should emphasize:

- profile name
- run type
- status
- short progress/result text
- started/finished time only if it still fits comfortably

### Recent Logs Summary

Each log summary row should emphasize:

- log title
- status
- truncated summary/error text
- link to log detail

## Trade-Offs

### Chosen Trade-Off

Do not try to keep all existing modules expanded at once.

Instead:

- prioritize actionability and status in the first viewport
- demote rarely used expanded detail into an explicit secondary layer

### Why This Is Correct

The sync page is an operational page, not a settings form with incidental run history.

Users need to know:

- what profile they are about to run
- whether the system is healthy
- what just happened
- whether something is currently running

They do not need the full edit form and the full history grid expanded before they have even acted.

## Implementation Boundaries

- Do not change back-end sync execution.
- Do not change current async progress logic.
- Do not introduce new view endpoints or new API polling endpoints.
- Do not remove the existing full history table.
- Do not remove the existing full profile editor.
- Do not redesign the broader application shell.
- Do not optimize mobile for no-scroll; only preserve reasonable usability there.

## Testing

### Template / View Tests

Add or update tests to confirm:

- the page renders the new first-screen card structure
- the page exposes a details entry point
- the page renders compact recent runs summary content
- the page renders compact recent logs summary content
- the full run history table remains present in the details region
- the profile editor remains present in the details region
- active progress still appears on the first screen

### Front-End Hook Tests

Add focused tests for:

- details toggle/tab hooks
- default collapsed details state
- progress rendering inside the top-level status area

### Manual Verification

Verify in a desktop browser at `1440x900`:

- initial `/jira/sync/` load shows all first-screen command-center areas without page scroll
- queued/running sync shows progress in the first-screen status area
- recent runs summary is readable without opening details
- recent logs summary is readable without opening details
- opening `Run History` reveals the full existing run table
- opening `Profile Editor` reveals the full existing form
- async page refresh behavior still works while a sync is active

## Non-Goals

- no new sync capabilities
- no rework of progress semantics
- no redesign of `/sync2pod/` or other tools
- no conversion of this page into a SPA-like live dashboard
- no attempt to show the complete run table in the first viewport
