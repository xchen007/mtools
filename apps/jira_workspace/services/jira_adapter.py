import json
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.utils import timezone


class JiraAdapter:
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
        self.base_url = (base_url or settings.JIRA_API_BASE_URL or "").rstrip("/") + "/"
        self.api_token = api_token if api_token is not None else settings.JIRA_API_TOKEN
        self.auth_type = (auth_type or settings.JIRA_AUTH_TYPE or "bearer").lower()
        self.user_email = (
            user_email if user_email is not None else settings.JIRA_USER_EMAIL or None
        )
        self.session = session or requests.Session()
        self.timeout = timeout

        if not self.base_url or not self.api_token:
            raise ValueError("JIRA_API_BASE_URL and JIRA_API_TOKEN are required.")
        if self.auth_type == "basic" and not self.user_email:
            raise ValueError("JIRA_USER_EMAIL is required when JIRA_AUTH_TYPE=basic.")
        if self.auth_type not in {"basic", "bearer"}:
            raise ValueError(f"Unsupported JIRA_AUTH_TYPE '{self.auth_type}'.")

    def fetch_current_user(self):
        payload = self._request("GET", "/rest/api/2/myself")
        return (
            payload.get("name")
            or payload.get("key")
            or payload.get("accountId")
            or payload.get("emailAddress")
            or ""
        )

    def fetch_issues(self, jql, page_size=50):
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
            "status": self._user_name(fields.get("status")),
            "assignee": self._user_name(fields.get("assignee")),
            "reporter": self._user_name(fields.get("reporter")),
            "priority": self._user_name(fields.get("priority")),
            "updated_at": self._parse_datetime(fields.get("updated")),
            "created_at": self._parse_datetime(fields.get("created")),
            "sprint": self._extract_sprint(fields),
            "raw_json": json.dumps(issue, ensure_ascii=False),
        }

    @staticmethod
    def _user_name(value):
        if not value:
            return None
        if isinstance(value, dict):
            return (
                value.get("name")
                or value.get("displayName")
                or value.get("emailAddress")
                or value.get("accountId")
            )
        return str(value)

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
            sprint_value = cls._coerce_sprint_value(value)
            if sprint_value:
                return sprint_value
        return None

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
