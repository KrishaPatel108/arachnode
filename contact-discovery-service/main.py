"""
main.py — FastAPI entrypoint for the Contact Discovery Service.

Endpoints
─────────
  POST /discover                     Run pipeline for a company
  GET  /contacts?company={company}   List contacts by company name
  GET  /contacts/{job_id}            List contacts by job UUID
  DELETE /contacts/{id}              Remove a contact record
  GET  /health                       Liveness probe
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

import storage
import discovery as disc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await storage.create_pool()
    logger.info("Contact Discovery Service ready.")
    yield
    await storage.close_pool()
    logger.info("Contact Discovery Service shut down.")


app = FastAPI(
    title="Contact Discovery Service",
    description=(
        "Discovers publicly available engineering and recruiting contacts "
        "for a given company and links them to job postings."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DiscoverRequest(BaseModel):
    company: str
    job_id: Optional[UUID] = None
    roles: list[str] = ["Engineering Manager", "Recruiter"]
    domain: Optional[str] = None   # override if you already know the domain


class ContactOut(BaseModel):
    id: UUID
    job_id: Optional[UUID]
    company: str
    domain: Optional[str]
    name: Optional[str]
    email: Optional[str]
    role: Optional[str]
    source: Optional[str]
    verified: str
    created_at: str

    @classmethod
    def from_record(cls, row) -> "ContactOut":
        d = dict(row)
        d["created_at"] = d["created_at"].isoformat()
        return cls(**d)


# ---------------------------------------------------------------------------
# Background task: run pipeline → persist
# ---------------------------------------------------------------------------

async def _discover_and_store(
    company: str,
    roles: list[str],
    job_id: Optional[UUID],
    domain: Optional[str],
) -> list[dict]:
    contacts = await disc.run_pipeline(company, roles, provided_domain=domain)
    pool = await storage.get_pool()
    stored = []
    for c in contacts:
        try:
            row = await storage.upsert_contact(
                pool,
                job_id=job_id,
                company=c["company"],
                domain=c.get("domain"),
                name=c.get("name"),
                email=c.get("email"),
                role=c.get("role"),
                source=c.get("source"),
                verified=c.get("verified", "unverified"),
            )
            if row:
                stored.append(dict(row))
        except Exception as exc:
            logger.error("Failed to store contact %s: %s", c.get("email"), exc)
    return stored


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}


@app.post("/discover", tags=["discovery"])
async def discover(body: DiscoverRequest, background_tasks: BackgroundTasks):
    """
    Trigger contact discovery for a company.
    Runs asynchronously in the background; results are persisted to PostgreSQL.
    Poll GET /contacts?company=... to retrieve results.
    """
    background_tasks.add_task(
        _discover_and_store,
        body.company,
        body.roles,
        body.job_id,
        body.domain,
    )
    return {
        "triggered": True,
        "company": body.company,
        "roles": body.roles,
        "message": "Discovery running in background. Poll GET /contacts?company=... for results.",
    }


@app.get("/contacts", tags=["contacts"])
async def list_contacts_by_company(
    company: str = Query(..., description="Company name substring")
):
    pool = await storage.get_pool()
    rows = await storage.get_contacts_by_company(pool, company)
    return [ContactOut.from_record(r) for r in rows]


@app.get("/contacts/{job_id}", tags=["contacts"])
async def list_contacts_by_job(job_id: UUID):
    pool = await storage.get_pool()
    rows = await storage.get_contacts_by_job(pool, job_id)
    if not rows:
        raise HTTPException(status_code=404, detail="No contacts found for this job_id")
    return [ContactOut.from_record(r) for r in rows]


@app.delete("/contacts/{contact_id}", status_code=204, tags=["contacts"])
async def remove_contact(contact_id: UUID):
    pool = await storage.get_pool()
    deleted = await storage.delete_contact(pool, contact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found")
