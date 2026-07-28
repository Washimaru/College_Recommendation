"""FastAPI app for the deterministic scoring service."""
from __future__ import annotations

from fastapi import FastAPI

from .schemas import RankRequest, RankResponse
from .scoring import rank

app = FastAPI(title="scoring-service", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/rank", response_model=RankResponse)
def post_rank(request: RankRequest) -> RankResponse:
    return rank(request)
