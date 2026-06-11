import shlex
import shutil
import subprocess

from django.utils import timezone

from jira_workspace.forms import Sync2PodProfileForm
from jira_workspace.models import Sync2PodProfile, Sync2PodRun, Sync2PodWatchEvent


class CommandRunner:
    def run(self, args, **kwargs):
        return subprocess.run(args, **kwargs)


class Sync2PodService:
    def __init__(self, *, command_runner=None):
        self.runner = command_runner or CommandRunner()

    def upsert_profile(self, data, *, instance=None):
        form = Sync2PodProfileForm(data, instance=instance)
        form.full_clean()
        return form.save()

    def delete_profile(self, profile):
        profile.delete()

    def check_capabilities(self, *, command=None):
        command_name = command or self._default_command()
        try:
            self.runner.run(
                [command_name, "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return {
                "is_available": False,
                "message": "sync2pod command is not available on this host.",
                "command_path": shutil.which(command_name) or command_name,
            }

        return {
            "is_available": True,
            "message": "",
            "command_path": shutil.which(command_name) or command_name,
        }

    def create_run(self, *, profile, trigger, watch_event=None):
        command = self._build_command(profile)
        run = Sync2PodRun.objects.create(
            profile=profile,
            status=Sync2PodRun.Status.RUNNING,
            trigger=trigger,
            command_line=" ".join(shlex.quote(part) for part in command),
        )

        try:
            result = self.runner.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            run.status = Sync2PodRun.Status.FAILED
            run.exit_code = 127
            run.error_message = "sync2pod command is not available on this host."
            run.finished_at = timezone.now()
            run.save(
                update_fields=["status", "exit_code", "error_message", "finished_at"]
            )
            self._finalize_watch_event(watch_event=watch_event, run=run, success=False)
            return run

        run.exit_code = result.returncode
        run.stdout_log = result.stdout or ""
        run.stderr_log = result.stderr or ""
        run.finished_at = timezone.now()
        if result.returncode == 0:
            run.status = Sync2PodRun.Status.SUCCESS
        else:
            run.status = Sync2PodRun.Status.FAILED
            run.error_message = self._build_failure_message(result)
        run.save(
            update_fields=[
                "status",
                "exit_code",
                "stdout_log",
                "stderr_log",
                "finished_at",
                "error_message",
            ]
        )
        self._finalize_watch_event(
            watch_event=watch_event,
            run=run,
            success=run.status == Sync2PodRun.Status.SUCCESS,
        )
        return run

    def build_status_summary(self):
        runs = list(Sync2PodRun.objects.select_related("profile").order_by("-started_at")[:10])
        queued_events = list(
            Sync2PodWatchEvent.objects.select_related("profile").filter(
                status=Sync2PodWatchEvent.Status.QUEUED
            )[:10]
        )
        latest_failure = next(
            (run for run in runs if run.status == Sync2PodRun.Status.FAILED),
            None,
        )
        command_name = self._default_command()
        capability = self.check_capabilities(command=command_name)
        error_messages = []
        if not capability["is_available"]:
            error_messages.append(capability["message"])
        if latest_failure and latest_failure.error_message:
            error_messages.append(latest_failure.error_message)

        return {
            "profiles": Sync2PodProfile.objects.order_by("name"),
            "runs": runs,
            "queued_events": queued_events,
            "queue_count": len(queued_events),
            "latest_failure": latest_failure,
            "capability": capability,
            "error_messages": error_messages,
        }

    def _build_command(self, profile):
        command = [profile.command, "push", "--pod", profile.pod_name]
        if profile.namespace:
            command.extend(["--namespace", profile.namespace])
        if profile.config_path:
            command.extend(["--config", profile.config_path])
        command.extend(["--watch-path", profile.watch_path])
        if profile.extra_args:
            command.extend(shlex.split(profile.extra_args))
        return command

    def _default_command(self):
        profile = Sync2PodProfile.objects.order_by("name").first()
        if profile and profile.command:
            return profile.command
        return "sync2pod"

    @staticmethod
    def _build_failure_message(result):
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            return detail
        return "sync2pod command failed."

    @staticmethod
    def _finalize_watch_event(*, watch_event, run, success):
        if not watch_event:
            return

        watch_event.run = run
        watch_event.status = (
            Sync2PodWatchEvent.Status.PROCESSED
            if success
            else Sync2PodWatchEvent.Status.FAILED
        )
        watch_event.processed_at = timezone.now()
        watch_event.save(update_fields=["run", "status", "processed_at"])
