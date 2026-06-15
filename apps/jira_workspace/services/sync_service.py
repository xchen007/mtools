import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jira_workspace.models import (
    GlobalSyncPolicy,
    GlobalSyncPolicyVersion,
    JiraIssue,
    JiraIssueScopeMembership,
    JiraIssueSyncMembership,
    JiraSyncProfile,
    JiraSyncRun,
    SyncScope,
)
from jira_workspace.services.jira_adapter import JiraAdapter


@dataclass
class SyncResult:
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    unchanged_checked_count: int = 0
    deactivated_membership_count: int = 0


class SyncService:
    CURSOR_OVERLAP_MINUTES = 5

    def __init__(self, *, jira_adapter=None):
        self.jira = jira_adapter

    @transaction.atomic
    def apply_policy_strategy(self, *, policy, strategy_json):
        normalized_strategy = self._normalize_strategy(strategy_json)
        strategy_hash = self._strategy_hash(normalized_strategy)
        if policy.strategy_hash == strategy_hash and policy.current_version_id:
            return policy.current_version

        last_version_no = (
            GlobalSyncPolicyVersion.objects.filter(policy=policy)
            .order_by("-version_no")
            .values_list("version_no", flat=True)
            .first()
            or 0
        )
        version = GlobalSyncPolicyVersion.objects.create(
            policy=policy,
            version_no=last_version_no + 1,
            strategy_hash=strategy_hash,
            status=GlobalSyncPolicyVersion.Status.PENDING_FULL_SYNC,
            full_sync_required=True,
        )
        self._create_scopes_for_version(version=version, strategy_json=normalized_strategy)

        policy.strategy_json = normalized_strategy
        policy.strategy_hash = strategy_hash
        policy.current_version = version
        policy.status = GlobalSyncPolicy.Status.STALE
        policy.last_strategy_changed_at = timezone.now()
        policy.save(
            update_fields=[
                "strategy_json",
                "strategy_hash",
                "current_version",
                "status",
                "last_strategy_changed_at",
                "updated_at",
            ]
        )
        return version

    def run_scope_full(self, scope):
        return self._run_scope(scope=scope, run_type=JiraSyncRun.RunType.FULL)

    def run_scope_incremental(self, scope):
        if scope.last_full_sync_at is None:
            raise ValueError("Incremental scope sync requires a prior full sync.")
        return self._run_scope(scope=scope, run_type=JiraSyncRun.RunType.INCREMENTAL)

    def full_sync(self, profile):
        return self._sync(profile=profile, run_type=JiraSyncRun.RunType.FULL)

    def incremental_sync(self, profile):
        return self._sync(
            profile=profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            updated_since=profile.last_cursor,
        )

    def build_sync_status(self):
        recent_runs = list(
            JiraSyncRun.objects.select_related("profile").order_by("-started_at")[:20]
        )
        latest_failure = next(
            (run for run in recent_runs if run.status == JiraSyncRun.Status.FAILED),
            None,
        )
        has_external_blocker = bool(
            latest_failure and self._is_external_blocker_error(latest_failure.error_message)
        )
        blocker_message = (
            "External Jira access is currently blocked."
            if has_external_blocker
            else ""
        )
        return {
            "recent_runs": recent_runs,
            "latest_failure": latest_failure,
            "has_external_blocker": has_external_blocker,
            "blocker_message": blocker_message,
        }

    def build_jql(self, profile, updated_since=None):
        if profile.profile_type == JiraSyncProfile.ProfileType.MY_ISSUES:
            base_jql = "assignee = currentUser()"
            return self._append_updated_clause(base_jql, updated_since)

        if profile.profile_type == JiraSyncProfile.ProfileType.PROJECT:
            project_key = profile.params_json.get("project_key")
            if not project_key:
                raise ValueError("project profile requires params_json.project_key.")
            base_jql = f'project = "{project_key}"'
            return self._append_updated_clause(base_jql, updated_since)

        if profile.profile_type == JiraSyncProfile.ProfileType.CUSTOM_JQL:
            base_jql = profile.params_json.get("jql") or profile.jql
            if not base_jql:
                raise ValueError("custom_jql profile requires params_json.jql or jql.")
            if not updated_since:
                return base_jql.strip()
            return self._append_updated_clause(base_jql, updated_since)

        raise ValueError(f"Unsupported profile type '{profile.profile_type}'.")

    def _sync(self, *, profile, run_type, updated_since=None):
        started_at = timezone.now()
        run = JiraSyncRun.objects.create(
            profile=profile,
            run_type=run_type,
            status=JiraSyncRun.Status.RUNNING,
            started_at=started_at,
        )

        try:
            self._refresh_profile_identity(profile)
            base_jql = self.build_jql(profile)
            effective_jql = self._append_updated_clause(base_jql, updated_since)
            items = self._jira_client().fetch_issues(effective_jql)
            result = self._store_items(
                profile=profile,
                items=items,
                run_type=run_type,
                synced_at=started_at,
            )

            profile.jql = base_jql
            if run_type == JiraSyncRun.RunType.FULL:
                profile.last_full_sync_at = timezone.now()
            else:
                profile.last_incremental_sync_at = timezone.now()
            profile.save(
                update_fields=[
                    "jql",
                    "params_json",
                    "last_cursor",
                    "last_full_sync_at",
                    "last_incremental_sync_at",
                    "updated_at",
                ]
            )

            run.status = JiraSyncRun.Status.SUCCESS
            run.finished_at = timezone.now()
            run.fetched_count = result.fetched_count
            run.inserted_count = result.inserted_count
            run.updated_count = result.updated_count
            run.skipped_count = result.skipped_count
            run.save(
                update_fields=[
                    "status",
                    "finished_at",
                    "fetched_count",
                    "inserted_count",
                    "updated_count",
                    "skipped_count",
                ]
            )
            return result
        except Exception as exc:
            run.status = JiraSyncRun.Status.FAILED
            run.finished_at = timezone.now()
            run.error_message = str(exc)
            run.save(update_fields=["status", "finished_at", "error_message"])
            raise

    @transaction.atomic
    def _store_items(self, *, profile, items, run_type, synced_at):
        result = SyncResult(fetched_count=len(items))
        max_updated = None

        for item in items:
            updated_at = item["updated_at"]
            issue = JiraIssue.objects.filter(issue_key=item["issue_key"]).first()

            if issue is None:
                issue = JiraIssue.objects.create(
                    issue_key=item["issue_key"],
                    project_key=item["project_key"],
                    summary=item["summary"],
                    status=item["status"],
                    assignee=item.get("assignee"),
                    reporter=item.get("reporter"),
                    priority=item.get("priority"),
                    sprint=item.get("sprint"),
                    issue_type=item.get("issue_type") or "",
                    labels_json=item.get("labels_json") or [],
                    updated_at=updated_at,
                    created_at=item.get("created_at"),
                    raw_json=item.get("raw_json", "{}"),
                    last_seen_at=synced_at,
                )
                result.inserted_count += 1
            elif issue.updated_at == updated_at:
                issue.last_seen_at = synced_at
                issue.save(update_fields=["last_seen_at"])
                result.skipped_count += 1
            else:
                issue.project_key = item["project_key"]
                issue.summary = item["summary"]
                issue.status = item["status"]
                issue.assignee = item.get("assignee")
                issue.reporter = item.get("reporter")
                issue.priority = item.get("priority")
                issue.sprint = item.get("sprint")
                issue.issue_type = item.get("issue_type") or ""
                issue.labels_json = item.get("labels_json") or []
                issue.updated_at = updated_at
                issue.created_at = item.get("created_at")
                issue.raw_json = item.get("raw_json", "{}")
                issue.last_seen_at = synced_at
                issue.save()
                result.updated_count += 1

            JiraIssueSyncMembership.objects.update_or_create(
                issue=issue,
                profile=profile,
                defaults={"last_seen_at": synced_at},
            )

            if updated_at and (max_updated is None or updated_at > max_updated):
                max_updated = updated_at

        if run_type == JiraSyncRun.RunType.FULL:
            self._reconcile_stale_memberships(profile=profile, synced_at=synced_at)

        if max_updated is not None:
            profile.last_cursor = max_updated.isoformat()
        elif run_type == JiraSyncRun.RunType.FULL:
            profile.last_cursor = None

        return result


    @transaction.atomic
    def _run_scope(self, *, scope, run_type):
        synced_at = timezone.now()
        effective_jql = self._build_scope_jql(scope=scope, run_type=run_type)
        scope.last_run_status = (
            SyncScope.RunStatus.RUNNING_FULL
            if run_type == JiraSyncRun.RunType.FULL
            else SyncScope.RunStatus.RUNNING_INCREMENTAL
        )
        scope.effective_jql_last_run = effective_jql
        scope.last_error_message = ""
        scope.save(
            update_fields=[
                "last_run_status",
                "effective_jql_last_run",
                "last_error_message",
                "updated_at",
            ]
        )

        try:
            items = self._jira_client().fetch_issues(effective_jql)
            result = self._store_scope_items(
                scope=scope,
                items=items,
                run_type=run_type,
                synced_at=synced_at,
            )
            scope.last_run_status = SyncScope.RunStatus.SUCCESS
            scope.last_successful_check_at = synced_at
            if run_type == JiraSyncRun.RunType.FULL:
                scope.last_full_sync_at = synced_at
            else:
                scope.last_incremental_sync_at = synced_at
            scope.save(
                update_fields=[
                    "last_run_status",
                    "last_successful_check_at",
                    "last_full_sync_at",
                    "last_incremental_sync_at",
                    "last_issue_updated_cursor",
                    "last_error_message",
                    "updated_at",
                ]
            )
            return result
        except Exception as exc:
            scope.last_run_status = SyncScope.RunStatus.FAILED
            scope.last_error_message = str(exc)
            scope.save(update_fields=["last_run_status", "last_error_message", "updated_at"])
            raise

    @transaction.atomic
    def _store_scope_items(self, *, scope, items, run_type, synced_at):
        result = SyncResult(fetched_count=len(items))
        seen_issue_keys = set()
        max_updated = self._parse_datetime(scope.last_issue_updated_cursor)

        for item in items:
            issue, was_inserted, was_updated, was_unchanged = self._upsert_scope_issue(
                item=item,
                scope=scope,
                synced_at=synced_at,
            )
            seen_issue_keys.add(issue.issue_key)

            if was_inserted:
                result.inserted_count += 1
            elif was_updated:
                result.updated_count += 1
            elif was_unchanged:
                result.skipped_count += 1
                result.unchanged_checked_count += 1

            self._refresh_scope_membership(
                issue=issue,
                scope=scope,
                synced_at=synced_at,
            )

            updated_at = item["updated_at"]
            if updated_at and (max_updated is None or updated_at > max_updated):
                max_updated = updated_at

        if run_type == JiraSyncRun.RunType.FULL:
            result.deactivated_membership_count = self._deactivate_missing_scope_memberships(
                scope=scope,
                seen_issue_keys=seen_issue_keys,
            )

        if max_updated is not None:
            scope.last_issue_updated_cursor = max_updated.isoformat()

        return result

    def _upsert_scope_issue(self, *, item, scope, synced_at):
        updated_at = item["updated_at"]
        issue = JiraIssue.objects.filter(issue_key=item["issue_key"]).first()
        if issue is None:
            issue = JiraIssue.objects.create(
                issue_key=item["issue_key"],
                last_seen_at=synced_at,
                last_checked_at=synced_at,
                last_synced_success_at=synced_at,
                is_active_in_current_policy=True,
                first_seen_policy_version=scope.policy_version,
                last_seen_policy_version=scope.policy_version,
                **self._issue_defaults(item),
            )
            return issue, True, False, False

        fields_match = issue.updated_at == updated_at and self._issue_matches_item(issue, item)
        if fields_match:
            issue.last_seen_at = synced_at
            issue.last_checked_at = synced_at
            issue.last_synced_success_at = synced_at
            issue.is_active_in_current_policy = True
            if issue.first_seen_policy_version_id is None:
                issue.first_seen_policy_version = scope.policy_version
            issue.last_seen_policy_version = scope.policy_version
            issue.save(
                update_fields=[
                    "last_seen_at",
                    "last_checked_at",
                    "last_synced_success_at",
                    "is_active_in_current_policy",
                    "first_seen_policy_version",
                    "last_seen_policy_version",
                ]
            )
            return issue, False, False, True

        for field, value in self._issue_defaults(item).items():
            setattr(issue, field, value)
        issue.last_seen_at = synced_at
        issue.last_checked_at = synced_at
        issue.last_synced_success_at = synced_at
        issue.is_active_in_current_policy = True
        if issue.first_seen_policy_version_id is None:
            issue.first_seen_policy_version = scope.policy_version
        issue.last_seen_policy_version = scope.policy_version
        issue.save()
        return issue, False, True, False

    @staticmethod
    def _refresh_scope_membership(*, issue, scope, synced_at):
        membership = JiraIssueScopeMembership.objects.filter(issue=issue, scope=scope).first()
        if membership is None:
            membership = JiraIssueScopeMembership(
                issue=issue,
                scope=scope,
                policy_version=scope.policy_version,
                first_seen_at=synced_at,
            )
        membership.policy_version = scope.policy_version
        membership.last_checked_at = synced_at
        membership.last_synced_success_at = synced_at
        membership.last_seen_issue_updated_at = issue.updated_at
        membership.is_active = True
        membership.save()

    @staticmethod
    def _deactivate_missing_scope_memberships(*, scope, seen_issue_keys):
        stale_memberships = JiraIssueScopeMembership.objects.filter(
            scope=scope,
            policy_version=scope.policy_version,
            is_active=True,
        ).exclude(issue_id__in=seen_issue_keys)
        deactivated_count = 0
        for membership in stale_memberships:
            membership.is_active = False
            membership.save(update_fields=["is_active", "updated_at"])
            has_active_policy_membership = membership.issue.sync_memberships.filter(
                policy_version=scope.policy_version,
                is_active=True,
            ).exists()
            if membership.issue.is_active_in_current_policy != has_active_policy_membership:
                membership.issue.is_active_in_current_policy = has_active_policy_membership
                membership.issue.save(
                    update_fields=["is_active_in_current_policy"]
                )
            deactivated_count += 1
        return deactivated_count

    def _build_scope_jql(self, *, scope, run_type):
        base, _order_by = self._split_order_by(scope.base_jql)
        if run_type == JiraSyncRun.RunType.FULL:
            return (scope.base_jql or "").strip()

        cursor = scope.last_issue_updated_cursor or scope.last_full_sync_at.isoformat()
        overlapped_cursor = self._subtract_cursor_overlap(cursor)
        if base:
            return f'({base}) AND updated >= "{overlapped_cursor}" ORDER BY updated ASC, key ASC'
        return f'updated >= "{overlapped_cursor}" ORDER BY updated ASC, key ASC'

    @staticmethod
    def _issue_defaults(item):
        return {
            "project_key": item["project_key"],
            "summary": item["summary"],
            "status": item["status"],
            "assignee": item.get("assignee"),
            "reporter": item.get("reporter"),
            "priority": item.get("priority"),
            "sprint": item.get("sprint"),
            "issue_type": item.get("issue_type") or "",
            "labels_json": item.get("labels_json") or [],
            "updated_at": item["updated_at"],
            "created_at": item.get("created_at"),
            "raw_json": item.get("raw_json", "{}"),
        }

    @classmethod
    def _issue_matches_item(cls, issue, item):
        defaults = cls._issue_defaults(item)
        return all(
            cls._field_matches(field, getattr(issue, field), value)
            for field, value in defaults.items()
        )

    @staticmethod
    def _field_matches(field, current_value, incoming_value):
        if field != "raw_json":
            return current_value == incoming_value
        return SyncService._normalize_raw_json(current_value) == SyncService._normalize_raw_json(
            incoming_value
        )

    @staticmethod
    def _normalize_raw_json(value):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value

    @classmethod
    def _subtract_cursor_overlap(cls, cursor):
        parsed = cls._parse_datetime(cursor)
        if parsed is None:
            raise ValueError("Scope cursor must be an ISO datetime.")
        return (parsed - timedelta(minutes=cls.CURSOR_OVERLAP_MINUTES)).isoformat()

    @staticmethod
    def _parse_datetime(value):
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value
        return timezone.datetime.fromisoformat(value)

    @classmethod
    def _create_scopes_for_version(cls, *, version, strategy_json):
        next_run_at = timezone.now()
        SyncScope.objects.create(
            policy_version=version,
            scope_type=SyncScope.ScopeType.SELF_REQUIRED,
            name="My Assigned or Reported Issues",
            is_required=True,
            is_enabled=True,
            is_system_scope=True,
            schedule_minutes=30,
            config_json={"mode": "self"},
            base_jql="assignee = currentUser() OR reporter = currentUser()",
            last_run_status=SyncScope.RunStatus.QUEUED_FULL,
            next_run_at=next_run_at,
        )

        for scope_config in strategy_json.get("scopes", []):
            SyncScope.objects.create(
                policy_version=version,
                scope_type=scope_config["scope_type"],
                name=scope_config["name"],
                is_required=scope_config.get("is_required", False),
                is_enabled=scope_config.get("is_enabled", True),
                is_system_scope=False,
                schedule_minutes=scope_config.get("schedule_minutes", 30),
                config_json=scope_config,
                base_jql=cls._scope_base_jql(scope_config),
                last_run_status=SyncScope.RunStatus.QUEUED_FULL,
                next_run_at=next_run_at,
            )

    @staticmethod
    def _scope_base_jql(scope_config):
        scope_type = scope_config["scope_type"]
        if scope_type == SyncScope.ScopeType.PROJECT:
            project_key = scope_config.get("project_key")
            if not project_key:
                raise ValueError("project scope requires project_key.")
            return f'project = "{project_key}"'
        if scope_type == SyncScope.ScopeType.CUSTOM_JQL:
            jql = scope_config.get("jql")
            if not jql:
                raise ValueError("custom_jql scope requires jql.")
            return jql.strip()
        if scope_type == SyncScope.ScopeType.ASSIGNEE_USER:
            username = scope_config.get("username")
            if not username:
                raise ValueError("assignee_user scope requires username.")
            return f'assignee = "{username}"'
        if scope_type == SyncScope.ScopeType.REPORTER_USER:
            username = scope_config.get("username")
            if not username:
                raise ValueError("reporter_user scope requires username.")
            return f'reporter = "{username}"'
        if scope_type == SyncScope.ScopeType.LABEL:
            label = scope_config.get("label")
            if not label:
                raise ValueError("label scope requires label.")
            return f'labels = "{label}"'
        if scope_type == SyncScope.ScopeType.SPRINT:
            sprint = scope_config.get("sprint")
            if not sprint:
                raise ValueError("sprint scope requires sprint.")
            return f'sprint = "{sprint}"'
        raise ValueError(f"Unsupported scope type '{scope_type}'.")

    @classmethod
    def _strategy_hash(cls, strategy_json):
        normalized_json = json.dumps(
            cls._normalize_strategy(strategy_json),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()

    @classmethod
    def _normalize_strategy(cls, value):
        if isinstance(value, dict):
            return {key: cls._normalize_strategy(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [cls._normalize_strategy(item) for item in value]
        return value

    def _refresh_profile_identity(self, profile):
        if profile.profile_type != JiraSyncProfile.ProfileType.MY_ISSUES:
            return

        params_json = dict(profile.params_json or {})
        stored_username = (params_json.get("username") or "").strip()

        try:
            username = self._jira_client().fetch_current_user()
        except Exception:
            if stored_username:
                return
            raise

        if not username:
            if stored_username:
                return
            raise ValueError("Unable to resolve Jira username for my_issues profile.")

        params_json["username"] = username
        profile.params_json = params_json

    @staticmethod
    def _reconcile_stale_memberships(*, profile, synced_at):
        stale_issue_keys = list(
            JiraIssueSyncMembership.objects.filter(profile=profile, last_seen_at__lt=synced_at)
            .values_list("issue_id", flat=True)
        )
        JiraIssueSyncMembership.objects.filter(profile=profile, last_seen_at__lt=synced_at).delete()
        if stale_issue_keys:
            JiraIssue.objects.filter(
                issue_key__in=stale_issue_keys,
                profile_sync_memberships__isnull=True,
                sync_memberships__isnull=True,
            ).delete()

    @staticmethod
    def _append_updated_clause(jql, updated_since):
        cleaned = (jql or "").strip()
        if not updated_since:
            if "order by" in cleaned.lower():
                return cleaned
            return f"{cleaned} ORDER BY updated DESC"

        updated_clause = f'updated >= "{updated_since}"'
        base, order_by = SyncService._split_order_by(cleaned)
        order_by = order_by or "ORDER BY updated DESC"

        if base:
            return f"({base}) AND {updated_clause} {order_by}".strip()
        return f"{updated_clause} {order_by}".strip()

    @staticmethod
    def _split_order_by(jql):
        match = re.search(r"\border\s+by\b", jql, flags=re.IGNORECASE)
        if not match:
            return jql.strip(), ""
        return jql[: match.start()].strip(), jql[match.start() :].strip()

    @staticmethod
    def _is_external_blocker_error(message):
        normalized = (message or "").lower()
        return "403" in normalized and (
            "the request is blocked" in normalized
            or "forbidden" in normalized
            or "access denied" in normalized
        )

    def _jira_client(self):
        if self.jira is None:
            if getattr(settings, "JIRA_SIMULATION_MODE", False):
                from jira_workspace.services.fake_jira_adapter import FakeJiraAdapter

                self.jira = FakeJiraAdapter()
            else:
                self.jira = JiraAdapter()
        return self.jira
