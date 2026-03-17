from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Synthesis Reset: Online", "message": "Ready to build the game logic step-by-step."}

@app.get("/health")
def health_check():
    return {"status": "ok"}
