"""Entry point for the PCG FEC Agent API.

Loads environment variables, initializes the semantic layer and LangGraph,
then starts the FastAPI server.

Usage:
    python main.py
    # or: uvicorn main:app --reload
"""

from __future__ import annotations

import os
import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from pcg_agent.semantic_layer.mdl_reader import PCGSemanticLayer
from pcg_agent.ingestion.fec_loader import FECIngestion
from pcg_agent.query_engine.duckdb_engine import FECQueryEngine
from pcg_agent.graph.graph import build_graph, load_agent_spec
from pcg_agent.api._runtime import set_runtime
from pcg_agent.api.routes import router, _sessions

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "pcg_agent" / "config"
FEC_FILE = BASE_DIR / "FEC_blckbx_cannes_2025.xlsx"

app = FastAPI(
    title="PCG FEC Agent",
    description="Agent conversationnel pour l'analyse financière française à partir du FEC",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    """Initialize all components on server start."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        print("WARNING: GEMINI_API_KEY not set. LLM calls will fail.")
        print("Set it in .env file: GEMINI_API_KEY=your_actual_key")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=api_key,
        temperature=0.1,
    )

    semantic = PCGSemanticLayer(CONFIG_DIR)
    agent_spec = load_agent_spec(CONFIG_DIR)

    if FEC_FILE.exists():
        print(f"Auto-loading FEC: {FEC_FILE}")
        ingestion = FECIngestion()
        df = ingestion.load(FEC_FILE)
        engine = FECQueryEngine(df)
        exercices = ingestion.get_exercices(df)

        session_id = "default"
        _sessions[session_id] = {
            "engine": engine,
            "df": df,
            "exercices": exercices,
            "chat_history": [],
        }
        print(f"FEC loaded: {len(df)} entries, exercices: {exercices}")
        print(f"Default session created: session_id='{session_id}'")

        graph = build_graph(engine, semantic, llm, agent_spec)
    else:
        print(f"No FEC file found at {FEC_FILE}. Use /upload-fec to load one.")
        engine_placeholder = None
        graph = None

    set_runtime({
        "graph": graph,
        "semantic": semantic,
        "llm": llm,
        "agent_spec": agent_spec,
    })

    print("PCG FEC Agent ready!")
    print("Endpoints:")
    print("  POST /upload-fec  — Upload a FEC file")
    print("  POST /chat        — Ask a question (use session_id='default' for pre-loaded FEC)")


@app.get("/")
async def root():
    return {
        "service": "PCG FEC Agent",
        "version": "1.0.0",
        "endpoints": ["/upload-fec", "/chat"],
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
