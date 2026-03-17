from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
from uuid import UUID, uuid4
import random, os

app = FastAPI()

# --- DATA MODELS ---
class Player(BaseModel):
    id: UUID
    display_name: str
    is_host: bool = False

class Session(BaseModel):
    id: UUID
    code: str
    players: List[Player] = []

# --- STORAGE ---
GAMES: Dict[str, Session] = {}

# --- API ENDPOINTS (Backend) ---
class CreateRequest(BaseModel):
    host_name: str

@app.get("/api")
def read_root():
    return {"status": "Synthesis Backend: Online", "active_games": len(GAMES)}

@app.post("/api/game/create")
async def create_game(req: CreateRequest):
    code = f"SYN-{random.randint(1000, 9999)}"
    host = Player(id=uuid4(), display_name=req.host_name, is_host=True)
    session = Session(id=uuid4(), code=code, players=[host])
    GAMES[code] = session
    return {"code": code, "player_id": host.id, "session_id": session.id}

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# --- FRONTEND SERVING ---

# Serve index.html at root
@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

# Serve static assets manually to avoid StaticFiles complexity on some serverless builds
@app.get("/assets/{file_path:path}")
async def serve_assets(file_path: str):
    full_path = f"static/assets/{file_path}"
    if os.path.exists(full_path):
        return FileResponse(full_path)
    raise HTTPException(status_code=404)

# Catch-all for React routing (redirect to index.html)
@app.exception_handler(404)
async def custom_404_handler(request, __):
    if not request.url.path.startswith("/api"):
        return FileResponse("static/index.html")
    return JSONResponse(status_code=404, content={"detail": "Not Found"})
