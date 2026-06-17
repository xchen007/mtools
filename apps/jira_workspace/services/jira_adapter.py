import json
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from django.utils import timezone


class JiraAdapter:
    _SPRINT_METADATA_KEYS = {
        "activatedDate",
        "boardId",
        "completeDate",
        "endDate",
        "goal",
        "originBoardId",
        "rapidViewId",
        "sequence",
        "startDate",
    }

    def __init__(
        self,
        *,
        base_url=None,
        api_token=None,
        auth_type=None,
        user_email=None,
        session=None,
        timeout=30,
    ):
        if all(value is None for value in (base_url, api_token, auth_type, user_email)):
            connection_values = self._active_connection_values()
            if not connection_values:
                raise ValueError("No active Jira connection is configured.")
            base_url = connection_values.get("base_url")
            api_token = connection_values.get("api_token")
            auth_type = connection_values.get("auth_type")
            user_email = connection_values.get("user_email")

        normalized_base_url = (base_url or "").rstrip("/")
        self.base_url = f"{normalized_base_url}/" if normalized_base_url else ""
        self.api_token = api_token or ""
        self.auth_type = (auth_type or "bearer").lower()
        self.user_email = user_email or None
        self.session = session or requests.Session()
        self.timeout = timeout

        if not self.base_url or not self.api_token:
            raise ValueError("Jira base URL and API token are required.")
        if self.auth_type == "basic" and not self.user_email:
            raise ValueError("Jira user email is required when auth type is basic.")
        if self.auth_type not in {"basic", "bearer"}:
            raise ValueError(f"Unsupported Jira auth type '{self.auth_type}'.")

    @classmethod
    def from_connection(cls, connection, **kwargs):
        return cls(
            base_url=connection.base_url,
            api_token=connection.api_token,
            auth_type=connection.auth_type,
            user_email=connection.user_email,
            **kwargs,
        )

    @staticmethod
    def _active_connection_values():
        from jira_workspace.models import JiraConnection

        connection = JiraConnection.objects.active().order_by("-updated_at").first()
        if connection is None:
            return {}
        return {
            "base_url": connection.base_url,
            "api_token": connection.api_token,
            "auth_type": connection.auth_type,
            "user_email": connection.user_email,
        }

    def fetch_current_user(self):
        payload = self._request("GET", "/rest/api/2/myself")
        return self._identity_value(payload) or ""

    def fetch_issues(self, jql, page_size=50, progress_callback=None):
        start_at = 0
        items = []

        while True:
            payload = self._request(
                "GET",
                "/rest/api/2/search",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": page_size,
                },
            )
            issues = payload.get("issues", [])
            for issue in issues:
                items.append(self._normalize_issue(issue))

            total = payload.get("total", 0)
            if progress_callback is not None:
                progress_callback(len(items), total)
            if not issues or start_at + len(issues) >= total:
                break
            start_at += len(issues)

        return items

    def _request(self, method, path, *, params=None):
        response = self.session.request(
            method=method,
            url=urljoin(self.base_url, path.lstrip("/")),
            params=params,
            headers=self._headers(),
            auth=self._basic_auth(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _headers(self):
        headers = {
            "Accept": "application/json",
        }
        if self.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _basic_auth(self):
        if self.auth_type == "basic":
            return (self.user_email, self.api_token)
        return None

    def _normalize_issue(self, issue):
        fields = issue.get("fields", {})
        return {
            "issue_key": issue.get("key", ""),
            "project_key": (fields.get("project") or {}).get("key", ""),
            "summary": fields.get("summary") or "",
            "status": self._display_value(fields.get("status")),
            "assignee": self._identity_value(fields.get("assignee")),
            "reporter": self._identity_value(fields.get("reporter")),
            "priority": self._display_value(fields.get("priority")),
            "issue_type": self._display_value(fields.get("issuetype")) or "",
            "labels_json": self._labels_value(fields.get("labels")),
            "updated_at": self._parse_datetime(fields.get("updated")),
            "created_at": self._parse_datetime(fields.get("created")),
            "sprint": self._extract_sprint(fields),
            "raw_json": json.dumps(issue, ensure_ascii=False),
        }

    @staticmethod
    def _identity_value(value):
        if not value:
            return None
        if isinstance(value, dict):
            return (
                value.get("name")
                or value.get("key")
                or value.get("accountId")
                or value.get("emailAddress")
                or value.get("displayName")
            )
        return str(value)

    @staticmethod
    def _display_value(value):
        if not value:
            return None
        if isinstance(value, dict):
            return value.get("name") or value.get("displayName") or value.get("value")
        return str(value)

    @staticmethod
    def _labels_value(value):
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @classmethod
    def _parse_datetime(cls, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value if timezone.is_aware(value) else timezone.make_aware(value)

        normalized = str(value).strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        normalized = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", normalized)
        parsed = datetime.fromisoformat(normalized)
        return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)

    @classmethod
    def _extract_sprint(cls, fields):
        direct = fields.get("sprint")
        if direct:
            return cls._coerce_sprint_value(direct)

        for key, value in fields.items():
            if not key.startswith("customfield_") or not value:
                continue
            if not cls._looks_like_sprint_value(value):
                continue
            sprint_value = cls._coerce_sprint_value(value)
            if sprint_value:
                return sprint_value
        return None

    @classmethod
    def _looks_like_sprint_value(cls, value):
        if isinstance(value, dict):
            return bool(cls._SPRINT_METADATA_KEYS.intersection(value.keys()))
        if isinstance(value, list):
            return any(cls._looks_like_sprint_value(item) for item in value)
        if isinstance(value, str):
            if "greenhopper.service.sprint.Sprint@" in value:
                return True
            return "name=" in value and any(
                marker in value
                for marker in (
                    "rapidViewId=",
                    "sequence=",
                    "startDate=",
                    "endDate=",
                    "completeDate=",
                    "activatedDate=",
                    "originBoardId=",
                )
            )
        return False

    @classmethod
    def _coerce_sprint_value(cls, value):
        if isinstance(value, dict):
            if value.get("name"):
                return str(value["name"])
            return None
        if isinstance(value, list):
            names = [name for name in (cls._coerce_sprint_value(item) for item in value) if name]
            if names:
                return ", ".join(names)
            return None
        if isinstance(value, str):
            match = re.search(r"name=([^,\]]+)", value)
            if match:
                return match.group(1)
        return None
