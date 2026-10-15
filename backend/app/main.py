import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config.settings import settings
from .database.connection import Database
from .services.auth_service import AuthConfigError
from .routes import ai, analytics, auth, expenses, ingredients, meals, pantry, receipt, recipes, shopping

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pantrypilot")


def _initialise_database() -> None:
    """Create indexes and seed the catalog. Failures are logged, not fatal:
    /ready reports the database state and requests return 503 until it works."""
    from .services.auth_service import ensure_indexes as ensure_user_indexes
    from .services.expense_service import ExpenseService
    from .services.ingredient_catalog import seed_catalog
    from .services.inventory_service import InventoryService

    if not Database.ping():
        logger.error("MongoDB is not reachable at startup; check MONGODB_URI and Atlas network access.")
        return
    database = Database.get_db()
    try:
        seed_catalog(database)
        InventoryService.ensure_indexes(database)
        ensure_user_indexes(database)
        ExpenseService.ensure_indexes(database)
        shopping.ensure_indexes(database)
        logger.info("Connected to MongoDB database '%s'", settings.database_name)
    except Exception as e:
        logger.warning("Index/seed initialisation failed: %s", type(e).__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.jwt_secret_key:
        logger.error("JWT_SECRET_KEY is not set: sign-in and all private routes will return 503.")
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY is not set: receipts, recipes and meal plans are unavailable.")
    Database.connect_db()
    _initialise_database()
    yield
    Database.close_db()


app = FastAPI(
    title="PantryPilot AI API",
    description="Backend API for PantryPilot AI",
    version="2.0.0",
    lifespan=lifespan,
    # Interactive docs only outside production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # bearer tokens, not cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    # Path only: never log query strings, headers or bodies (may contain secrets).
    logger.info("%s %s -> %s (%.0f ms)", request.method, request.url.path,
                response.status_code, (time.perf_counter() - start) * 1000)
    return response


@app.exception_handler(AuthConfigError)
async def auth_not_configured(request: Request, exc: AuthConfigError):
    return JSONResponse(status_code=503, content={"detail": "Authentication is not configured on the server."})


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})


@app.get("/")
def read_root():
    return {"message": "PantryPilot AI API is running"}


@app.get("/health")
def health():
    """Liveness: the process is up. Does not touch external dependencies."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: critical dependencies are configured and reachable."""
    db_ok = Database.ping()
    checks = {
        "database": "ok" if db_ok else "unavailable",
        "auth": "ok" if settings.jwt_secret_key else "not_configured",
        "ai": "configured" if settings.gemini_api_key else "not_configured",
    }
    is_ready = db_ok and bool(settings.jwt_secret_key)
    return JSONResponse(status_code=200 if is_ready else 503,
                        content={"status": "ready" if is_ready else "not_ready", "checks": checks})


# Mirror the probes under /api so clients that only know the API base URL can use them.
app.add_api_route("/api/health", health, methods=["GET"], include_in_schema=False)
app.add_api_route("/api/ready", ready, methods=["GET"], include_in_schema=False)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(pantry.router, prefix="/api/pantry", tags=["pantry"])
app.include_router(receipt.router, prefix="/api/receipt", tags=["receipt"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])
app.include_router(ingredients.router, prefix="/api/ingredients", tags=["ingredients"])
app.include_router(meals.router, prefix="/api/meals", tags=["meals"])
app.include_router(expenses.router, prefix="/api/expenses", tags=["expenses"])
app.include_router(shopping.router, prefix="/api/shopping", tags=["shopping"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
