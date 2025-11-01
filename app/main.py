from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html
from app.auth.router import router as auth_router
from app.auth.middleware import AuthMiddleware


app = FastAPI(title="Weather Outfit Recommender", version="0.1.0")

# -------------------------------
# Routers and middleware
# -------------------------------
app.include_router(auth_router)
app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4200",
        "http://10.0.2.2:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Health check
# -------------------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/me")
async def me(req: Request):
    return {"user_id": getattr(req.state, "user_id", None)}


# -------------------------------
# Custom Swagger UI (cookies + auth button)
# -------------------------------
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css",
        swagger_ui_parameters={
            "withCredentials": True,  # ✅ Send cookies automatically
        },
    )


# -------------------------------
# Custom OpenAPI schema (adds Authorize 🔒 button)
# -------------------------------
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description="Weather-Based Outfit Recommender API with JWT Authentication",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            # apply security only to protected routes
            if not method.get("operationId", "").startswith(("login", "register", "activate", "healthz")):
                method["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
