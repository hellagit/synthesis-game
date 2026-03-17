from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
import random, os, time

# Get base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Synthesis Full Engine")

# --- DATA MODELS ---

class Player(BaseModel):
    id: UUID
    display_name: str
    is_host: bool = False
    is_alive: bool = True
    role: Optional[str] = None
    faction: Optional[str] = None
    inbox: List[str] = []

class GameState(BaseModel):
    phase: str = "LOBBY"
    round: int = 1
    lead_architect_index: int = 0
    nominated_admin_id: Optional[UUID] = None
    patches_compiled: int = 0
    exploits_compiled: int = 0
    election_tracker: int = 0
    drawn_blocks: List[str] = []
    votes: Dict[str, Optional[bool]] = {} # Use string for UUID keys
    game_over: bool = False
    winner: Optional[str] = None
    executive_power_available: Optional[str] = None

class Session(BaseModel):
    id: UUID
    code: str
    status: str = "LOBBY"
    players: List[Player] = []
    state: GameState = GameState()
    deck: List[str] = []
    recycle_bin: List[str] = []

# --- ENGINE LOGIC ---

def initialize_deck():
    # Phase 1: Fixed Deck - 11 Exploits, 5 Patches
    deck = ["EXPLOIT"] * 11 + ["PATCH"] * 5
    random.shuffle(deck)
    return deck

def check_reshuffle(session: Session):
    if len(session.deck) < 3:
        # Phase 2: Recycle Bin Reshuffle
        session.deck.extend(session.recycle_bin)
        session.recycle_bin = []
        random.shuffle(session.deck)

def compile_block(session: Session, block: str, is_chaos: bool = False):
    if block == "EXPLOIT":
        session.state.exploits_compiled += 1
        # Phase 4: Executive Power Balancing
        # Only trigger power if actively compiled by Admin (not chaos)
        if not is_chaos:
            session.state.executive_power_available = get_executive_power(session)
    else:
        session.state.patches_compiled += 1
    
    # Win conditions
    if session.state.patches_compiled >= 5:
        session.state.game_over = True
        session.state.winner = "HUMAN"
    elif session.state.exploits_compiled >= 6:
        session.state.game_over = True
        session.state.winner = "ANDROID"

def get_executive_power(session: Session) -> Optional[str]:
    # Logic for power unlocks based on exploit count
    count = session.state.exploits_compiled
    if count == 3: return "NETWORK_SCAN"
    if count == 4: return "IDENTITY_PROBE"
    if count == 5: return "FORCED_DISCONNECT"
    return None

def advance_turn(session: Session):
    session.state.lead_architect_index = (session.state.lead_architect_index + 1) % len(session.players)
    session.state.phase = "NOMINATION"
    session.state.nominated_admin_id = None
    session.state.votes = {str(p.id): None for p in session.players}
    session.state.drawn_blocks = []
    # Only reset power if it wasn't used? For MVP let's just reset
    session.state.executive_power_available = None
    check_reshuffle(session)

# --- API ENDPOINTS (Backend) ---

class CreateRequest(BaseModel):
    host_name: str

class JoinRequest(BaseModel):
    display_name: str

class NominateRequest(BaseModel):
    nominee_id: UUID

class VoteRequest(BaseModel):
    approve: bool

class DiscardRequest(BaseModel):
    index: int

@app.get("/api")
def read_root():
    return {"status": "Synthesis Engine: Online", "active_games": len(GAMES)}

@app.post("/api/game/create")
async def create_game(req: CreateRequest):
    code = f"SYN-{random.randint(1000, 9999)}"
    host = Player(id=uuid4(), display_name=req.host_name, is_host=True)
    session = Session(id=uuid4(), code=code, players=[host])
    GAMES[code] = session
    return {"code": code, "player_id": host.id, "session_id": session.id}

@app.post("/api/game/{code}/join")
async def join_game(code: str, req: JoinRequest):
    if code not in GAMES: raise HTTPException(status_code=404)
    session = GAMES[code]
    if session.status != "LOBBY": raise HTTPException(status_code=400, detail="Started")
    player = Player(id=uuid4(), display_name=req.display_name)
    session.players.append(player)
    return {"player_id": player.id}

@app.post("/api/game/{code}/start")
async def start_game(code: str, x_player_id: UUID = Header(...)):
    if code not in GAMES: raise HTTPException(status_code=404)
    session = GAMES[code]
    if session.players[0].id != x_player_id: raise HTTPException(status_code=403)
    if len(session.players) < 5: raise HTTPException(status_code=400, detail="Need 5 players")
    
    assign_roles(session.players)
    session.deck = initialize_deck()
    session.status = "ACTIVE"
    session.state.phase = "NOMINATION"
    session.state.votes = {str(p.id): None for p in session.players}
    return {"status": "STARTED"}

@app.get("/api/game/{code}/view")
async def get_view(code: str, x_player_id: UUID = Header(...)):
    if code not in GAMES: raise HTTPException(status_code=404)
    session = GAMES[code]
    player = next((p for p in session.players if p.id == x_player_id), None)
    if not player: raise HTTPException(status_code=403)
    
    visible_players = []
    for p in session.players:
        p_view = {"id": p.id, "name": p.display_name, "is_host": p.is_host, "is_alive": p.is_alive}
        if p.id == x_player_id or (player.faction == "ANDROID" and p.faction == "ANDROID"):
            p_view["role"] = p.role
            p_view["faction"] = p.faction
        visible_players.append(p_view)
        
    return {
        "code": session.code,
        "status": session.status,
        "phase": session.state.phase,
        "players": visible_players,
        "state": session.state,
        "my_role": player.role,
        "my_faction": player.faction,
        "inbox": player.inbox,
        "instability": {
            "level": session.state.election_tracker,
            "max": 3,
            "percent": (session.state.election_tracker / 3) * 100,
            "status": "DANGER" if session.state.election_tracker >= 2 else "STABLE"
        }
    }

@app.post("/api/game/{code}/nominate")
async def nominate(code: str, req: NominateRequest, x_player_id: UUID = Header(...)):
    session = GAMES.get(code)
    if not session: raise HTTPException(status_code=404)
    if session.state.phase != "NOMINATION": raise HTTPException(status_code=400)
    
    architect = session.players[session.state.lead_architect_index]
    if architect.id != x_player_id: raise HTTPException(status_code=403)
    
    session.state.nominated_admin_id = req.nominee_id
    session.state.phase = "ELECTION"
    return {"status": "ELECTION_STARTED"}

@app.post("/api/game/{code}/vote")
async def vote(code: str, req: VoteRequest, x_player_id: UUID = Header(...)):
    session = GAMES.get(code)
    if not session: raise HTTPException(status_code=404)
    if session.state.phase != "ELECTION": raise HTTPException(status_code=400)
    
    session.state.votes[str(x_player_id)] = req.approve
    
    # Check if all voted
    votes_cast = [v for v in session.state.votes.values() if v is not None]
    if len(votes_cast) == len(session.players):
        approves = sum(1 for v in votes_cast if v)
        if approves > len(session.players) / 2:
            session.state.phase = "LEGISLATIVE"
            session.state.election_tracker = 0
            # Draw 3 blocks
            session.state.drawn_blocks = [session.deck.pop(0) for _ in range(3)]
            return {"result": "PASSED"}
        else:
            session.state.election_tracker += 1
            # Add to inbox for all players
            for p in session.players:
                p.inbox.append(f"GRID INSTABILITY DETECTED: Level {session.state.election_tracker}/3. Election failure detected.")
            
            # Phase 3: Grid Instability (3 failed elections)
            if session.state.election_tracker >= 3:
                chaos_block = session.deck.pop(0)
                compile_block(session, chaos_block, is_chaos=True)
                session.state.election_tracker = 0
                for p in session.players:
                    p.inbox.append(f"SYSTEM OVERLOAD: Forced compile of top Code Block: {chaos_block}. Stability reset.")
                advance_turn(session)
                return {"result": "CHAOS", "block": chaos_block}
            
            advance_turn(session)
            return {"result": "FAILED"}
    return {"status": "VOTE_RECORDED"}

@app.post("/api/game/{code}/discard")
async def discard(code: str, req: DiscardRequest, x_player_id: UUID = Header(...)):
    session = GAMES.get(code)
    if not session: raise HTTPException(status_code=404)
    if session.state.phase != "LEGISLATIVE": raise HTTPException(status_code=400)
    
    # Simple check for demo: index 0, 1, or 2
    if len(session.state.drawn_blocks) == 3: # Architect discard
        architect = session.players[session.state.lead_architect_index]
        if architect.id != x_player_id: raise HTTPException(status_code=403)
        discarded = session.state.drawn_blocks.pop(req.index)
        # Phase 2: Discard goes into Recycle Bin
        session.recycle_bin.append(discarded)
        return {"status": "DISCARDED"}
    elif len(session.state.drawn_blocks) == 2: # Admin compile
        if session.state.nominated_admin_id != x_player_id: raise HTTPException(status_code=403)
        compiled = session.state.drawn_blocks.pop(req.index)
        # Remaining block also goes to recycle bin
        session.recycle_bin.append(session.state.drawn_blocks.pop(0))
        
        compile_block(session, compiled, is_chaos=False)
        
        advance_turn(session)
        return {"compiled": compiled}
    
    raise HTTPException(status_code=400)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# --- FRONTEND SERVING ---
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/assets/{file_path:path}")
async def serve_assets(file_path: str):
    full_path = os.path.join(STATIC_DIR, "assets", file_path)
    if os.path.exists(full_path): return FileResponse(full_path)
    raise HTTPException(status_code=404)

@app.exception_handler(404)
async def custom_404_handler(request, __):
    if not request.url.path.startswith("/api"):
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
    return JSONResponse(status_code=404, content={"detail": "Not Found"})
