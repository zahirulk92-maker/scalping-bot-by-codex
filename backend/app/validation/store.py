"""Thin validation-history repository facade."""

from app.db.repositories.paper import PaperRepository
from app.validation.models import ValidationSnapshot


class ValidationStore:
    def __init__(self, repository: PaperRepository) -> None:
        self.repository = repository

    def save(self, snapshot: ValidationSnapshot) -> None:
        self.repository.persist_validation_snapshot(snapshot.session_id, snapshot.snapshot_id, snapshot.evaluated_at, snapshot.status.value, snapshot.model_dump(mode="json"))

    def recent(self, session_id: str, limit: int, offset: int = 0) -> list[ValidationSnapshot]:
        return [ValidationSnapshot.model_validate(value) for value in self.repository.validation_snapshots(session_id, limit, offset)]

    def latest(self, session_id: str) -> ValidationSnapshot | None:
        values = self.recent(session_id, 1)
        return values[0] if values else None
