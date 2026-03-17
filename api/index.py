from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from uuid import UUID, uuid4
import random

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

# --- API ENDPOINTS ---
class CreateRequest(BaseModel):
    host_name: str

@app.get("/")
def read_root():
    return {"status": "Synthesis: Online", "active_games": len(GAMES)}

@app.post("/game/create")
async def create_game(req: CreateRequest):
    code = f"SYN-{random.randint(1000, 9999)}"
    host = Player(id=uuid4(), display_name=req.host_name, is_host=True)
    session = Session(id=uuid4(), code=code, players=[host])
    GAMES[code] = session
    return {"code": code, "player_id": host.id, "session_id": session.id}

@app.get("/health")
def health_check():
    return {"status": "ok"}
