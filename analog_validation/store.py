"""Append-only run snapshots and explicit feedback review; no scientific auto-learning."""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

from .models import UserFeedback


class Store:
    def __init__(self, path: str):
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                    feedback_id TEXT PRIMARY KEY REFERENCES feedback(id),
                    reviewer TEXT NOT NULL, decision TEXT NOT NULL,
                    evidence TEXT NOT NULL, created TEXT NOT NULL);
            """)

    def close(self) -> None:
        self.connection.close()

    def save_run(self, run: dict) -> str:
        payload = json.dumps(run, sort_keys=True, allow_nan=False)
        with self.connection:
            self.connection.execute("INSERT INTO runs VALUES (?, ?, ?)",
                                    (run["run_id"], datetime.now(timezone.utc).isoformat(), payload))
        return run["run_id"]

    def get_run(self, run_id: str) -> dict:
        row = self.connection.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def add_feedback(self, feedback: UserFeedback) -> str:
        run = self.get_run(feedback.run_id)
        if not any(r["site_id"] == feedback.site_id and r["mission_id"] == feedback.mission_id
                   for r in run["results"]):
            raise ValueError("Feedback site and mission do not belong to the referenced run")
        id_ = str(uuid4())
        with self.connection:
            self.connection.execute("INSERT INTO feedback VALUES (?, ?, ?, ?)",
                                    (id_, feedback.run_id, datetime.now(timezone.utc).isoformat(),
                                     json.dumps(asdict(feedback), allow_nan=False)))
        return id_

    def review_feedback(self, feedback_id: str, *, reviewer: str, decision: str,
                        evidence: tuple[str, ...]) -> None:
        """Trusted host must authenticate reviewer. This records a decision, never edits KB/scores."""
        if not reviewer or decision not in ("accepted", "rejected") or not evidence or not all(evidence):
            raise ValueError("Review requires reviewer, accepted/rejected decision and evidence")
        with self.connection:
            self.connection.execute("INSERT INTO reviews VALUES (?, ?, ?, ?, ?)",
                                    (feedback_id, reviewer, decision, json.dumps(evidence),
                                     datetime.now(timezone.utc).isoformat()))

    def list_feedback(self, run_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT f.id, f.payload, r.reviewer, r.decision, r.evidence FROM feedback f "
            "LEFT JOIN reviews r ON r.feedback_id = f.id WHERE f.run_id = ? ORDER BY f.created, f.id",
            (run_id,)).fetchall()
        return [{"id": row[0], "feedback": json.loads(row[1]), "reviewer": row[2],
                 "decision": row[3] or "pending_review", "review_evidence": json.loads(row[4] or "[]")}
                for row in rows]
