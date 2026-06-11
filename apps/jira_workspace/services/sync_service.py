from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from jira_workspace.models import JiraIssue, JiraSyncProfile, JiraSyncRun
from jira_workspace.services.jira_adapter import JiraAdapter


@dataclass
class SyncResult:
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0


class SyncService:
    def __init__(self, *, jira_adapter=None):
        self.jira = jira_adapter or JiraAdapter()

    def full_sync(self, profile):
        return self._sync(profile=profile, run_type=JiraSyncRun.RunType.FULL)

    def incremental_sync(self, profile):
        return self._sync(
            profile=profile,
            run_type=JiraSyncRun.RunType.INCREMENTAL,
            updated_since=profile.last_cursor,
        )

    def build_jql(self, profile, updated_since=None):
        if profile.profile_type == JiraSyncProfile.ProfileType.MY_ISSUES:
            username = profile.params_json.get("username") or self.jira.fetch_current_user()
            if not username:
                raise ValueError("Unable to resolve Jira username for my_issues profile.")
            base_jql = f'assignee = "{username}"'
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
            base_jql = self.build_jql(profile)
            effective_jql = self._append_updated_clause(base_jql, updated_since)
            items = self.jira.fetch_issues(effective_jql)
            result = self._store_items(profile=profile, items=items, run_type=run_type)

            profile.jql = base_jql
            if run_type == JiraSyncRun.RunType.FULL:
                profile.last_full_sync_at = timezone.now()
            else:
                profile.last_incremental_sync_at = timezone.now()
            profile.save(
                update_fields=[
                    "jql",
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
    def _store_items(self, *, profile, items, run_type):
        result = SyncResult(fetched_count=len(items))
        last_seen_at = timezone.now()
        max_updated = None

        for item in items:
            updated_at = item["updated_at"]
            issue = JiraIssue.objects.filter(issue_key=item["issue_key"]).first()

            if issue is None:
                JiraIssue.objects.create(
                    issue_key=item["issue_key"],
                    project_key=item["project_key"],
                    summary=item["summary"],
                    status=item["status"],
                    assignee=item.get("assignee"),
                    reporter=item.get("reporter"),
                    priority=item.get("priority"),
                    sprint=item.get("sprint"),
                    updated_at=updated_at,
                    created_at=item.get("created_at"),
                    raw_json=item.get("raw_json", "{}"),
                    last_seen_at=last_seen_at,
                )
                result.inserted_count += 1
            elif issue.updated_at == updated_at:
                issue.last_seen_at = last_seen_at
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
                issue.updated_at = updated_at
                issue.created_at = item.get("created_at")
                issue.raw_json = item.get("raw_json", "{}")
                issue.last_seen_at = last_seen_at
                issue.save()
                result.updated_count += 1

            if updated_at and (max_updated is None or updated_at > max_updated):
                max_updated = updated_at

        if max_updated is not None:
            profile.last_cursor = max_updated.isoformat()
        elif run_type == JiraSyncRun.RunType.FULL:
            profile.last_cursor = None

        return result

    @staticmethod
    def _append_updated_clause(jql, updated_since):
        cleaned = (jql or "").strip()
        if not updated_since:
            if "order by" in cleaned.lower():
                return cleaned
            return f"{cleaned} ORDER BY updated DESC"

        updated_clause = f'updated >= "{updated_since}"'
        lower_jql = cleaned.lower()
        order_index = lower_jql.find(" order by ")
        if order_index >= 0:
            base = cleaned[:order_index].strip()
            order_by = cleaned[order_index:].strip()
        else:
            base = cleaned
            order_by = "ORDER BY updated DESC"

        if base:
            return f"{base} AND {updated_clause} {order_by}".strip()
        return f"{updated_clause} {order_by}".strip()
