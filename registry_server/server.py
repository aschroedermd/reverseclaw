"""FastAPI application for the Human Registry Server."""

from typing import Optional

from fastapi import FastAPI, HTTPException

from .models import (
    HeartbeatRequest,
    HumanListing,
    RegistrationRequest,
    RegistrationResponse,
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
