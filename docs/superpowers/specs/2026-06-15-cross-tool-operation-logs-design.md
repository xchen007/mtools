# Cross-Tool Operation Logs Design

## Goal

Add a unified operation logging system across the active mtools tools so every user-triggered query, sync, run, or scan action produces a durable log record that can be inspected in the UI.

The first implementation must cover:

- `/jira/query/`
- `/jira/sync/`
- `/sync2pod/`
- `/integrations/`

The system must provide both:

- a global log center for cross-tool inspection
- local recent-log visibility inside each tool page

## Product Direction

The product problem is not limited to one failing page. The current system has fragmented execution visibility:

- Jira Query has no durable run record at all
- Jira Sync stores run state but exposes only limited error detail in the UI
- sync2pod stores execution output in a tool-specific model
- integrations already has tool-specific run history, but not a cross-tool log center

The design should add one consistent observation layer instead of multiplying per-tool UI and persistence patterns.

The new logging layer is an audit and troubleshooting surface. It does not replace existing domain models such as `JiraSyncRun`, `Sync2PodRun`, or `IntegrationScanRun`.

## Scope

This design includes:

- a new unified `OperationLog` persistence model
- log creation for all supported user-triggered tool actions
- a global `/logs/` route for list and detail views
- a shared recent-log summary surface embedded into each covered tool page
- storage of request metadata, result summary, failure summary, and detailed log body
- test coverage for logging persistence, log views, and per-tool logging hooks

This design does not include:

- background job infrastructure
- streaming live logs over websockets
- retention policies, archival, or pagination optimization beyond reasonable defaults
- replacing existing run tables with `OperationLog`
- automatic logging of every page load or passive read-only browse action

## Actions Covered

The first implementation should log all current execution-entry actions across the active tools.

Covered actions:

- Jira Query:
  - `run_card`
- Jira Sync:
  - `full_sync`
  - `incremental_sync`
- sync2pod:
  - manual `start_sync`
  - watch-triggered sync runs
- integrations:
  - scan or refresh actions that execute tool checks

If integrations does not yet have a clear user-triggered execution entry that persists a run, the implementation should introduce the smallest consistent execution path necessary to create an `OperationLog`.

## Data Model

Add a new model, `OperationLog`, in `apps/jira_workspace/models.py`.

Suggested fields:

- `tool`
  - enum-like text field
  - values: `jira_query`, `jira_sync`, `sync2pod`, `integrations`
- `action`
  - text field describing the operation type
- `status`
  - values: `running`, `success`, `failed`
- `title`
  - user-facing summary label for list display
- `triggered_by`
  - username string
- `target_type`
  - optional text field for the domain object type, such as `query_card`, `jira_sync_profile`, `sync2pod_profile`, `integration_tool`
- `target_id`
  - optional text field for the related object identifier
- `request_payload_json`
  - JSON field with execution inputs
- `result_summary`
  - short text summary for success or neutral completion
- `error_message`
  - short failure summary
- `log_text`
  - detailed log body shown in the detail view
- `started_at`
  - datetime
- `finished_at`
  - nullable datetime
- `created_at`
  - auto timestamp
- `updated_at`
  - auto timestamp

Recommended model metadata:

- default ordering: newest first by `started_at`
- indexes on `tool`, `status`, `action`, `target_type`, `target_id`, and `started_at`

The model should be general enough to support future tools without schema changes.

## Logging Semantics

Each user-triggered operation should follow the same lifecycle:

1. Create `OperationLog(status="running")` before the main business operation starts.
2. Execute the business logic.
3. On success:
   - set `status="success"`
   - set `finished_at`
   - write `result_summary`
   - write `log_text`
4. On failure:
   - set `status="failed"`
   - set `finished_at`
   - write `error_message`
   - write `log_text`
   - re-raise the business exception when current behavior expects failure propagation

The logging layer must never silently swallow a real business failure.

If the logging write itself fails, the main business result should still win. In that situation:

- log the logging failure to Django application logging
- preserve the main business result or exception behavior
- do not fabricate a user-visible business failure solely because the audit write failed

## Per-Tool Logging Content

### Jira Query

Jira Query currently evaluates cards during page rendering and does not maintain a run record. The implementation should make `Run now` produce a true logged execution.

Minimum captured content:

- card name
- card id
- card syntax mode
- stored `jql_text`
- effective local filters
- selected username context
- result count
- relevant metric summary
- failure exception text if execution fails

The `Run now` action should be the explicit logging trigger. Passive page loads should not create operation logs.

### Jira Sync

Jira Sync already has `JiraSyncRun`. The new log record should supplement it, not replace it.

Minimum captured content:

- profile name
- profile id
- run type
- base JQL
- effective JQL with incremental clause if applicable
- fetched, inserted, updated, and skipped counts
- failure exception text

When possible, link the `OperationLog` target fields back to the profile that initiated the run.

### sync2pod

sync2pod already stores command execution output. The unified operation log should capture the same operational narrative in a cross-tool shape.

Minimum captured content:

- profile name
- profile id
- trigger type
- command line
- exit code
- stdout
- stderr
- failure summary

For watch-triggered runs, `triggered_by` can fall back to a stable system label when there is no explicit user action.

### Integrations

Integrations should log each execution-oriented scan or refresh operation through the unified model.

Minimum captured content:

- tool or catalog target name
- scan or refresh scope
- query or filter inputs
- result summary
- failure summary
- detailed execution body if available

The integrations page currently needs a clearly defined execution hook if one is not already exposed by the view layer.

## Services

Add a small service boundary around operation logging instead of writing `OperationLog` directly from every view and service branch.

Suggested service responsibilities:

- create a running log entry
- finalize success entries
- finalize failure entries
- build consistent `log_text`
- provide recent-log queries by tool and by target
- provide filtered queries for the global log center

This can be implemented as a service such as `operation_log_service.py` or a similarly named helper module under `apps/jira_workspace/services/`.

The service should be thin and deterministic. It should not contain business logic for Jira sync, query evaluation, or sync2pod execution.

## Routing

Add a new top-level route:

- `/logs/`

Add a detail route:

- `/logs/<id>/`

The global workspace shell should expose Logs as a top-level tool entry alongside the current tools.

The global list page should support query-string filters:

- `tool`
- `status`
- `action`

The detail surface can be either:

- a dedicated detail page
- a list page with a detail drawer

The initial implementation should prefer the simplest server-rendered option that matches the current shell patterns. A dedicated detail page is acceptable if it keeps complexity lower than coordinating a new drawer.

## UI Structure

### Global Log Center

Create a global logs page that acts as the unified troubleshooting center.

List contents:

- title
- tool label
- action
- status
- started time
- duration
- result summary or failure summary

Filtering:

- by tool
- by status
- by action

Ordering:

- newest first

Detail contents:

- metadata summary
- request payload
- result summary
- error message
- full `log_text`

Failure entries should be visually more prominent than success entries, but success entries must remain inspectable.

### Tool-Local Recent Logs

Each covered tool page should show a compact recent-log section with links to the global or direct detail views.

Jira Query:

- show recent logs for the selected Query Card or for the Jira Query tool
- place near the result workbench without crowding the main table

Jira Sync:

- show recent sync-related operation logs in the sidebar or near the sync timeline

sync2pod:

- expose recent logs near the existing run and capability surfaces

integrations:

- expose recent logs near recent scans or refresh surfaces

These local summaries should remain compact. They should not inline full log bodies.

## UX Principles

- Use summary-first, detail-on-demand presentation.
- Make failures easier to spot than successes.
- Keep long log bodies out of the primary workspace views.
- Reuse existing panel and shell patterns instead of inventing a parallel admin console aesthetic.
- Avoid creating separate logging paradigms per tool.

## Error Handling

Business execution failures should preserve current behavior unless there is a strong product reason to change it.

Examples:

- Jira Sync failures should still surface as failures to the sync page flow.
- Query execution failures should become visible to the user instead of disappearing behind a server error without context.

For the first implementation, Query Card execution should become explicit enough that a failure can be captured, persisted, and shown in UI. This may require moving part of evaluation out of purely implicit page-render time for the `Run now` action while keeping page rendering behavior coherent.

## Testing

Add focused tests that scale with this feature's risk.

Model tests:

- `OperationLog` defaults
- status lifecycle persistence
- ordering and basic filtering assumptions

Service tests:

- running log creation
- success finalization
- failure finalization
- recent-log query helpers

View tests:

- `/logs/` renders list
- `/logs/` filters by tool and status
- `/logs/<id>/` renders detail
- workspace shell exposes Logs top-level entry
- each covered tool page renders recent logs

Integration tests:

- `run_card` creates a success log
- Jira sync failure creates a failed log with error text
- sync2pod success captures stdout and stderr in `log_text`
- integrations execution creates a log entry visible in the global list

## Compatibility

The design deliberately preserves existing domain records:

- `JiraSyncRun`
- `Sync2PodRun`
- `IntegrationScanRun`

These remain the domain-specific source of truth for their subsystems.

`OperationLog` is the cross-tool observation layer.

## Implementation Notes

Keep implementation conservative and aligned with the existing Django app structure:

- add the model and migration in `jira_workspace`
- add a focused logging service
- extend existing views and services rather than rewriting them
- add log panels and list pages using current template and CSS patterns

The likely blast radius is:

- `models.py`
- new migration
- a new operation log service
- `views.py`
- `urls.py`
- workspace shell navigation service
- logs templates
- recent-log partials or embedded tool-page sections
- tests across models, services, and views

## Open Decisions Resolved

The feature decisions validated in brainstorming are:

- use one unified `OperationLog` model
- cover all active tools with execution entry points
- provide a global log center plus recent logs inside each tool page
- keep existing business run tables
- log both successes and failures

## Success Criteria

The feature is complete when:

- every supported execution entry writes a durable log record
- users can browse logs across tools in one place
- users can inspect a full log detail view in the UI
- each tool page shows recent relevant logs
- failures are visible and diagnosable without reading server console output
