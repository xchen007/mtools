# Query Card Workbench Design

## Goal

Turn the Jira Query area into a configurable personal query-results workbench. The app should not replicate Jira's official product UI. It should let the user create reusable query cards, select one card, and view that card's result set in a shared, high-quality table layout with a lightweight detail drawer.

## Product Direction

The central object is a Query Card.

A Query Card is a saved result-view definition:

- display name
- description
- card kind
- query syntax
- query text or structured filters
- summary metrics to show above the table
- default columns
- default sort and page size
- pinned and starred state
- per-card table layout persistence key

Cards such as "Assigned to me", "Reported by me", "Blocked or waiting", and "Current sprint review" are not separate pages. They are different Query Card records rendered by the same page shell.

## Scope

This design covers the Jira query workbench at `/jira/query/`.

It includes:

- replacing the current split query library, query details, query editor, and query results layout with one workbench layout
- adding a `New Card` entry point
- editing cards in a drawer or modal surface
- rendering the selected card through the existing rich table shell
- showing query-level summary metrics
- keeping ticket row click detail behavior
- persisting table settings per card

It does not include:

- replacing Jira as an issue editing system
- building a full Jira JQL parser
- adding full kanban, backlog, project settings, workflow, or transition management
- moving sync2pod or integrations to Query Cards in this iteration

## UX Model

### Top Bar

The top bar remains tool-level navigation:

- collapse or expand left navigation
- current tool name
- top-level tool switcher
- settings and theme controls

It should not expose individual Jira query cards.

### Left Navigation

Inside Jira, the left secondary area changes from fixed Jira functions to card-centric navigation.

The Jira section contains:

- `Query Cards`
  - `New Card` button
  - ordered list of saved cards
  - each card shows name, row count, short query preview, and small metadata tags
- `Starred Objects`
  - starred cards
  - starred tickets
  - starred project-like objects
- `Sync Status`
  - cache freshness
  - active source
  - last failure summary if present

The list should support enough information for quick selection but stay compact. It should not become a full card grid.

### Main Workbench

The main area always renders the selected card.

The page structure is:

1. Card header
   - card name
   - short description
   - actions: `Edit card`, `Duplicate`, `Copy query`, `Run now`
2. Card configuration strip
   - card kind
   - query syntax
   - default view
   - persistence mode
3. Summary strip
   - metrics computed from the selected card's current result set
4. Result table
   - rich table shell with search, quick filters, sort, columns, density, pagination, horizontal scroll
5. Ticket detail drawer
   - opens when a result row is selected
   - overlays the right side without changing the main layout

### Drawers

The workbench has two drawer types:

- Card editor drawer
- Ticket detail drawer

They are mutually exclusive. Opening `Edit card` closes any ticket detail drawer. Selecting a ticket closes the card editor drawer. This prevents stacked overlays and avoids the visual conflict shown in the reference mockup.

### Card Editor

The card editor supports:

- name
- description
- profile or data source
- card kind
- query syntax
- query text
- structured filters
- summary metrics
- default columns
- default sort
- default page size
- pinned state
- starred state

The editor should preview the selected card state in the same page after save. Live preview can be added later; the first implementation can use save-and-refresh.

## Query Semantics

The first implementation should be honest about query execution.

Supported executable query modes:

- structured local filters backed by cached `JiraIssue` rows
- saved profile filters backed by existing sync profiles

Stored query syntax modes:

- `local_filter`
- `jql_text`
- `saved_filter_reference`

`jql_text` can be stored, displayed, copied, and sent to a live Jira adapter when live access is available. Local cached execution should not claim full Jira JQL support. If a JQL text card also has structured filters, the structured filters drive local results.

This keeps the app useful when Jira API access is blocked while still allowing real JQL-oriented cards to exist.

## Data Model

Keep `JiraSavedQuery` as the persistence model, but treat it as the backing model for Query Cards.

Add fields:

- `card_kind`: initial value `jira_issue_query`
- `query_syntax`: `local_filter`, `jql_text`, or `saved_filter_reference`
- `summary_metrics_json`: ordered list of metric keys
- `default_columns_json`: ordered list of table column keys
- `default_page_size`: integer, default `25`
- `position`: integer for left-nav ordering
- `is_enabled`: boolean

Existing fields remain useful:

- `name`
- `profile`
- `description`
- `filters_json`
- `jql_text`
- `is_starred`
- `is_pinned`
- `sort_by`
- `sort_order`

Avoid renaming the database model in this iteration. Renaming can be considered later if the feature stabilizes.

## Services

Add a small service boundary around card evaluation.

`query_card_service` responsibilities:

- list cards in display order
- resolve selected card
- build editor view model
- validate card input
- evaluate a card into result rows
- compute summary metrics for the selected result set
- build table configuration for the rich table shell
- build card-level persistence keys

Views should not manually assemble query semantics. They should call the service and pass a stable view model to templates.

## Routing

Keep the primary route:

- `/jira/query/`

Selection uses:

- `/jira/query/?card=<id>`

POST actions on the same route:

- `create_card`
- `update_card`
- `duplicate_card`
- `delete_card`
- `run_card`

Deletion should require an explicit submitted card id and redirect to the next available card.

The old `saved_query` query parameter can redirect or alias to `card` for backward compatibility.

## Template Structure

Target template decomposition:

- `templates/jira_workspace/queries.html`
  - page shell for the workbench
- `partials/query_card_nav.html`
  - left card list
- `partials/query_card_header.html`
  - selected card heading and actions
- `partials/query_card_summary.html`
  - metric strip
- `partials/query_card_editor_drawer.html`
  - create and edit form
- `partials/ticket_table.html`
  - unchanged shared rich table container, with card-specific persistence scope
- `partials/ticket_detail_drawer.html`
  - existing row detail drawer

The selected card's result table should use a per-card persistence scope:

`/jira/query/card/<card-id>/`

This satisfies the requirement that page and card settings persist locally and restore on next open.

## Visual Design

The visual direction is compact, work-focused, and closer to a query console than a dashboard product.

Use:

- a narrow left card list
- single-line card titles and query previews
- small metadata tags for syntax, view type, and metric count
- a restrained metric strip above the table
- simple table chrome
- stable table height with both vertical and horizontal scrolling
- right-side overlay drawer for details

Avoid:

- large marketing-style cards
- Jira-official clone layouts
- separate pages for each query result type
- multiple open overlays
- dashboard widgets that compete with the result table

## Error States

If Jira live access is blocked:

- card list still renders from local saved cards
- cached results still render
- the selected card shows source status as blocked or cache-only
- `Run now` shows a clear failure state without breaking the page

If a card has invalid input:

- the editor stays open
- field-level errors are shown
- previous valid result table remains visible if available

If no cards exist:

- left navigation shows an empty state
- main area opens the new-card editor
- result table is not shown until a card can be evaluated

## Testing

Back-end tests:

- query page renders Query Cards navigation
- selecting `?card=<id>` chooses the correct card
- legacy `?saved_query=<id>` is accepted or redirected
- creating a card persists query fields and redirects to the new card
- updating a card changes the selected card and result set
- duplicating a card creates a separate record
- deleting a card redirects to a valid fallback
- invalid editor input preserves errors
- blocked Jira state still renders cached card results
- summary metrics are computed from selected card results

Template tests:

- the page renders `New Card`
- the selected card configuration strip is present
- rich table uses card-specific persistence scope
- ticket detail drawer is present
- card editor drawer markup is present
- edit and ticket drawers have distinct hooks for mutual exclusion

Front-end tests or focused browser checks:

- opening the card editor closes the ticket drawer
- selecting a ticket closes the card editor
- rich table settings persist per card
- table horizontal scroll remains available
- no console errors on `/jira/query/`

Manual verification:

- create a new card
- edit query fields
- run the card
- switch between cards
- reload and confirm selected card and table settings persist
- click a ticket and verify right-side detail drawer
- switch theme modes and confirm readability

## Migration Plan

Existing `JiraSavedQuery` records become Query Cards automatically.

Default values:

- `card_kind`: `jira_issue_query`
- `query_syntax`: `jql_text` if `jql_text` exists, otherwise `local_filter`
- `summary_metrics_json`: `["total", "updated_today", "blocked", "in_progress", "high_priority"]`
- `default_columns_json`: `["issue_key", "project_key", "summary", "status", "assignee", "reporter", "priority", "updated_at"]`
- `default_page_size`: `25`
- `position`: order by current pinned, starred, name ordering
- `is_enabled`: `true`

No existing query records should be deleted.

## Reference Mockup

The current static reference is:

- `tmp/jira-query-workbench-reference.html`
- `tmp/jira-query-card-workbench-reference.png`

The mockup communicates the product model only. Final implementation should improve overlay behavior by keeping the card editor and ticket drawer mutually exclusive.

## Open Decisions Resolved

- Use one shared workbench page rather than one page per query function.
- Query cards are user-configured records, not hard-coded navigation features.
- Card editor and ticket detail drawer are mutually exclusive.
- Local cache mode supports structured filters first; stored JQL is preserved and copied but not falsely advertised as fully locally executable.
- `JiraSavedQuery` remains the database model for the first implementation.
