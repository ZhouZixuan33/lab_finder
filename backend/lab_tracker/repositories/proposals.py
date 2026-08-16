"""Parameterized SQL access for update proposals."""

import json
import sqlite3
from datetime import UTC, datetime

from lab_tracker.models.common import ProposalStatus
from lab_tracker.models.update import ProposalCreate, ProposalRecord


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _proposal_from_row(row: sqlite3.Row) -> ProposalRecord:
    values = dict(row)
    values["old_values"] = json.loads(values.pop("old_values_json") or "{}")
    values["new_values"] = json.loads(values.pop("new_values_json") or "{}")
    values["publication_diff"] = json.loads(values.pop("publication_diff_json") or "{}")
    values["source_urls"] = json.loads(values.pop("source_urls_json") or "[]")
    return ProposalRecord.model_validate(values)


class ProposalsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, proposal_id: int) -> ProposalRecord | None:
        row = self.connection.execute(
            "SELECT * FROM update_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
        return _proposal_from_row(row) if row is not None else None

    def get_pending_for_professor(self, professor_id: int) -> ProposalRecord | None:
        row = self.connection.execute(
            """
            SELECT * FROM update_proposals
            WHERE professor_id = ? AND status = 'pending'
            """,
            (professor_id,),
        ).fetchone()
        return _proposal_from_row(row) if row is not None else None

    def create_pending(
        self,
        proposal: ProposalCreate,
        *,
        now: datetime | None = None,
    ) -> ProposalRecord:
        cursor = self.connection.execute(
            """
            INSERT INTO update_proposals (
                job_id, professor_id, status, old_values_json, new_values_json,
                publication_diff_json, source_urls_json, confidence, created_at
            ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.job_id,
                proposal.professor_id,
                _json(proposal.old_values),
                _json(proposal.new_values),
                _json(proposal.publication_diff),
                _json(proposal.source_urls),
                proposal.confidence,
                _timestamp(now or datetime.now(UTC)),
            ),
        )
        record = self.get(int(cursor.lastrowid))
        if record is None:  # pragma: no cover - guarded by INSERT success
            raise RuntimeError("Proposal insert did not return a row")
        return record

    def list_pending(
        self,
        *,
        professor_id: int | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[ProposalRecord], int]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("Invalid proposal pagination")

        return self.list(
            status=ProposalStatus.PENDING,
            professor_id=professor_id,
            page=page,
            page_size=page_size,
        )

    def list(
        self,
        *,
        status: ProposalStatus | None = None,
        professor_id: int | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[ProposalRecord], int]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("Invalid proposal pagination")

        conditions: list[str] = []
        parameters: list[object] = []
        if status is not None:
            conditions.append("status = ?")
            parameters.append(status.value)
        if professor_id is not None:
            conditions.append("professor_id = ?")
            parameters.append(professor_id)
        where = " AND ".join(conditions) or "1 = 1"

        total = self.connection.execute(
            f"SELECT COUNT(*) FROM update_proposals WHERE {where}",
            parameters,
        ).fetchone()[0]
        rows = self.connection.execute(
            f"""
            SELECT * FROM update_proposals
            WHERE {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
        return [_proposal_from_row(row) for row in rows], int(total)

    def mark_applied(
        self,
        proposal_id: int,
        *,
        resolved_at: datetime | None = None,
    ) -> ProposalRecord | None:
        return self._resolve(proposal_id, ProposalStatus.APPLIED, resolved_at)

    def mark_rejected(
        self,
        proposal_id: int,
        *,
        resolved_at: datetime | None = None,
    ) -> ProposalRecord | None:
        return self._resolve(proposal_id, ProposalStatus.REJECTED, resolved_at)

    def _resolve(
        self,
        proposal_id: int,
        status: ProposalStatus,
        resolved_at: datetime | None,
    ) -> ProposalRecord | None:
        cursor = self.connection.execute(
            """
            UPDATE update_proposals
            SET status = ?, resolved_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (
                status.value,
                _timestamp(resolved_at or datetime.now(UTC)),
                proposal_id,
            ),
        )
        return self.get(proposal_id) if cursor.rowcount > 0 else None
