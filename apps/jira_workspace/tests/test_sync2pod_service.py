from types import SimpleNamespace
from unittest.mock import Mock

from django.test import TestCase

from jira_workspace.models import Sync2PodProfile, Sync2PodRun, Sync2PodWatchEvent
from jira_workspace.services.sync2pod_service import Sync2PodService


class Sync2PodServiceTests(TestCase):
    def setUp(self):
        self.runner = Mock()
        self.service = Sync2PodService(command_runner=self.runner)

    def test_upsert_profile_persists_sync2pod_configuration(self):
        profile = self.service.upsert_profile(
            {
                "name": "Primary Pod",
                "pod_name": "pod-a",
                "namespace": "sync",
                "watch_path": "/tmp/watch",
                "config_path": "/tmp/sync2pod.yaml",
                "command": "sync2pod",
                "extra_args": "--delete --verbose",
                "is_enabled": True,
            }
        )

        stored = Sync2PodProfile.objects.get(pk=profile.pk)
        assert stored.namespace == "sync"
        assert stored.extra_args == "--delete --verbose"
        assert stored.is_enabled is True

    def test_capability_check_reports_missing_binary_as_actionable_failure(self):
        self.runner.run.side_effect = FileNotFoundError("sync2pod")

        capability = self.service.check_capabilities()

        assert capability["is_available"] is False
        assert "sync2pod command is not available" in capability["message"]
        assert capability["command_path"] == "sync2pod"

    def test_create_run_records_successful_execution_summary(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            config_path="/tmp/sync2pod.yaml",
            command="sync2pod",
            extra_args="--delete",
        )
        self.runner.run.return_value = SimpleNamespace(
            returncode=0,
            stdout="synced 4 files",
            stderr="",
        )

        run = self.service.create_run(profile=profile, trigger=Sync2PodRun.Trigger.MANUAL)

        run.refresh_from_db()
        assert run.status == Sync2PodRun.Status.SUCCESS
        assert run.exit_code == 0
        assert run.stdout_log == "synced 4 files"
        assert "sync2pod" in run.command_line
        assert "--delete" in run.command_line

    def test_create_run_records_failure_state_and_actionable_error_message(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        self.runner.run.return_value = SimpleNamespace(
            returncode=7,
            stdout="",
            stderr="permission denied",
        )

        run = self.service.create_run(profile=profile, trigger=Sync2PodRun.Trigger.MANUAL)

        run.refresh_from_db()
        assert run.status == Sync2PodRun.Status.FAILED
        assert run.exit_code == 7
        assert "permission denied" in run.error_message

    def test_build_status_summary_counts_queue_and_latest_failure(self):
        profile = Sync2PodProfile.objects.create(
            name="Primary Pod",
            pod_name="pod-a",
            namespace="sync",
            watch_path="/tmp/watch",
            command="sync2pod",
        )
        failed_run = Sync2PodRun.objects.create(
            profile=profile,
            status=Sync2PodRun.Status.FAILED,
            trigger=Sync2PodRun.Trigger.MANUAL,
            command_line="sync2pod push",
            exit_code=1,
            error_message="cluster rejected transfer",
        )
        Sync2PodWatchEvent.objects.create(
            profile=profile,
            event_type=Sync2PodWatchEvent.EventType.FILE_CHANGED,
            status=Sync2PodWatchEvent.Status.QUEUED,
            file_path="src/module.py",
            detail="queued",
        )

        summary = self.service.build_status_summary()

        assert summary["queue_count"] == 1
        assert summary["latest_failure"] == failed_run
        assert summary["runs"][0] == failed_run
        assert "cluster rejected transfer" in summary["error_messages"][0]
