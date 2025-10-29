from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.auth.router import router as auth_router

from app.auth.middleware import AuthMiddleware
from app.auth.router import router as auth_router


app = FastAPI(title="Weather Outfit Recommender")

app.include_router(auth_router)
app.add_middleware(AuthMiddleware)

# CORS (adjust origins for Android/emulator/web as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:4200", "http://10.0.2.2:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.add_middleware(AuthMiddleware)

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/me")
async def me(req: Request):
    return {"user_id": req.state.user_id}
