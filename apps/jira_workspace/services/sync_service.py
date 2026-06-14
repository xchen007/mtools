import re
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jira_workspace.models import (
    JiraIssue,
    JiraIssueSyncMembership,
    JiraSyncProfile,
    JiraSyncRun,
)
from jira_workspace.services.jira_adapter import JiraAdapter


@dataclass
class SyncResult:
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0


class SyncService:
    def __init__(self, *, jira_adapter=None):
        self.jira = jira_adapter

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
