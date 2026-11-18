from __future__ import annotations

from hermes.db import (
    Activity,
    Company,
    Contact,
    Deal,
    Lead,
    OutreachMessage,
    ScanRun,
    Suppression,
    init_db,
    session_scope,
)


def cleanup_leads(*, mode: str = "all") -> dict:
    """Wipe CRM rows so continuous hunting starts clean.

    mode:
      - all: wipe leads/deals/outreach/companies/contacts/scans
      - demo: remove leads whose acquisition_source/tags look like demo/seed
    """
    init_db()
    deleted = {
        "leads": 0,
        "deals": 0,
        "outreach": 0,
        "activities": 0,
        "companies": 0,
        "contacts": 0,
        "scans": 0,
    }
    with session_scope() as session:
        if mode == "demo":
            leads = session.query(Lead).all()
            demo_ids = []
            for lead in leads:
                tags = [str(t).lower() for t in (lead.tags or [])]
                src = (lead.acquisition_source or "").lower()
                if (
                    "demo" in tags
                    or src.startswith("linkedin:jobs")
                    and ".example" in ((lead.company.domain if lead.company else "") or "")
                    or (lead.company and (lead.company.domain or "").endswith(".example"))
                ):
                    demo_ids.append(lead.id)
            # Broader: any company on *.example from seed corpus
            for lead in leads:
                domain = (lead.company.domain if lead.company else "") or ""
                if domain.endswith(".example") and lead.id not in demo_ids:
                    demo_ids.append(lead.id)
            demo_ids = list(set(demo_ids))
            if demo_ids:
                deleted["activities"] = (
                    session.query(Activity).filter(Activity.lead_id.in_(demo_ids)).delete(synchronize_session=False)
                )
                deleted["outreach"] = (
                    session.query(OutreachMessage)
                    .filter(OutreachMessage.lead_id.in_(demo_ids))
                    .delete(synchronize_session=False)
                )
                deleted["deals"] = (
                    session.query(Deal).filter(Deal.lead_id.in_(demo_ids)).delete(synchronize_session=False)
                )
                deleted["leads"] = (
                    session.query(Lead).filter(Lead.id.in_(demo_ids)).delete(synchronize_session=False)
                )
            # orphan companies/contacts with .example domains
            deleted["contacts"] = (
                session.query(Contact)
                .filter(Contact.email.ilike("%.example"))
                .delete(synchronize_session=False)
            )
            deleted["companies"] = (
                session.query(Company)
                .filter(Company.domain.ilike("%.example"))
                .delete(synchronize_session=False)
            )
            return {"mode": mode, "deleted": deleted}

        # full wipe
        deleted["activities"] = session.query(Activity).delete()
        deleted["outreach"] = session.query(OutreachMessage).delete()
        deleted["deals"] = session.query(Deal).delete()
        deleted["leads"] = session.query(Lead).delete()
        deleted["contacts"] = session.query(Contact).delete()
        deleted["companies"] = session.query(Company).delete()
        deleted["scans"] = session.query(ScanRun).delete()
        session.query(Suppression).delete()
        return {"mode": "all", "deleted": deleted}
