# Jira Sync Navigation Design

## Goal

Make `Jira Sync` reachable through the product UI without requiring the user to guess or manually type `/jira/sync/`.

The fix should support two user needs:

- global discoverability while working anywhere inside the Jira tool
- immediate context escape from the query workbench when cached Jira data looks stale or incorrect

## Problem

`/jira/sync/` already exists and exposes the operational controls required to refresh Jira data.

Today the route is effectively hidden:

- the top-level tool switcher sends `Jira` to `/jira/query/`
- the query workbench left navigation is intentionally card-centric and does not expose legacy Jira function links
- the query page includes `Run now`, but that action only re-runs the local cached card query and does not take the user to sync controls

This creates a product mismatch:

- stale or dirty cached fields such as `sprint` need `Jira Sync`
- the UI does not provide an obvious path to the page that actually fixes the data

## Product Decision

Keep the existing top-level tool switcher shape.

Do not add a brand-new top-level `Sync` tool beside `Jira`, `sync2pod`, and `Integrations`.

Instead:

- keep `Jira` as the top-level tool
- expose a Jira-local secondary navigation set that includes `Sync`
- add a contextual query-page shortcut that opens `Jira Sync` directly

This keeps the global shell compact while making sync operationally reachable.

## Scope

This design includes:

- a Jira-local secondary navigation group with a `Sync` entry
- a query-page contextual link to `/jira/sync/`
- active-state handling for Jira-local navigation
- tests for both navigation surfaces

This design does not include:

- changes to Jira sync logic
- new sync actions from the query page
- background jobs, polling, or run status redesign
- adding another top-level tool to the shell

## UX

### Global Jira Navigation

When the current tool is `Jira`, the shell should render a Jira-local route group.

Initial items:

- `Dashboard`
- `Query`
- `Sync`
- `Profiles`

Behavior rules:

- the group is only shown in Jira context
- the current Jira route is visually highlighted
- `Sync` points directly to `/jira/sync/`
- the top-level tool switcher remains unchanged

This is a tool-local navigation layer, not a replacement for query cards.

### Query Page Shortcut

The query workbench should expose a direct `Open Jira Sync` action in the card header action area.

Placement rules:

- place it in the same horizontal action cluster as `Edit card`, `Duplicate`, `Copy query`, and `Run now`
- style it as a secondary action
- keep it visible regardless of selected card state as long as the query page itself is rendered

Behavior rules:

- link target is `/jira/sync/`
- no modal, drawer, or inline sync surface is added in this iteration
- the action is purely navigational

The shortcut exists to answer the question: "my cached Jira data looks wrong, where do I fix it?"

## Architecture

### Shell Navigation Model

Extend the existing shell navigation view model to support tool-local sections for Jira.

The current shell already understands:

- the active top-level tool
- the current route name
- shell tool items

It should now also provide a small list of Jira-local routes when the active tool is Jira.

Suggested item shape:

- `key`
- `label`
- `href`
- `active`

This should come from `WorkspaceService.build_shell_navigation()` so templates stay declarative and route ownership remains centralized.

### Templates

The top bar remains the top-level tool switcher.

Add a dedicated render area for tool-local navigation in the shared shell template stack, using the shell context produced by `WorkspaceService`.

The query page header should receive a direct sync URL through standard template context or by calling `reverse()` inline in the template.

No JavaScript is required for the feature itself.

## Error Handling and Edge Cases

- If the sync route exists, the navigation should always render. This feature is about discoverability, not permission gating.
- If Jira has no configured connection, the `Sync` entry still appears because the sync page is also the place where the user sees connection and run status.
- If the user lands directly on `/jira/sync/`, the Jira-local `Sync` item should be active.
- Query cards and their left navigation remain unchanged; this feature must not reintroduce the old fixed Jira function list into the left sidebar.

## Testing

Add view and shell tests that prove:

- Jira shell navigation contains a `Sync` item when rendering a Jira page
- the `Sync` item is active on `/jira/sync/`
- the query page renders an `Open Jira Sync` link to `/jira/sync/`
- the query page still keeps query cards in the left sidebar rather than replacing them with legacy Jira sections

Testing should stay server-rendered and template-focused. No browser automation is required for this iteration.

## Acceptance Criteria

- A user on `/jira/query/` can reach `/jira/sync/` through a visible contextual action.
- A user anywhere inside the Jira tool can reach `/jira/sync/` through Jira-local navigation.
- The top-level shell does not grow a new standalone `Sync` tool.
- Query-card navigation remains card-centric.
- No sync behavior changes are introduced.
