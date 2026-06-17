from datetime import datetime, timezone

import requests
from django.test import SimpleTestCase, TestCase

from jira_workspace.models import JiraConnection
from jira_workspace.services.jira_adapter import JiraAdapter


class StubResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class RecordingSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class JiraAdapterTests(SimpleTestCase):
    def test_fetch_current_user_sends_bearer_authorization_header(self):
        session = RecordingSession(
            [StubResponse({"name": "xchen17"})]
        )
        adapter = JiraAdapter(
            base_url="https://jira.example.com",
            api_token="token-123",
            auth_type="bearer",
            session=session,
            timeout=12,
        )

        username = adapter.fetch_current_user()

        assert username == "xchen17"
        assert session.calls == [
            {
                "method": "GET",
                "url": "https://jira.example.com/rest/api/2/myself",
                "params": None,
                "headers": {
                    "Accept": "application/json",
                    "Authorization": "Bearer token-123",
                },
                "auth": None,
                "timeout": 12,
            }
        ]

    def test_fetch_current_user_sends_basic_auth_credentials(self):
        session = RecordingSession(
            [StubResponse({"emailAddress": "xchen17@example.com"})]
        )
        adapter = JiraAdapter(
            base_url="https://jira.example.com/",
            api_token="token-123",
            auth_type="basic",
            user_email="xchen17@example.com",
            session=session,
        )

        username = adapter.fetch_current_user()

        assert username == "xchen17@example.com"
        assert session.calls == [
            {
                "method": "GET",
                "url": "https://jira.example.com/rest/api/2/myself",
                "params": None,
                "headers": {
                    "Accept": "application/json",
                },
                "auth": ("xchen17@example.com", "token-123"),
                "timeout": 30,
            }
        ]

    def test_fetch_current_user_prefers_server_and_cloud_identity_fields_consistently(self):
        session = RecordingSession(
            [
                StubResponse(
                    {
                        "accountId": "acct-123",
                        "displayName": "X Chen",
                    }
                )
            ]
        )
        adapter = JiraAdapter(
            base_url="https://jira.example.com",
            api_token="token-123",
            session=session,
        )

        username = adapter.fetch_current_user()

        assert username == "acct-123"

    def test_fetch_issues_paginates_until_total_is_reached(self):
        session = RecordingSession(
            [
                StubResponse(
                    {
                        "issues": [
                            {
                                "key": "TESS-1",
                                "fields": {
                                    "project": {"key": "TESS"},
                                    "summary": "First",
                                },
                            },
                            {
                                "key": "TESS-2",
                                "fields": {
                                    "project": {"key": "TESS"},
                                    "summary": "Second",
                                },
                            },
                        ],
                        "total": 3,
                    }
                ),
                StubResponse(
                    {
                        "issues": [
                            {
                                "key": "TESS-3",
                                "fields": {
                                    "project": {"key": "TESS"},
                                    "summary": "Third",
                                },
                            }
                        ],
                        "total": 3,
                    }
                ),
            ]
        )
        adapter = JiraAdapter(
            base_url="https://jira.example.com",
            api_token="token-123",
            session=session,
        )

        issues = adapter.fetch_issues('project = "TESS"', page_size=2)

        assert [issue["issue_key"] for issue in issues] == ["TESS-1", "TESS-2", "TESS-3"]
        assert [call["params"] for call in session.calls] == [
            {
                "jql": 'project = "TESS"',
                "startAt": 0,
                "maxResults": 2,
            },
            {
                "jql": 'project = "TESS"',
                "startAt": 2,
                "maxResults": 2,
            },
        ]

    def test_fetch_issues_reports_page_progress(self):
        session = RecordingSession(
            [
                StubResponse(
                    {
                        "issues": [
                            {
                                "key": "TESS-1",
                                "fields": {
                                    "project": {"key": "TESS"},
                                    "summary": "First",
                                },
                            }
                        ],
                        "total": 2,
                    }
                ),
                StubResponse(
                    {
                        "issues": [
                            {
                                "key": "TESS-2",
                                "fields": {
                                    "project": {"key": "TESS"},
                                    "summary": "Second",
                                },
                            }
                        ],
                        "total": 2,
                    }
                ),
            ]
        )
        adapter = JiraAdapter(
            base_url="https://jira.example.com",
            api_token="token-123",
            session=session,
        )
        progress_updates = []

        adapter.fetch_issues(
            'project = "TESS"',
            page_size=1,
            progress_callback=lambda fetched, total: progress_updates.append((fetched, total)),
        )

        assert progress_updates == [(1, 2), (2, 2)]

    def test_fetch_issues_normalizes_representative_jira_payload_shapes(self):
        created_at = "2026-06-01T09:00:00Z"
        updated_at = "2026-06-12T16:45:00+0800"
        session = RecordingSession(
            [
                StubResponse(
                    {
                        "issues": [
                            {
                                "key": "TESS-321",
                                "fields": {
                                    "project": {"key": "TESS"},
                                    "summary": "Refine query presets",
                                    "status": {"name": "In Progress"},
                                    "assignee": {
                                        "accountId": "acct-123",
                                        "displayName": "X Chen",
                                    },
                                    "reporter": {"emailAddress": "reporter@example.com"},
                                    "priority": {"value": "Highest"},
                                    "issuetype": {"name": "Bug"},
                                    "labels": ["backend", "urgent"],
                                    "created": created_at,
                                    "updated": updated_at,
                                    "sprint": {"name": "Sprint 42"},
                                },
                            },
                            {
                                "key": "OPS-778",
                                "fields": {
                                    "project": {"key": "OPS"},
                                    "summary": None,
                                    "status": "Done",
                                    "assignee": None,
                                    "reporter": {"name": "nina"},
                                    "priority": {"displayName": "High"},
                                    "created": "2026-06-02T09:00:00+00:00",
                                    "updated": None,
                                    "customfield_10020": [
                                        "com.atlassian.greenhopper.service.sprint.Sprint@1[id=7,rapidViewId=2,state=ACTIVE,name=Sprint 7,startDate=2026-06-01T08:00:00.000Z,endDate=2026-06-14T08:00:00.000Z,completeDate=<null>,sequence=7]",
                                        {"name": "Sprint 8"},
                                    ],
                                },
                            },
                        ],
                        "total": 2,
                    }
                )
            ]
        )
        adapter = JiraAdapter(
            base_url="https://jira.example.com",
            api_token="token-123",
            session=session,
        )

        issues = adapter.fetch_issues("project in (TESS, OPS)")

        assert issues == [
            {
                "issue_key": "TESS-321",
                "project_key": "TESS",
                "summary": "Refine query presets",
                "status": "In Progress",
                "assignee": "acct-123",
                "reporter": "reporter@example.com",
                "priority": "Highest",
                "issue_type": "Bug",
                "labels_json": ["backend", "urgent"],
                "updated_at": datetime.fromisoformat("2026-06-12T16:45:00+08:00"),
                "created_at": datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
                "sprint": "Sprint 42",
                "raw_json": issues[0]["raw_json"],
            },
            {
                "issue_key": "OPS-778",
                "project_key": "OPS",
                "summary": "",
                "status": "Done",
                "assignee": None,
                "reporter": "nina",
                "priority": "High",
                "issue_type": "",
                "labels_json": [],
                "updated_at": None,
                "created_at": datetime(2026, 6, 2, 9, 0, tzinfo=timezone.utc),
                "sprint": "Sprint 7, Sprint 8",
                "raw_json": issues[1]["raw_json"],
            },
        ]

    def test_fetch_issues_ignores_non_sprint_customfields_when_extracting_sprint(self):
        session = RecordingSession(
            [
                StubResponse(
                    {
                        "issues": [
                            {
                                "key": "SDSTOR-22591",
                                "fields": {
                                    "project": {"key": "SDSTOR"},
                                    "summary": "Resolve stubborn heal issues",
                                    "customfield_10010": {
                                        "name": "xchen17",
                                        "displayName": "Chen, Xuan",
                                    },
                                    "customfield_10020": [
                                        "com.atlassian.greenhopper.service.sprint.Sprint@1[id=11,rapidViewId=2,state=CLOSED,name=SDS-CP-Sprint11-2026,startDate=2026-06-01T08:00:00.000Z,endDate=2026-06-09T08:00:00.000Z,completeDate=2026-06-09T08:00:00.000Z,sequence=11]"
                                    ],
                                },
                            }
                        ],
                        "total": 1,
                    }
                )
            ]
        )
        adapter = JiraAdapter(
            base_url="https://jira.example.com",
            api_token="token-123",
            session=session,
        )

        issues = adapter.fetch_issues('key = "SDSTOR-22591"')

        assert issues[0]["sprint"] == "SDS-CP-Sprint11-2026"

    def test_fetch_issues_does_not_treat_dev_summary_as_sprint(self):
        session = RecordingSession(
            [
                StubResponse(
                    {
                        "issues": [
                            {
                                "key": "SSI-10595",
                                "fields": {
                                    "project": {"key": "SSI"},
                                    "summary": "Migrate CMS Auth from Keystone to TrustFabric",
                                    "customfield_31300": (
                                        "{summaryBean=com.atlassian.jira.plugin.devstatus.rest."
                                        "SummaryBean@1[summary={pullrequest="
                                        "PullRequestOverallBean{stateCount=1, state='OPEN'},"
                                        "repository={byInstanceType={githube="
                                        "ObjectByInstanceTypeBean@1[count=3,"
                                        "name=GitHub Enterprise]}}}]}"
                                    ),
                                },
                            }
                        ],
                        "total": 1,
                    }
                )
            ]
        )
        adapter = JiraAdapter(
            base_url="https://jira.example.com",
            api_token="token-123",
            session=session,
        )

        issues = adapter.fetch_issues('key = "SSI-10595"')

        assert issues[0]["sprint"] is None

    def test_fetch_current_user_propagates_request_failures(self):
        error = requests.HTTPError("401 Client Error: Unauthorized")
        session = RecordingSession([StubResponse(error=error)])
        adapter = JiraAdapter(
            base_url="https://jira.example.com",
            api_token="token-123",
            session=session,
        )

        with self.assertRaises(requests.HTTPError) as raised:
            adapter.fetch_current_user()

        assert raised.exception is error


class JiraAdapterDatabaseConfigTests(TestCase):
    def test_adapter_requires_active_database_connection_when_explicit_values_are_absent(self):
        with self.assertRaisesMessage(
            ValueError,
            "No active Jira connection is configured.",
        ):
            JiraAdapter(session=RecordingSession([]))

    def test_adapter_uses_active_database_connection_when_explicit_values_are_absent(self):
        JiraConnection.objects.create(
            base_url="https://jira-db.example.com",
            api_token="db-token",
            auth_type=JiraConnection.AuthType.BEARER,
            is_active=True,
        )
        session = RecordingSession([StubResponse({"name": "xchen17"})])

        adapter = JiraAdapter(session=session, timeout=7)
        username = adapter.fetch_current_user()

        assert username == "xchen17"
        assert session.calls[0]["url"] == "https://jira-db.example.com/rest/api/2/myself"
        assert session.calls[0]["headers"]["Authorization"] == "Bearer db-token"
        assert session.calls[0]["timeout"] == 7
