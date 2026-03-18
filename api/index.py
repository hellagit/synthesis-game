from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
import random, os, time, traceback

# Get base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Synthesis Full Engine")

# --- DATA MODELS ---

class GameConfig(BaseModel):
    gameDuration: str = "medium"
    missionFrequency: str = "medium"
    blackoutEnabled: bool = True

class Player(BaseModel):
    id: str
    name: str
    isHost: bool = False
    isAlive: bool = True
    isOverridden: bool = False
    avatarUrl: Optional[str] = None
    faction: Optional[str] = None
    role: Optional[str] = None
    qrCode: str = ""

class Vote(BaseModel):
    playerId: str
    approve: bool

class GameRound(BaseModel):
    roundNumber: int = 1
    leadArchitectId: Optional[str] = None
    nominatedAdminId: Optional[str] = None
    rootAdminId: Optional[str] = None
    failedElections: int = 0
    electionVotes: List[Vote] = []
    codeBlocks: Optional[List[str]] = None
    architectDiscarded: Optional[int] = None
    adminSelected: Optional[int] = None
    scanResult: Optional[str] = None
    powerTarget: Optional[str] = None
    activePower: Optional[str] = None

class Message(BaseModel):
    id: str
    type: str
    subject: str
    body: str
    timestamp: int
    isRead: bool = False

class Mission(BaseModel):
    id: str
    name: str
    description: str
    difficulty: str
    assignedTo: str
    completed: bool = False
    requiresQrScan: bool = False
    expiresAt: int

class GameSession(BaseModel):
    id: str
    joinCode: str
    phase: str = "lobby"
    config: GameConfig
    players: List[Player] = []
    messages: List[Message] = []
    missions: List[Mission] = []
    round: GameRound = Field(default_factory=GameRound)
    patches: int = 0
    exploits: int = 0
    alphaConstructId: Optional[str] = None
    hostId: str
    isBlackoutWindow: bool = False
    powerBoard: List[Optional[str]] = ["vulnerability_scan", "override_command", "process_deletion", None, None, None]
    deck: List[str] = []
    recycle_bin: List[str] = []

# --- IN-MEMORY STORAGE ---
GAMES: Dict[str, GameSession] = {}

# --- ENGINE LOGIC ---

def initialize_deck():
    deck = ["exploit"] * 11 + ["patch"] * 5
    random.shuffle(deck)
    return deck

def assign_roles(session: GameSession):
    num_players = len(session.players)
    num_androids = 3 if num_players >= 7 else (2 if num_players >= 5 else 1)
    
    roles_list = ["ALPHA_CONSTRUCT"] + (["ROGUE_ANDROID"] * (num_androids - 1)) + (["HUMAN_RESISTANCE"] * (num_players - num_androids))
    random.shuffle(roles_list)
    
    for i, p in enumerate(session.players):
        p.role = roles_list[i]
        p.faction = "android" if p.role in ["ALPHA_CONSTRUCT", "ROGUE_ANDROID"] else "resistance"
        p.qrCode = f"SYN-{uuid4().hex[:8].upper()}"
        session.messages.append(Message(
            id=str(uuid4()),
            type="briefing",
            subject="MISSION START",
            body=f"Your assigned role is: {p.role}. Your faction is: {p.faction.upper()}.",
            timestamp=int(time.time() * 1000)
        ))
    
    alpha = next((p for p in session.players if p.role == "ALPHA_CONSTRUCT"), None)
    if alpha: session.alphaConstructId = alpha.id

def advance_lead_architect(session: GameSession):
    alive_players = [p for p in session.players if p.isAlive]
    if not alive_players: return
    
    current_id = session.round.leadArchitectId
    current_index = -1
    for i, p in enumerate(alive_players):
        if p.id == current_id:
            current_index = i
            break
    
    next_index = (current_index + 1) % len(alive_players)
    session.round.leadArchitectId = alive_players[next_index].id

# --- API ENDPOINTS ---

@app.post("/api/games")
async def create_game(req: Any = None, request: Request = None):
    # Flexible request handling for different frontend versions
    body = await request.json() if request else {}
    host_name = body.get("hostName", "Operator")
    config_data = body.get("config", {})
    
    game_id = str(uuid4())
    join_code = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=6))
    host_id = str(uuid4())
    
    host = Player(id=host_id, name=host_name, isHost=True)
    session = GameSession(
        id=game_id,
        joinCode=join_code,
        config=GameConfig(**config_data),
        players=[host],
        hostId=host_id
    )
    GAMES[game_id] = session
    return session

@app.post("/api/games/join")
async def join_game(req: Dict[str, str]):
    join_code = req.get("joinCode")
    player_name = req.get("playerName", "Operative")
    
    session = next((s for s in GAMES.values() if s.joinCode == join_code), None)
    if not session: raise HTTPException(status_code=404, detail="Game not found")
    
    player = Player(id=str(uuid4()), name=player_name)
    session.players.append(player)
    return {"gameId": session.id, "player": player}

@app.get("/api/games/{id}")
async def get_game(id: str):
    if id not in GAMES: raise HTTPException(status_code=404)
    return GAMES[id]

@app.get("/api/games/{id}/player/{playerId}")
async def get_game_for_player(id: str, playerId: str):
    if id not in GAMES: raise HTTPException(status_code=404)
    return GAMES[id] # In a real game, we'd filter roles here

@app.post("/api/games/{id}/start")
async def start_game(id: str):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    assign_roles(session)
    session.deck = initialize_deck()
    session.phase = "briefing"
    return session

@app.post("/api/games/{id}/deliberate")
async def begin_deliberation(id: str):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    session.phase = "deliberation"
    session.round.leadArchitectId = session.players[0].id
    return session

@app.post("/api/games/{id}/nominate")
async def nominate(id: str, req: Dict[str, str]):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    session.round.nominatedAdminId = req.get("rootAdminId")
    session.phase = "election"
    session.round.electionVotes = []
    return session

@app.post("/api/games/{id}/vote/{playerId}")
async def cast_vote(id: str, playerId: str, req: Dict[str, bool]):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    
    session.round.electionVotes = [v for v in session.round.electionVotes if v.playerId != playerId]
    session.round.electionVotes.append(Vote(playerId=playerId, approve=req.get("approve", False)))
    
    alive_voters = [p for p in session.players if p.isAlive and not p.isOverridden]
    if len(session.round.electionVotes) >= len(alive_voters):
        approves = sum(1 for v in session.round.electionVotes if v.approve)
        if approves > len(alive_voters) / 2:
            session.phase = "system_update"
            session.round.rootAdminId = session.round.nominatedAdminId
            session.round.failedElections = 0
            session.round.codeBlocks = [session.deck.pop(0) for _ in range(3)]
        else:
            session.round.failedElections += 1
            if session.round.failedElections >= 3:
                top = session.deck.pop(0)
                if top == "patch": session.patches += 1
                else: session.exploits += 1
                session.round.failedElections = 0
            advance_lead_architect(session)
            session.phase = "deliberation"
    return session

@app.post("/api/games/{id}/discard")
async def architect_discard(id: str, req: Dict[str, int]):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    session.round.architectDiscarded = req.get("index")
    return session

@app.post("/api/games/{id}/compile")
async def admin_compile(id: str, req: Dict[str, int]):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    remaining = [b for i, b in enumerate(session.round.codeBlocks) if i != session.round.architectDiscarded]
    compiled = remaining[req.get("index", 0)]
    if compiled == "patch": session.patches += 1
    else: session.exploits += 1
    
    if session.patches >= 5: session.phase = "game_over"; session.winner = "resistance"
    elif session.exploits >= 6: session.phase = "game_over"; session.winner = "android"
    else:
        advance_lead_architect(session)
        session.phase = "deliberation"
        session.round.codeBlocks = None
        session.round.architectDiscarded = None
    return session

@app.post("/api/games/{id}/blackout")
async def toggle_blackout(id: str):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    session.isBlackoutWindow = not session.isBlackoutWindow
    return session

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
