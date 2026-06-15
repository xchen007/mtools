# Jira Global Sync Policy Design

## Goal

Define a Jira sync architecture for `mtools` that supports:

- one current global sync policy
- multiple child sync scopes inside that policy
- a cached local `JiraIssue` total table used by all cards and dashboards
- versioned full rebuilds when the global policy changes
- scope-level incremental sync between rebuilds
- durable sync status, execution reports, and cache freshness visibility

This design is specifically optimized for the current intended usage:

- the user always needs `assignee = me OR reporter = me`
- the user may optionally add more scopes for a person, project, label, sprint, or similar Jira filter
- policy changes are expected to be infrequent
- the product must expose both global status and per-scope run detail

## Product Direction

The core product decision is:

- there is exactly one active global policy at a time
- that policy can contain many child scopes
- the local issue cache represents the union of all tickets covered by the current policy version

This is intentionally not a multi-profile design where several unrelated strategies coexist as first-class independent caches. It is a single policy with many execution scopes.

The system must keep old data for audit and history, but current operational views should be driven by the active policy version and active scope memberships.

## Scope

This design includes:

- a persisted global sync policy and policy versions
- child sync scopes with independent schedules and status
- one local cached issue table
- issue-to-scope membership tracking
- full sync rules for policy changes
- incremental sync rules for steady-state operation
- run reports and status surfaces
- product rules for cache trust and freshness display

This design does not include:

- background job framework choice
- websockets or live streaming logs
- Jira write-back workflows
- advanced retention pruning for historical inactive issues

## Core Architecture

The architecture has four distinct roles:

- `GlobalSyncPolicy`: configuration root and strategy definition
- `GlobalSyncPolicyVersion`: execution consistency boundary for policy changes
- `SyncScope`: independently scheduled child query task
- `JiraIssue` + `JiraIssueScopeMembership`: cached read model plus scope attribution

The separation is deliberate:

- policy version answers whether the cache is aligned with the latest strategy
- scope answers what runs, how often, and with what result
- issue table answers what cards query quickly
- membership answers why a ticket is present and whether it is still covered by the current policy

## Data Model

### GlobalSyncPolicy

There should be one persisted policy row representing the current strategy root.

Suggested fields:

- `id`
- `name`
- `strategy_json`
- `strategy_hash`
- `current_version_id`
- `status`
- `last_strategy_changed_at`
- `last_version_built_at`
- `created_at`
- `updated_at`

Notes:

- `strategy_json` stores the full user-facing configuration
- `strategy_hash` is used to detect meaningful changes
- `status` should communicate whether the current version is aligned and trusted

### GlobalSyncPolicyVersion

Each strategy change produces a new version row.

Suggested fields:

- `id`
- `policy_id`
- `version_no`
- `strategy_hash`
- `status`
- `full_sync_required`
- `full_sync_started_at`
- `full_sync_completed_at`
- `created_at`

Recommended status values:

- `pending_full_sync`
- `building`
- `ready`
- `partial_failed`
- `stale`

Product meaning:

- a new version exists whenever the strategy changes
- a version is not trusted until required full syncs complete
- old versions are retained for traceability

### SyncScope

Each child query task under the active policy version becomes one scope row.

Suggested fields:

- `id`
- `policy_version_id`
- `scope_type`
- `name`
- `is_required`
- `is_enabled`
- `schedule_minutes`
- `config_json`
- `base_jql`
- `effective_jql_last_run`
- `last_full_sync_at`
- `last_incremental_sync_at`
- `last_successful_check_at`
- `last_issue_updated_cursor`
- `last_run_status`
- `last_error_message`
- `next_run_at`
- `created_at`
- `updated_at`

Recommended scope types:

- `self_required`
- `assignee_user`
- `reporter_user`
- `project`
- `label`
- `sprint`
- `custom_jql`

Rules:

- `self_required` is a system scope and cannot be removed
- default `schedule_minutes` should be `30`
- each scope owns its own incremental cursor and run status

### JiraIssue

`JiraIssue` remains the shared cached total table used by cards and dashboards.

Existing fields can stay, but the model should be extended with:

- `last_checked_at`
- `last_synced_success_at`
- `is_active_in_current_policy`
- `first_seen_policy_version_id`
- `last_seen_policy_version_id`

Field semantics:

- `updated_at`: Jira-side issue update time
- `last_checked_at`: most recent local sync check that touched this ticket
- `last_synced_success_at`: most recent successful confirmation of this ticket, even if unchanged
- `is_active_in_current_policy`: whether the ticket is still covered by the current policy version

Historical tickets should not be physically deleted by default.

### JiraIssueScopeMembership

This is the key table for scope attribution and active coverage.

Suggested fields:

- `id`
- `issue_id`
- `scope_id`
- `policy_version_id`
- `first_seen_at`
- `last_checked_at`
- `last_synced_success_at`
- `last_seen_issue_updated_at`
- `is_active`
- `created_at`
- `updated_at`

Purpose:

- explain why a ticket entered the cache
- show which scope currently covers it
- mark tickets no longer returned by a given scope during a full sync
- support current views that include only active policy memberships

## Policy Change Rules

The system must treat any meaningful global strategy edit as a version change.

Recommended flow:

1. Normalize `strategy_json`
2. Compute a canonical `strategy_hash`
3. Compare with the current policy hash
4. If unchanged, keep the current version
5. If changed, create a new `GlobalSyncPolicyVersion`
6. Generate the new version's `SyncScope` rows
7. Mark the policy and version state as needing a full rebuild

Important rules:

- do not delete existing tickets on policy change
- do not consider a new policy version usable until required full syncs complete
- if the policy changed and the new version has not fully built, the product must show the cache as not fully aligned

## Full Sync Rules

Full sync is version-building work, not a cosmetic refresh.

Each scope full sync should:

1. run the scope's `base_jql`
2. page through all matching Jira issues
3. upsert each issue into `JiraIssue`
4. create or update `JiraIssueScopeMembership`
5. mark memberships returned in this run as `is_active = true`
6. mark older memberships for the same scope and policy version that were not returned as `is_active = false`
7. update the scope's timestamps and cursor
8. emit a durable run report

Critical freshness rule:

- if a ticket is returned by the scope but its Jira fields did not change, the system must still update:
  - `JiraIssue.last_checked_at`
  - `JiraIssue.last_synced_success_at`
  - `JiraIssueScopeMembership.last_checked_at`
  - `JiraIssueScopeMembership.last_synced_success_at`

This preserves the intended semantics of "successfully verified now" instead of "changed now".

## Incremental Sync Rules

Incremental sync is allowed only after a scope has completed at least one full sync for its policy version.

The Jira Python library does not provide a dedicated incremental sync API. Incremental behavior should be implemented with:

- `search_issues()`
- scope `base_jql`
- JQL `updated` filtering
- local cursor persistence

Recommended incremental JQL:

- `base_jql AND updated >= "<cursor - overlap>" ORDER BY updated ASC, key ASC`

Recommended overlap:

- default `5` to `10` minutes

Required reasons for overlap:

- Jira `updated` is not unique
- same-second issue updates can share timestamps
- paging interruptions and retries should not risk missing issues

Recommended incremental flow:

1. read `last_issue_updated_cursor`
2. subtract overlap
3. build effective incremental JQL
4. fetch matching issues page by page
5. upsert returned issues
6. refresh touched memberships and issue freshness timestamps
7. compute the highest returned Jira `updated`
8. persist the new cursor
9. write a run report

If no issues are returned:

- the run should still be recorded as a successful check
- the scope's own `last_successful_check_at` should advance
- tickets are not bulk refreshed unless they were actually returned by Jira

Incremental sync is not responsible for correcting policy coverage after a strategy change. Coverage changes require full sync on the new policy version.

## Status Model

### Policy Version Status

Recommended status values:

- `pending_full_sync`
- `building`
- `ready`
- `partial_failed`
- `stale`

Meaning:

- `pending_full_sync`: version created, no rebuild started
- `building`: one or more scope full syncs are running
- `ready`: all required scopes completed their full sync successfully
- `partial_failed`: one or more scopes failed and the version is not fully aligned
- `stale`: a newer strategy version exists but cache alignment is incomplete

### Scope Status

Recommended scope run status values:

- `idle`
- `queued_full`
- `running_full`
- `queued_incremental`
- `running_incremental`
- `success`
- `failed`
- `blocked`

Notes:

- `blocked` is for authentication, permission, or external access problems
- `failed` is for a failed run that is not a persistent external blocker

## Failure Handling

Failure handling should distinguish between required and optional scopes.

Rules:

- if a required scope fails, the policy version cannot become `ready`
- if an optional scope fails, the policy version may remain visible as `partial_failed`
- retrying a failed scope should not require deleting old data
- manual "rebuild current version" should enqueue fresh full sync work for all scopes in that version

The UI should surface:

- which scope failed
- whether it is required
- the latest error text
- whether the failure is blocking policy readiness

## Query Semantics

All cards should read from the local cache, not directly from Jira.

Default query mode should use:

- current policy version
- active memberships only
- active issues only

Historical diagnostic mode can optionally include:

- inactive memberships
- previous policy versions
- historical inactive issues

This keeps current operational views clean while preserving audit value.

## Execution Reports

Each scope run, whether full or incremental, should create a durable execution report.

The existing `JiraSyncRun` can be extended or replaced with a more explicit run-log model. Minimum fields should include:

- `policy_version_id`
- `scope_id`
- `run_type`
- `status`
- `trigger_mode`
- `started_at`
- `finished_at`
- `duration_ms`
- `jira_query_count`
- `jira_page_count`
- `db_total_ticket_count_after_run`
- `active_ticket_count_after_run`
- `scope_active_ticket_count_after_run`
- `fetched_count`
- `inserted_count`
- `updated_count`
- `unchanged_checked_count`
- `membership_touched_count`
- `deactivated_membership_count`
- `cursor_before`
- `cursor_after`
- `error_message`
- `report_json`

This covers the user-facing reporting needs:

- how many tickets are currently in the local DB
- how many tickets were inserted or updated in this run
- how long the run took

It also adds the extra numbers needed for real operations:

- how many matched tickets remain active
- how many unchanged tickets were still successfully checked
- how many memberships were deactivated after a full sync

## Frontend Status Surfaces

The product should expose sync state at three layers.

### Global Status Bar

Show:

- current policy name
- current policy version
- strategy hash summary
- policy status
- last strategy change time
- full sync completion ratio
- required scopes total, ready, failed
- optional scopes total, ready, failed
- current active ticket count
- latest successful global alignment time

Actions:

- rebuild current version
- run all due scopes now
- retry failed scopes
- view global reports

### Scope Status Cards

Each scope should show:

- scope name
- scope type
- JQL or condition summary
- schedule minutes
- required or optional
- last run status
- last full sync time
- last incremental sync time
- last successful check time
- last cursor
- active ticket count
- last inserted, updated, unchanged counts
- last run duration
- latest failure reason

Actions:

- run incremental now
- run full now
- view reports
- edit scope
- enable or disable scope

### Ticket Freshness Fields

Ticket table or detail surfaces should show:

- Jira `updated_at`
- local `last_checked_at`
- local `last_synced_success_at`
- `is_active_in_current_policy`
- matched scopes
- last seen policy version

This allows fast diagnosis of whether a problem is caused by stale Jira data, stale local checks, or loss of scope coverage.

## Review of the Chosen Direction

The chosen design is correct for the intended use case, but several implementation mistakes should be explicitly avoided.

### Do Not Treat Policy Version as Cosmetic

Policy version must participate in execution decisions, not only UI display.

Required guardrails:

- each scope run must be tied to a `policy_version_id`
- incremental runs are valid only after that scope has completed a full sync for that version
- a newer strategy version must visibly mark the cache as not fully aligned until required rebuilds complete

### Do Not Skip Active Membership Maintenance

Without active membership tracking, the total issue cache becomes operationally ambiguous.

Required rule:

- current operational views should be driven by active memberships in the current policy version, not by raw total-table presence alone

### Do Not Refresh Success Time Only on Data Changes

This design requires successful verification timestamps, not just mutation timestamps.

Required rule:

- every returned issue updates success freshness metadata even when business fields are unchanged

### Do Not Use Timestamp Cursor Without Overlap

Incremental sync without overlap is too risky on Jira Server or Data Center.

Required rule:

- use `updated >= cursor - overlap`
- use stable ordering by `updated ASC, key ASC`
- rely on idempotent local upsert

## Additional Engineering Recommendations

### Canonical Strategy Hashing

`strategy_hash` should be computed from normalized JSON:

- stable key ordering
- normalized list ordering rules where applicable
- irrelevant whitespace removed

This avoids false-positive policy version churn.

### System Scope for Self Coverage

`assignee = me OR reporter = me` should be a protected system scope:

- always present
- not deletable
- schedule may be editable
- enablement may not be disabled

### Persist Base and Effective JQL Separately

Store:

- `base_jql`
- `effective_jql_last_run`

This makes debugging incremental behavior much easier.

### Separate Total Ticket Count From Active Ticket Count

Always show both:

- total cached tickets in DB
- active tickets in current policy version

This avoids misleading interpretation of cache size.

### Classify Failure Types More Precisely

Do not collapse all failures into one generic bucket.

Recommended subtyping:

- `blocked_auth`
- `blocked_permission`
- `blocked_rate_limit`
- `failed_transient`
- `failed_data`

This will matter for retry policy and troubleshooting.

## Scheduling Guidance

The design should not hardcode "scan every scope every 30 minutes" as the only runtime pattern.

Preferred scheduling model:

- each scope has `next_run_at`
- the scheduler selects only due scopes
- manual actions create high-priority immediate runs
- a scope already running should not be enqueued twice
- a new policy version first enters a full-sync queue

This stays compatible with cron-style drivers today and background queue systems later.

## Deliberately Rejected Design

Do not merge all child scopes into one massive OR-based JQL and run only one sync task.

Reasons:

- it destroys independent scope status and reporting
- it makes per-scope failure diagnosis impossible
- it prevents independent scheduling
- it breaks the requirement to show detailed status for each child query task

Execution must remain multi-scope even though the policy is single-root.

## Final Product Principles

The implementation should hold to these product rules:

1. One global policy version decides whether the cache is aligned and trustworthy.
2. Many independent scopes decide what to fetch, when to fetch it, and how to report status.
3. One shared `JiraIssue` total table plus active memberships provides both query speed and attribution.
4. Ticket success freshness must advance even when the Jira ticket content did not change.
