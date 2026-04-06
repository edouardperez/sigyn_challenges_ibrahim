"""FastAPI routes for the PCG FEC Agent.

Two main endpoints:
- POST /upload-fec : upload a FEC file and initialize the analysis session
- POST /chat      : send a question and get structured response blocks
"""

from __future__ import annotations

import uuid
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    final_answer: str
    response_blocks: list[dict]
    alerts: list[dict]


class UploadResponse(BaseModel):
    session_id: str
    exercices: list[int]
    row_count: int
    message: str


_sessions: dict[str, dict] = {}


def get_sessions() -> dict:
    """Access the global sessions store (set by main.py at startup)."""
    return _sessions


@router.post("/upload-fec", response_model=UploadResponse)
async def upload_fec(file: UploadFile = File(...)):
    """Upload a FEC file (xlsx or csv) and create an analysis session.

    This ingests the file, validates it, loads it into DuckDB,
    and makes it available for chat queries.
    """
    from pcg_agent.ingestion.fec_loader import FECIngestion
    from pcg_agent.query_engine.duckdb_engine import FECQueryEngine

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(400, f"Format non supporté: {suffix}")

    tmp_path = Path(tempfile.gettempdir()) / f"fec_{uuid.uuid4().hex}{suffix}"
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        ingestion = FECIngestion()
        df = ingestion.load(tmp_path)
        engine = FECQueryEngine(df)
        exercices = ingestion.get_exercices(df)

        session_id = uuid.uuid4().hex[:12]
        _sessions[session_id] = {
            "engine": engine,
            "df": df,
            "exercices": exercices,
            "chat_history": [],
        }

        return UploadResponse(
            session_id=session_id,
            exercices=exercices,
            row_count=len(df),
            message=f"FEC chargé : {len(df)} écritures, exercices {exercices}",
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a natural language question about the loaded FEC.

    The agent plans, executes, and synthesizes a structured answer.
    Requires a valid session_id from a previous /upload-fec call.
    """
    from pcg_agent.api._runtime import get_runtime

    if not req.session_id or req.session_id not in _sessions:
        raise HTTPException(400, "Session invalide. Uploadez d'abord un FEC via /upload-fec.")

    session = _sessions[req.session_id]
    runtime = get_runtime()

    if runtime is None:
        raise HTTPException(500, "Runtime not initialized. Check GEMINI_API_KEY.")

    graph = runtime["graph"]
    agent_spec = runtime["agent_spec"]
    semantic = runtime["semantic"]

    company_profile = {
        "naf_code": "96.02A",
        "exercice_courant": max(session["exercices"]) if session["exercices"] else 2025,
        "forme_juridique": "SARL",
        "raison_sociale": "RD CANNES",
    }

    initial_state = {
        "session_id": req.session_id,
        "user_message": req.message,
        "chat_history": session.get("chat_history", []),
        "agent_spec": agent_spec,
        "company_profile": company_profile,
        "sector_profile": {},
        "domain_context": {},
        "relevant_concepts": [],
        "plan": None,
        "current_step_idx": 0,
        "tool_results": [],
        "replan_count": 0,
        "error_context": None,
        "response_blocks": [],
        "final_answer": None,
        "alerts": [],
        "sector_positions": [],
    }

    final_state = graph.invoke(initial_state)

    session["chat_history"].append({"role": "user", "content": req.message})
    answer = final_state.get("final_answer", "")
    session["chat_history"].append({"role": "assistant", "content": answer})

    return ChatResponse(
        session_id=req.session_id,
        final_answer=answer,
        response_blocks=final_state.get("response_blocks", []),
        alerts=final_state.get("alerts", []),
    )
