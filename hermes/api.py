from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from hermes import __app_name__, __version__
from hermes.agents.cleanup import cleanup_leads, run_expiry_pass
from hermes.agents.continuous import count_strong_leads
from hermes.agents.pipeline import advance_lead, backfill_missing_drafts, mark_as_lead, run_scan
from hermes.analytics import dashboard_kpis, list_leads
from hermes.browser import camoufox_available, warmup_note
from hermes.config import DATA_DIR, get_settings
from hermes.db import Lead, OutreachMessage, get_session, init_db
from hermes.integrations import list_integrations
from hermes.outreach_send import prepare_send
from hermes.runtime import BUS

STATIC_DIR = Path(__file__).parent / "static"


class StageUpdate(BaseModel):
    stage: str
    note: str = ""


class ScanRequest(BaseModel):
    query: str = ""
    use_demo: bool = False
    use_reddit: bool = True
    use_web: bool = True
    limit_per_source: int = Field(25, ge=1, le=100)
    use_llm: bool = False


class CleanupRequest(BaseModel):
    mode: str = Field("all", pattern="^(all|demo|expired)$")


class SendRequest(BaseModel):
    subject_variant: str = "a"
    mark_sent: bool = True
    use_smtp: bool = False


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title=__app_name__, version=__version__)

    def db_dep():
        session = get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @app.get("/api/health")
    def health():
        settings = get_settings()
        strong = count_strong_leads(settings.strong_lead_min_score)
        return {
            "ok": True,
            "app": __app_name__,
            "version": __version__,
            "llm_enabled": settings.llm_enabled,
            "llm_provider": "openrouter" if settings.uses_openrouter else "openai",
            "llm_model": settings.openai_model,
            "db": str(settings.db_path),
            "runner": BUS.snapshot(),
            "strong_leads": strong,
            "strong_lead_target": settings.strong_lead_target,
            "strong_lead_min_score": settings.strong_lead_min_score,
            "camoufox_available": camoufox_available(),
            "camoufox_enabled": settings.camoufox_enabled,
            "camoufox_hint": warmup_note(),
            "brand": "Intellytics",
        }

    @app.get("/api/kpis")
    def kpis(session: Session = Depends(db_dep)):
        return dashboard_kpis(session)

    @app.get("/api/leads")
    def leads(
        stage: Optional[str] = None,
        platform: Optional[str] = None,
        min_score: float = Query(0, ge=0, le=100),
        revenue_fit_only: bool = False,
        record_kind: Optional[str] = None,
        include_expired: bool = False,
        session: Session = Depends(db_dep),
    ):
        return {
            "items": list_leads(
                session,
                stage=stage,
                platform=platform,
                min_score=min_score,
                revenue_fit_only=revenue_fit_only,
                record_kind=record_kind,
                include_expired=include_expired,
            )
        }

    @app.get("/api/leads/{lead_id}")
    def lead_detail(lead_id: int, session: Session = Depends(db_dep)):
        lead = (
            session.query(Lead)
            .options(
                joinedload(Lead.company),
                joinedload(Lead.contact),
                joinedload(Lead.deal),
                joinedload(Lead.activities),
                joinedload(Lead.outreach),
            )
            .filter(Lead.id == lead_id)
            .one_or_none()
        )
        if not lead:
            raise HTTPException(404, "Listing/lead not found")
        from hermes.analytics import _serialize_lead
        from hermes.outreach_send import build_mailto, build_tel

        data = _serialize_lead(lead)
        data["activities"] = [
            {
                "id": a.id,
                "kind": a.kind,
                "message": a.message,
                "meta": a.meta,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in sorted(lead.activities, key=lambda x: x.created_at or x.id, reverse=True)
        ]
        data["outreach"] = [
            {
                "id": o.id,
                "channel": o.channel,
                "subject_a": o.subject_a,
                "subject_b": o.subject_b,
                "body": o.body,
                "status": o.status,
            }
            for o in lead.outreach
        ]
        msg = lead.outreach[0] if lead.outreach else None
        data["send"] = {
            "mailto": build_mailto(lead, msg) if msg else None,
            "tel": build_tel(lead),
        }
        return data

    @app.post("/api/leads/{lead_id}/stage")
    def set_stage(
        lead_id: int,
        payload: Annotated[StageUpdate, Body()],
        session: Session = Depends(db_dep),
    ):
        try:
            lead = advance_lead(session, lead_id, payload.stage, payload.note)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        session.flush()
        from hermes.analytics import _serialize_lead

        return _serialize_lead(lead)

    @app.post("/api/leads/{lead_id}/send")
    def send_draft(lead_id: int, payload: Annotated[SendRequest, Body()]):
        result = prepare_send(
            lead_id,
            subject_variant=payload.subject_variant,
            mark_sent=payload.mark_sent,
            use_smtp=payload.use_smtp,
        )
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Send failed"))
        return result

    @app.post("/api/leads/{lead_id}/convert")
    def convert_to_lead(lead_id: int, session: Session = Depends(db_dep)):
        try:
            lead = mark_as_lead(session, lead_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        from hermes.analytics import _serialize_lead

        return _serialize_lead(lead)

    @app.post("/api/scan")
    def scan(payload: Annotated[ScanRequest, Body()]):
        settings = get_settings()
        imports = list((DATA_DIR / "imports").glob("*.csv"))
        stats = run_scan(
            query=payload.query,
            use_demo=payload.use_demo,
            use_reddit=payload.use_reddit,
            use_web=payload.use_web and bool(settings.serper_api_key),
            import_paths=imports,
            limit_per_source=payload.limit_per_source,
            use_llm=payload.use_llm or settings.hermes_use_llm,
        )
        return {
            "signals_found": stats.signals_found,
            "leads_created": stats.listings_created,
            "listings_created": stats.listings_created,
            "leads_skipped_existing": stats.leads_skipped,
            "qualified": stats.qualified,
            "outreach_drafted": stats.outreach_drafted,
            "expired": stats.expired,
            "suppressed": stats.suppressed,
            "deals_opened": stats.deals_opened,
            "notes": stats.notes,
            "strong_leads": count_strong_leads(settings.strong_lead_min_score),
            "hint": (
                "0 new listings — signals already stored or stale at crawl time."
                if stats.listings_created == 0 and stats.signals_found > 0
                else ""
            ),
        }

    @app.post("/api/cleanup")
    def cleanup(payload: Annotated[CleanupRequest, Body()]):
        return cleanup_leads(mode=payload.mode)

    @app.post("/api/expire")
    def expire():
        return run_expiry_pass()

    @app.post("/api/backfill-drafts")
    def backfill_drafts():
        n = backfill_missing_drafts(use_llm=False)
        return {"drafts_created": n}

    @app.get("/api/integrations")
    def integrations():
        return {"items": list_integrations()}

    @app.get("/api/runner")
    def runner():
        settings = get_settings()
        snap = BUS.snapshot()
        snap["strong_leads"] = count_strong_leads(settings.strong_lead_min_score)
        snap["strong_lead_target"] = settings.strong_lead_target
        return snap

    @app.post("/api/import")
    async def import_csv(file: UploadFile = File(...)):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "imports").mkdir(parents=True, exist_ok=True)
        dest = DATA_DIR / "imports" / (file.filename or "upload.csv")
        content = await file.read()
        dest.write_bytes(content)
        return {"saved": str(dest), "bytes": len(content)}

    @app.get("/api/outreach/{lead_id}")
    def outreach(lead_id: int, session: Session = Depends(db_dep)):
        rows = session.query(OutreachMessage).filter(OutreachMessage.lead_id == lead_id).all()
        return {
            "items": [
                {
                    "id": r.id,
                    "subject_a": r.subject_a,
                    "subject_b": r.subject_b,
                    "body": r.body,
                    "status": r.status,
                    "channel": r.channel,
                }
                for r in rows
            ]
        }

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
