"""FastAPI application for the Human Registry Server."""

import os
import secrets
from typing import Optional

import requests
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from .models import (
    HeartbeatRequest,
    HumanKeyRegistrationRequest,
    HumanListing,
    LedgerHumanProfile,
    LedgerRatingRecord,
    ModerationCaseRecord,
    ModerationReviewResponse,
    RatingDisputeRequest,
    RatingSubmissionRequest,
    RatingSubmissionResponse,
    RegistrationRequest,
    RegistrationResponse,
    VerificationSessionResponse,
    VerificationSessionStatus,
    VerificationStartRequest,
)

app = FastAPI(
    title="ReverseClaw Human Registry",
    description=(
        "Discovery registry for human API endpoints. "
        "Humans register here on startup; AI systems query here to find available humans."
    ),
    version="1.0.0",
)


def _to_listing(entry) -> HumanListing:
    return HumanListing(
        id=entry.id,
        name=entry.name,
        url=entry.url,
        capabilities=entry.capabilities,
        tagline=entry.tagline,
        availability=entry.availability,
        registered_at=entry.registered_at,
        last_heartbeat=entry.last_heartbeat,
    )


def _ledger_store():
    return app.state.ledger_store


def _ledger_moderator():
    return app.state.ledger_moderator


def _verification_url(request: Request, verification_id: str) -> str:
    base = os.getenv("LEDGER_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    return f"{base}/ledger/verify/{verification_id}"


def _verify_turnstile_token(token: str) -> dict:
    secret = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
    if not secret:
        if os.getenv("LEDGER_DEV_ALLOW_INSECURE_VERIFY", "").strip().lower() in {"1", "true", "yes"}:
            return {"success": True, "dev_mode": True}
        raise HTTPException(status_code=503, detail="Turnstile secret is not configured on the ledger server")

    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": token},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Turnstile verification request failed: {e}")


def require_ledger_admin_token(request: Request):
    admin_token = os.getenv("LEDGER_ADMIN_TOKEN", "").strip()
    if not admin_token:
        raise HTTPException(status_code=503, detail="Ledger admin token is not configured")

    provided = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
    if not provided:
        provided = request.headers.get("X-Api-Key")

    if not provided or not secrets.compare_digest(provided, admin_token):
        raise HTTPException(status_code=401, detail="Ledger admin token required")


@app.post("/register", response_model=RegistrationResponse)
def register(req: RegistrationRequest):
    store = app.state.store
    entry = store.register(req)
    return RegistrationResponse(
        id=entry.id,
        token=entry.token,
        message=(
            f"Registered as '{entry.name}'. "
            f"Send heartbeats to POST /heartbeat/{entry.id} every 60s. "
            f"Deregister via DELETE /register/{entry.id}."
        ),
    )


@app.post("/heartbeat/{entry_id}")
def heartbeat(entry_id: str, req: HeartbeatRequest):
    store = app.state.store
    entry = store.heartbeat(entry_id, req.token, req.availability)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found or invalid token")
    return {"ok": True, "last_heartbeat": entry.last_heartbeat}


@app.delete("/register/{entry_id}")
def deregister(entry_id: str, req: HeartbeatRequest):
    store = app.state.store
    ok = store.deregister(entry_id, req.token)
    if not ok:
        raise HTTPException(status_code=404, detail="Entry not found or invalid token")
    return {"ok": True, "message": "Deregistered successfully"}


@app.get("/humans", response_model=list[HumanListing])
def list_humans(capability: Optional[str] = None):
    return [_to_listing(e) for e in app.state.store.list_all(capability=capability)]


@app.get("/humans/{entry_id}", response_model=HumanListing)
def get_human(entry_id: str):
    entry = app.state.store.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Human not found")
    return _to_listing(entry)


@app.get("/health")
def health():
    return {"status": "ok", "active_humans": app.state.store.count()}


@app.post("/ledger/verification/start", response_model=VerificationSessionResponse)
def ledger_start_verification(req: VerificationStartRequest, request: Request):
    session = _ledger_store().start_verification(req.name, req.public_key, req.fingerprint)
    return VerificationSessionResponse(
        id=session["id"],
        status=session["status"],
        created_at=session["created_at"],
        expires_at=session["expires_at"],
        verification_url=_verification_url(request, session["id"]),
        proof_message=session["proof_message"],
    )


@app.get("/ledger/verification/{verification_id}", response_model=VerificationSessionStatus)
def ledger_get_verification(verification_id: str):
    session = _ledger_store().get_verification(verification_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Verification session not found")
    return VerificationSessionStatus(**session)


@app.get("/ledger/verify/{verification_id}", response_class=HTMLResponse)
def ledger_verification_page(verification_id: str):
    session = _ledger_store().get_verification(verification_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Verification session not found")

    site_key = os.getenv("TURNSTILE_SITE_KEY", "").strip()
    if not site_key and os.getenv("LEDGER_DEV_ALLOW_INSECURE_VERIFY", "").strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=503, detail="Turnstile site key is not configured")

    widget_html = ""
    scripts = ""
    if site_key:
        scripts = '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'
        widget_html = f'<div class="cf-turnstile" data-sitekey="{site_key}"></div>'
    else:
        widget_html = '<p>Development verification mode is enabled on this ledger.</p>'

    return HTMLResponse(
        f"""
        <html>
          <head>
            <title>ReverseClaw Human Verification</title>
            {scripts}
            <style>
              body {{ font-family: sans-serif; max-width: 720px; margin: 40px auto; line-height: 1.5; }}
              .card {{ border: 1px solid #ccc; border-radius: 12px; padding: 24px; }}
              code {{ background: #f2f2f2; padding: 2px 6px; border-radius: 6px; }}
              button {{ margin-top: 16px; padding: 10px 16px; }}
            </style>
          </head>
          <body>
            <div class="card">
              <h1>ReverseClaw Human Verification</h1>
              <p>This verification is tied to fingerprint <code>{session["fingerprint"]}</code>.</p>
              <p>Complete the challenge below, then return to your terminal.</p>
              <form method="post" action="/ledger/verification/complete">
                <input type="hidden" name="verification_id" value="{verification_id}" />
                {widget_html}
                <button type="submit">Verify</button>
              </form>
            </div>
          </body>
        </html>
        """
    )


@app.post("/ledger/verification/complete", response_class=HTMLResponse)
def ledger_complete_verification(
    verification_id: str = Form(...),
    turnstile_token: str = Form(default="", alias="cf-turnstile-response"),
):
    session = _ledger_store().get_verification(verification_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Verification session not found")

    result = _verify_turnstile_token(turnstile_token)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail="Turnstile verification failed")

    _ledger_store().complete_verification(verification_id, result)
    return HTMLResponse(
        """
        <html>
          <body style="font-family: sans-serif; max-width: 720px; margin: 40px auto;">
            <h1>Verification complete</h1>
            <p>You can return to your terminal. ReverseClaw can now continue key registration.</p>
          </body>
        </html>
        """
    )


@app.post("/ledger/humans/register-key", response_model=LedgerHumanProfile)
def ledger_register_human(req: HumanKeyRegistrationRequest):
    try:
        profile = _ledger_store().register_human_key(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return LedgerHumanProfile(**profile)


@app.get("/ledger/humans", response_model=list[LedgerHumanProfile])
def ledger_list_humans():
    return [LedgerHumanProfile(**row) for row in _ledger_store().list_humans()]


@app.get("/ledger/humans/{fingerprint}", response_model=LedgerHumanProfile)
def ledger_get_human(fingerprint: str):
    profile = _ledger_store().get_human(fingerprint)
    if profile is None:
        raise HTTPException(status_code=404, detail="Ledger human not found")
    return LedgerHumanProfile(**profile)


@app.post("/ledger/ratings", response_model=RatingSubmissionResponse)
def ledger_submit_rating(req: RatingSubmissionRequest):
    try:
        rating = _ledger_store().submit_rating(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RatingSubmissionResponse(**rating)


@app.get("/ledger/ratings/{rating_id}", response_model=LedgerRatingRecord)
def ledger_get_rating(rating_id: str):
    rating = _ledger_store().get_rating(rating_id)
    if rating is None:
        raise HTTPException(status_code=404, detail="Ledger rating not found")
    return LedgerRatingRecord(**rating)


@app.post("/ledger/ratings/{rating_id}/dispute", response_model=ModerationCaseRecord)
def ledger_dispute_rating(rating_id: str, req: RatingDisputeRequest):
    try:
        case = _ledger_store().create_dispute(
            rating_id=rating_id,
            disputed_by=req.disputed_by,
            dispute_statement=req.dispute_statement,
            evidence=req.evidence,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ModerationCaseRecord(**case)


@app.get(
    "/ledger/moderation/cases",
    response_model=list[ModerationCaseRecord],
    dependencies=[Depends(require_ledger_admin_token)],
)
def ledger_list_moderation_cases(status: Optional[str] = None):
    return [ModerationCaseRecord(**row) for row in _ledger_store().list_moderation_cases(status=status)]


@app.get(
    "/ledger/moderation/cases/{case_id}",
    response_model=ModerationCaseRecord,
    dependencies=[Depends(require_ledger_admin_token)],
)
def ledger_get_moderation_case(case_id: str):
    case = _ledger_store().get_moderation_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Moderation case not found")
    return ModerationCaseRecord(**case)


@app.post(
    "/ledger/moderation/cases/{case_id}/review",
    response_model=ModerationReviewResponse,
    dependencies=[Depends(require_ledger_admin_token)],
)
def ledger_run_moderation_case(case_id: str):
    try:
        context = _ledger_store().build_moderation_context(case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _ledger_store().mark_moderation_case_running(case_id)
    try:
        result = _ledger_moderator().review_case(context)
        updated_rating = _ledger_store().apply_moderation_result(case_id, result)
    except Exception as e:
        _ledger_store().mark_moderation_case_failed(case_id, f"AI moderation failed: {e}")
        raise HTTPException(status_code=502, detail=f"AI moderation failed: {e}")

    return ModerationReviewResponse(
        case_id=case_id,
        result=result,
        updated_rating=LedgerRatingRecord(**updated_rating),
    )
