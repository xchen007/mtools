from dataclasses import dataclass

from jira_workspace.models import WorkspaceStar


@dataclass(frozen=True)
class StarToggleResult:
    created: bool
    star: WorkspaceStar | None = None


class StarService:
    def list_items(self):
        return [
            {
                "label": star.label,
                "href": star.route,
                "group_key": star.group_key,
                "kind": star.kind,
                "object_id": star.object_id,
            }
            for star in WorkspaceStar.objects.order_by("position", "created_at", "label")
        ]

    def is_starred(self, *, kind, route, object_id=""):
        return WorkspaceStar.objects.filter(
            kind=kind,
            route=route,
            object_id=object_id or "",
        ).exists()

    def toggle(self, *, kind, label, route, group_key, object_id="", position=0):
        normalized_object_id = object_id or ""
        existing = WorkspaceStar.objects.filter(
            kind=kind,
            route=route,
            object_id=normalized_object_id,
        ).first()
        if existing:
            existing.delete()
            return StarToggleResult(created=False)

        star = WorkspaceStar.objects.create(
            kind=kind,
            label=label,
            route=route,
            group_key=group_key,
            object_id=normalized_object_id,
            position=position,
        )
        return StarToggleResult(created=True, star=star)
