from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
from uuid import UUID, uuid4
import random, os

# Get base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI()

# --- DATA MODELS ---
class Player(BaseModel):
    id: UUID
    display_name: str
    is_host: bool = False
    role: Optional[str] = None
    faction: Optional[str] = None

class Session(BaseModel):
    id: UUID
    code: str
    status: str = "LOBBY" # LOBBY, ACTIVE, COMPLETED
    players: List[Player] = []

# --- STORAGE ---
GAMES: Dict[str, Session] = {}

# --- ENGINE LOGIC ---
def assign_roles(players: List[Player]):
    num_players = len(players)
    # Standard social deduction ratio: roughly 1/3 are infiltrators
    num_androids = 2 if num_players >= 6 else 1
    
    roles = (["ANDROID"] * num_androids) + (["HUMAN"] * (num_players - num_androids))
    random.shuffle(roles)
    
    for i, p in enumerate(players):
        p.role = roles[i]
        p.faction = "ANDROID" if roles[i] == "ANDROID" else "HUMAN"

# --- API ENDPOINTS (Backend) ---
class CreateRequest(BaseModel):
    host_name: str

class JoinRequest(BaseModel):
    display_name: str

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

@app.post("/api/game/{code}/join")
async def join_game(code: str, req: JoinRequest):
    if code not in GAMES:
        raise HTTPException(status_code=404, detail="Game not found")
    
    session = GAMES[code]
    if session.status != "LOBBY":
        raise HTTPException(status_code=400, detail="Game already started")
    
    player = Player(id=uuid4(), display_name=req.display_name)
    session.players.append(player)
    return {"player_id": player.id, "code": code}

@app.post("/api/game/{code}/start")
async def start_game(code: str, x_player_id: UUID = Header(...)):
    if code not in GAMES:
        raise HTTPException(status_code=404, detail="Game not found")
    
    session = GAMES[code]
    # Simple check: only the host (first player) can start
    if session.players[0].id != x_player_id:
        raise HTTPException(status_code=403, detail="Only the host can start the game")
    
    if len(session.players) < 5:
        raise HTTPException(status_code=400, detail="Minimum 5 players required to start")

    assign_roles(session.players)
    session.status = "ACTIVE"
    return {"status": "ACTIVE", "player_count": len(session.players)}

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# --- FRONTEND SERVING ---

# Serve index.html at root
@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_path)

# Serve static assets manually to avoid StaticFiles complexity on some serverless builds
@app.get("/assets/{file_path:path}")
async def serve_assets(file_path: str):
    full_path = os.path.join(STATIC_DIR, "assets", file_path)
    if os.path.exists(full_path):
        return FileResponse(full_path)
    raise HTTPException(status_code=404)

# Catch-all for React routing (redirect to index.html)
@app.exception_handler(404)
async def custom_404_handler(request, __):
    if not request.url.path.startswith("/api"):
        index_path = os.path.join(STATIC_DIR, "index.html")
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})
