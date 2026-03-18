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

# --- DATA MODELS (Matching Frontend Expectations) ---

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
    faction: Optional[str] = None # "resistance" or "android"
    role: Optional[str] = None # "ALPHA_CONSTRUCT", "ROGUE_ANDROID", "HUMAN_RESISTANCE"
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
    codeBlocks: Optional[List[str]] = None # "patch" or "exploit"
    architectDiscarded: Optional[int] = None
    adminSelected: Optional[int] = None
    scanResult: Optional[str] = None
    powerTarget: Optional[str] = None
    activePower: Optional[str] = None

class Message(BaseModel):
    id: str
    type: str # "briefing", "system", "intel", "emergency"
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
    phase: str = "lobby" # briefing, deliberation, election, system_update, executive_power, alpha_election, game_over
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

# --- STORAGE ---
GAMES: Dict[str, GameSession] = {}

# --- HELPER LOGIC ---

def initialize_deck():
    deck = ["exploit"] * 11 + ["patch"] * 5
    random.shuffle(deck)
    return deck

def assign_roles(session: GameSession):
    num_players = len(session.players)
    if num_players >= 7: num_androids = 3
    elif num_players >= 5: num_androids = 2
    else: num_androids = 1 
    
    roles_list = ["ALPHA_CONSTRUCT"] + (["ROGUE_ANDROID"] * (num_androids - 1)) + (["HUMAN_RESISTANCE"] * (num_players - num_androids))
    random.shuffle(roles_list)
    
    for i, p in enumerate(session.players):
        p.role = roles_list[i]
        p.faction = "android" if p.role in ["ALPHA_CONSTRUCT", "ROGUE_ANDROID"] else "resistance"
        p.qrCode = f"SYN-{uuid4().hex[:8].upper()}"
        
        # Add Briefing Message
        session.messages.append(Message(
            id=str(uuid4()),
            type="briefing",
            subject="MISSION START",
            body=f"Your assigned role is: {p.role}. Your faction is: {p.faction.upper()}.",
            timestamp=int(time.time() * 1000)
        ))
        
    # Find Alpha
    alpha = next((p for p in session.players if p.role == "ALPHA_CONSTRUCT"), None)
    if alpha:
        session.alphaConstructId = alpha.id

def advance_lead_architect(session: GameSession):
    alive_players = [p for p in session.players if p.isAlive]
    current_index = -1
    for i, p in enumerate(alive_players):
        if p.id == session.round.leadArchitectId:
            current_index = i
            break
    
    next_index = (current_index + 1) % len(alive_players)
    session.round.leadArchitectId = alive_players[next_index].id

# --- API ENDPOINTS (Matching Perplexity Frontend) ---

class CreateRequest(BaseModel):
    hostName: str
    config: GameConfig

@app.post("/api/games")
async def create_game(req: CreateRequest):
    game_id = str(uuid4())
    join_code = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=6))
    host_id = str(uuid4())
    
    host = Player(id=host_id, name=req.hostName, isHost=True)
    session = GameSession(
        id=game_id,
        joinCode=join_code,
        config=req.config,
        players=[host],
        hostId=host_id
    )
    GAMES[game_id] = session
    return session

class JoinRequest(BaseModel):
    joinCode: str
    playerName: str

@app.post("/api/games/join")
async def join_game(req: JoinRequest):
    session = next((s for s in GAMES.values() if s.joinCode == req.joinCode), None)
    if not session: raise HTTPException(status_code=404, detail="Game not found")
    if session.phase != "lobby": raise HTTPException(status_code=400, detail="Game started")
    
    player_id = str(uuid4())
    player = Player(id=player_id, name=req.playerName)
    session.players.append(player)
    return {"gameId": session.id, "player": player}

@app.get("/api/games/{id}")
async def get_game(id: str):
    if id not in GAMES: raise HTTPException(status_code=404)
    return GAMES[id]

@app.post("/api/games/{id}/start")
async def start_game(id: str):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    if len(session.players) < 5: raise HTTPException(status_code=400, detail="Min 5 players")
    
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

class NominateRequest(BaseModel):
    rootAdminId: str

@app.post("/api/games/{id}/nominate")
async def nominate(id: str, req: NominateRequest):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    session.round.nominatedAdminId = req.rootAdminId
    session.phase = "election"
    session.round.electionVotes = []
    return session

class VoteRequest(BaseModel):
    approve: bool

@app.post("/api/games/{id}/vote/{playerId}")
async def cast_vote(id: str, playerId: str, req: VoteRequest):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    
    # Check if already voted
    if any(v.playerId == playerId for v in session.round.electionVotes):
        raise HTTPException(status_code=400, detail="Already voted")
        
    session.round.electionVotes.append(Vote(playerId=playerId, approve=req.approve))
    
    # Resolve if all voted
    alive_voters = [p for p in session.players if p.isAlive and not p.isOverridden]
    if len(session.round.electionVotes) >= len(alive_voters):
        approves = sum(1 for v in session.round.electionVotes if v.approve)
        if approves > len(alive_voters) / 2:
            session.phase = "system_update"
            session.round.rootAdminId = session.round.nominatedAdminId
            session.round.failedElections = 0
            # Draw 3
            session.round.codeBlocks = [session.deck.pop(0) for _ in range(3)]
        else:
            session.round.failedElections += 1
            if session.round.failedElections >= 3:
                # CHAOS
                top = session.deck.pop(0)
                if top == "patch": session.patches += 1
                else: session.exploits += 1
                session.round.failedElections = 0
                advance_lead_architect(session)
                session.phase = "deliberation"
            else:
                advance_lead_architect(session)
                session.phase = "deliberation"
                
    return session

class IndexRequest(BaseModel):
    index: int

@app.post("/api/games/{id}/discard")
async def architect_discard(id: str, req: IndexRequest):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    session.round.architectDiscarded = req.index
    discarded = session.round.codeBlocks[req.index]
    session.recycle_bin.append(discarded)
    return session

@app.post("/api/games/{id}/compile")
async def admin_compile(id: str, req: IndexRequest):
    session = GAMES.get(id)
    if not session: raise HTTPException(status_code=404)
    
    # Filter out discarded
    remaining = [b for i, b in enumerate(session.round.codeBlocks) if i != session.round.architectDiscarded]
    compiled = remaining[req.index]
    
    # Recycle the other one
    other = remaining[1-req.index]
    session.recycle_bin.append(other)
    
    if compiled == "patch": session.patches += 1
    else: session.exploits += 1
    
    # Check win
    if session.patches >= 5: session.phase = "game_over"; session.winner = "resistance"
    elif session.exploits >= 6: session.phase = "game_over"; session.winner = "android"
    else:
        advance_lead_architect(session)
        session.phase = "deliberation"
        # Reset round state
        session.round.codeBlocks = None
        session.round.architectDiscarded = None
        
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

# Catch-all for React routing
@app.exception_handler(404)
async def custom_404_handler(request, __):
    if not request.url.path.startswith("/api"):
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
    return JSONResponse(status_code=404, content={"detail": "Not Found"})
