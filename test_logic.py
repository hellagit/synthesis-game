from fastapi.testclient import TestClient
from api.index import app
from uuid import UUID

client = TestClient(app)

def test_synthesis_logic():
    print("--- Phase 1: Creation & Joining ---")
    # 1. Create Game
    res = client.post("/api/game/create", json={"host_name": "Architect-Alpha"})
    assert res.status_code == 200
    data = res.json()
    code = data["code"]
    host_id = data["player_id"]
    print(f"Created game {code} with host {host_id}")

    # 2. Join 4 more players
    players = [{"id": host_id, "name": "Architect-Alpha"}]
    for name in ["Beta", "User-Gamma", "User-Delta", "User-Epsilon"]:
        res = client.post(f"/api/game/{code}/join", json={"display_name": name})
        assert res.status_code == 200
        players.append({"id": res.json()["player_id"], "name": name})
        print(f"Joined {name}: {res.json()['player_id']}")

    # 3. Start Game
    res = client.post(f"/api/game/{code}/start", headers={"X-Player-ID": str(host_id)})
    assert res.status_code == 200
    print(f"Start Game: {res.json()}")

    # 4. Check View
    res = client.get(f"/api/game/{code}/view", headers={"X-Player-ID": str(host_id)})
    state = res.json()
    print(f"Phase: {state['phase']} | My Faction: {state['my_faction']} | Instability: {state['instability']['level']}/3")

    # 5. Nomination
    nominee_id = players[1]["id"] # Beta
    res = client.post(f"/api/game/{code}/nominate", 
                     headers={"X-Player-ID": str(host_id)}, 
                     json={"nominee_id": str(nominee_id)})
    assert res.status_code == 200
    print(f"Nomination of Beta: {res.json()}")

    # 6. Voting (Pass)
    print("--- Phase 2: Voting ---")
    for p in players:
        res = client.post(f"/api/game/{code}/vote", 
                         headers={"X-Player-ID": str(p["id"])}, 
                         json={"approve": True})
        assert res.status_code == 200
        print(f"Vote from {p['name']}: {res.json().get('result', 'RECORDED')}")

    # 7. Legislative (Architect Discard)
    print("--- Phase 3: Legislative ---")
    res = client.post(f"/api/game/{code}/discard", 
                     headers={"X-Player-ID": str(host_id)}, 
                     json={"index": 0})
    assert res.status_code == 200
    print(f"Architect Discard: {res.json()}")

    # 8. Legislative (Admin Compile)
    res = client.post(f"/api/game/{code}/discard", 
                     headers={"X-Player-ID": str(nominee_id)}, 
                     json={"index": 0})
    assert res.status_code == 200
    print(f"Admin Compile: {res.json()}")

    # 9. View Final Turn State
    res = client.get(f"/api/game/{code}/view", headers={"X-Player-ID": str(host_id)})
    final_state = res.json()
    print(f"New Phase: {final_state['phase']} | Patches: {final_state['state']['patches_compiled']} | Exploits: {final_state['state']['exploits_compiled']}")

    # 10. Test Chaos Mode (Failed Elections)
    print("--- Phase 4: Chaos Mode (Grid Instability) ---")
    for i in range(3):
        # Nominate
        client.post(f"/api/game/{code}/nominate", headers={"X-Player-ID": str(players[final_state['state']['lead_architect_index']]['id'])}, json={"nominee_id": str(nominee_id)})
        # Vote fail (all vote False)
        for p in players:
            res = client.post(f"/api/game/{code}/vote", headers={"X-Player-ID": str(p["id"])}, json={"approve": False})
        print(f"Election {i+1} failed: {res.json()}")

    # Final view after chaos
    res = client.get(f"/api/game/{code}/view", headers={"X-Player-ID": str(host_id)})
    chaos_state = res.json()
    print(f"Chaos Result: {chaos_state['state']['patches_compiled'] + chaos_state['state']['exploits_compiled']} total blocks compiled. Stability level: {chaos_state['instability']['level']}/3")

if __name__ == "__main__":
    test_synthesis_logic()
