"""FastAPI app for the recommendation service (loop owner + writes)."""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from . import db
from .candidates import by_id, load_universities
from .clients import make_rank_fn
from .llm import MockLLM
from .loop import iter_loop, run_loop
from .schemas import RecommendationRequest, RecommendationResponse, University

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
    universities = load_universities()
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
    universities = load_universities()
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
