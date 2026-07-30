"""FastAPI app for the recommendation service (loop owner + writes)."""
from __future__ import annotations

import json
from collections.abc import Callable

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from . import db
from .candidates import by_id, in_scope, load_universities
from .clients import make_classify_fn, make_rank_fn
from .llm import MockLLM
from .loop import iter_loop, run_loop
from .schemas import (
    ClassifyRequest,
    ClassifyResponse,
    RecommendationRequest,
    RecommendationResponse,
    University,
)

app = FastAPI(title="recommendation-service", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/universities")
def universities() -> dict[str, list[University]]:
    """The whole catalog, for the browse view.

    Returned in one response so the client can search instantly rather than
    issuing a request per keystroke; at 364 records that is cheaper than
    paginating. Read-only - no scoring, no loop, no writes.
    """
    catalog = sorted(load_universities(), key=lambda u: u.id)
    return {"universities": catalog}


@app.post("/recommend", response_model=RecommendationResponse)
def recommend(request: RecommendationRequest) -> RecommendationResponse:
    universities = in_scope(
        load_universities(),
        request.profile.preferences.scope,
        request.profile.preferences.institution_type,
    )
    rank_fn = make_rank_fn(request.profile, universities)
    llm = MockLLM(top_k=request.top_k)
    response = iter_loop(
        rank_fn, llm, request.profile, by_id(universities),
        max_iterations=request.max_iterations, top_k=request.top_k,
    )
    db.persist(request.profile, response)
    return response


@app.post("/recommend/stream")
def recommend_stream(request: RecommendationRequest) -> StreamingResponse:
    universities = in_scope(
        load_universities(),
        request.profile.preferences.scope,
        request.profile.preferences.institution_type,
    )
    rank_fn = make_rank_fn(request.profile, universities)
    llm = MockLLM(top_k=request.top_k)

    def sse():
        final = None
        for event in run_loop(
            rank_fn, llm, request.profile, by_id(universities),
            max_iterations=request.max_iterations, top_k=request.top_k,
        ):
            if event["type"] == "iteration":
                payload = event["step"].model_dump()
                yield f"event: iteration\ndata: {json.dumps(payload)}\n\n"
            else:
                final = event["response"]
                yield f"event: final\ndata: {final.model_dump_json()}\n\n"
        if final is not None:
            db.persist(request.profile, final)

    return StreamingResponse(sse(), media_type="text/event-stream")


def get_classify_fn() -> Callable[[str, str, str | None], list[str]]:
    """Injection point: tests override this so no unit test opens a socket."""
    return make_classify_fn()


@app.post("/activities/classify", response_model=ClassifyResponse)
def classify(
    request: ClassifyRequest,
    classify_fn: Callable[[str, str, str | None], list[str]] = Depends(get_classify_fn),
) -> ClassifyResponse:
    """Forward to scoring-service, which owns the pattern table."""
    try:
        subjects = classify_fn(request.name, request.kind, request.description)
    except (httpx.HTTPError, KeyError) as exc:
        raise HTTPException(status_code=502, detail="scoring_service_unavailable") from exc
    return ClassifyResponse(subjects=subjects)
