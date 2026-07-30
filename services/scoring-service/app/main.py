"""FastAPI app for the deterministic scoring service."""
from __future__ import annotations

from fastapi import FastAPI

from .schemas import ClassifyRequest, ClassifyResponse, RankRequest, RankResponse
from .scoring import classify_activity, rank

app = FastAPI(title="scoring-service", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/rank", response_model=RankResponse)
def post_rank(request: RankRequest) -> RankResponse:
    return rank(request)


@app.post("/classify", response_model=ClassifyResponse)
def classify(request: ClassifyRequest) -> ClassifyResponse:
    """Subject families for one activity. Deterministic, like everything here:
    no clock, no randomness, no network."""
    return ClassifyResponse(
        subjects=classify_activity(request.name, request.kind, request.description)
    )
