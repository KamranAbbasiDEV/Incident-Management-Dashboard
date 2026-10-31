"""FastAPI incident tracker with a lightweight HTML dashboard.

This is a local demo without authentication. Do not expose it on the public
internet or use it for real customer incidents.
"""
from contextlib import asynccontextmanager
import csv
import io
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .db import connection, event, initialize, one, utcnow

Severity = Literal["P1", "P2", "P3", "P4"]
Status = Literal["open", "investigating", "mitigated", "resolved"]
TRANSITIONS = {
    "open": {"investigating", "resolved"},
    "investigating": {"mitigated", "resolved"},
    "mitigated": {"investigating", "resolved"},
    "resolved": {"investigating"},
}
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=4, max_length=120)
    description: str = Field(default="", max_length=2000)
    service: str = Field(min_length=2, max_length=80)
    severity: Severity = "P3"
    owner: str = Field(default="", max_length=80)


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=4, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    service: str | None = Field(default=None, min_length=2, max_length=80)
    severity: Severity | None = None
    owner: str | None = Field(default=None, max_length=80)
    status: Status | None = None


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(min_length=3, max_length=1000)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize()
    yield


app = FastAPI(
    title="Incident Management Dashboard",
    version="1.0.0",
    description="Local demonstration incident tracker, not a production ITSM solution.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "application": "incident-management-dashboard"}


@app.get("/api/incidents")
def list_incidents(
    status: Status | None = None,
    severity: Severity | None = None,
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=100, ge=1, le=200),
):
    conditions, params = [], []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if q.strip():
        conditions.append("(title LIKE ? OR service LIKE ? OR owner LIKE ?)")
        term = f"%{q.strip()}%"
        params.extend((term, term, term))
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    with connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM incidents {where} ORDER BY id DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        count = conn.execute(
            f"SELECT COUNT(*) FROM incidents {where}", params
        ).fetchone()[0]
    return {"items": [dict(row) for row in rows], "total": count}


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: int):
    with connection() as conn:
        item = one(conn, incident_id)
        if item is None:
            raise HTTPException(404, "Incident not found")
        return item


@app.post("/api/incidents", status_code=201)
def create_incident(body: IncidentCreate):
    now = utcnow()
    data = body.model_dump()
    with connection() as conn:
        cursor = conn.execute(
            """INSERT INTO incidents
               (title, description, service, severity, status, owner, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'open', ?, ?, ?)""",
            (data["title"], data["description"], data["service"],
             data["severity"], data["owner"], now, now),
        )
        incident_id = cursor.lastrowid
        event(conn, incident_id, "created", f"Incident opened at {data['severity']} severity")
        return one(conn, incident_id)


@app.patch("/api/incidents/{incident_id}")
def update_incident(incident_id: int, body: IncidentUpdate):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "Supply at least one field to update")
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "Fields cannot be null")
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = one(conn, incident_id)
        if existing is None:
            raise HTTPException(404, "Incident not found")
        if "status" in changes and changes["status"] != existing["status"]:
            new_status = changes["status"]
            if new_status not in TRANSITIONS[existing["status"]]:
                raise HTTPException(
                    409, f"Invalid status transition: {existing['status']} -> {new_status}"
                )
            changes["resolved_at"] = utcnow() if new_status == "resolved" else None
        if "status" in changes and changes["status"] == existing["status"]:
            changes.pop("status")
        if not changes:
            return existing
        fields = [f"{key}=?" for key in changes]
        fields.append("updated_at=?")
        conn.execute(
            f"UPDATE incidents SET {', '.join(fields)} WHERE id=?",
            [*changes.values(), utcnow(), incident_id],
        )
        for key, value in changes.items():
            if key == "resolved_at":
                continue
            old = existing.get(key, "")
            if old != value:
                # Do not log free-text descriptions to avoid duplicating sensitive content.
                detail = (f"{key}: {old} -> {value}" if key in {"severity", "status"}
                          else f"{key} updated")
                event(conn, incident_id, "updated", detail)
        return one(conn, incident_id)


@app.get("/api/incidents/{incident_id}/events")
def incident_events(incident_id: int):
    with connection() as conn:
        if one(conn, incident_id) is None:
            raise HTTPException(404, "Incident not found")
        return {"items": [
            dict(row) for row in conn.execute(
                "SELECT * FROM incident_events WHERE incident_id=? ORDER BY id DESC",
                (incident_id,),
            ).fetchall()
        ]}


@app.post("/api/incidents/{incident_id}/notes", status_code=201)
def add_note(incident_id: int, body: NoteCreate):
    with connection() as conn:
        if one(conn, incident_id) is None:
            raise HTTPException(404, "Incident not found")
        event(conn, incident_id, "note", body.note)
        conn.execute(
            "UPDATE incidents SET updated_at=? WHERE id=?", (utcnow(), incident_id)
        )
    return {"message": "Note added"}


@app.get("/api/metrics")
def metrics():
    with connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        status_counts = {
            row["status"]: row["n"] for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM incidents GROUP BY status"
            )
        }
        severity_counts = {
            row["severity"]: row["n"] for row in conn.execute(
                "SELECT severity, COUNT(*) AS n FROM incidents GROUP BY severity"
            )
        }
        p1_active = conn.execute("SELECT COUNT(*) FROM incidents WHERE severity=? AND status!=?", ("P1", "resolved")).fetchone()[0]
        resolved = conn.execute(
            "SELECT created_at, resolved_at FROM incidents WHERE resolved_at IS NOT NULL"
        ).fetchall()
    from datetime import datetime
    durations = [
        (datetime.fromisoformat(row["resolved_at"]) -
         datetime.fromisoformat(row["created_at"])).total_seconds() / 3600
        for row in resolved
    ]
    return {
        "total": count,
        "active": sum(status_counts.get(s, 0) for s in ("open", "investigating", "mitigated")),
        "resolved": status_counts.get("resolved", 0),
        "p1_active": p1_active,
        "by_status": {s: status_counts.get(s, 0) for s in ("open", "investigating", "mitigated", "resolved")},
        "by_severity": {s: severity_counts.get(s, 0) for s in ("P1", "P2", "P3", "P4")},
        "mean_time_to_resolve_hours": round(sum(durations) / len(durations), 2) if durations else None,
    }


@app.get("/api/export.csv")
def export_incidents():
    with connection() as conn:
        rows = conn.execute("SELECT * FROM incidents ORDER BY id DESC").fetchall()
    fields = ("id", "title", "service", "severity", "status", "owner", "created_at", "updated_at", "resolved_at")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fields)
    for row in rows:
        # Guard against spreadsheet formula execution in CSV viewers.
        writer.writerow([
            "'" + str(row[field]) if isinstance(row[field], str) and
            row[field].lstrip().startswith(("=", "+", "-", "@")) else row[field]
            for field in fields
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="incidents.csv"'},
    )
