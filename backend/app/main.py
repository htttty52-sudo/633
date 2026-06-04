import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routes import router
from app.template_routes import router as template_router
from app.ota_routes import router as ota_router
from app.dashboard_routes import router as dashboard_router
from app.scheduler import start_scheduler, stop_scheduler
from app.redis_client import get_redis
from app.redis_streams import ensure_consumer_group
import app.template_models  # noqa: F401 - ensure tables are created
import app.ota_models  # noqa: F401 - ensure tables are created

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    r = get_redis()
    ensure_consumer_group(r)
    # Sync expected hashes to Redis for fast drift detection
    from app.database import SessionLocal
    from app.dashboard_crud import sync_expected_hashes_to_redis
    db = SessionLocal()
    try:
        sync_expected_hashes_to_redis(db)
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="嵌入式Linux系统构建与配置平台",
    description="设备管理API - 支持设备CRUD、心跳模拟、分布式OTA升级",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(template_router)
app.include_router(ota_router)
app.include_router(dashboard_router)


@app.get("/api/health")
def health_check():
    r = get_redis()
    redis_ok = r.ping()
    return {"status": "ok", "redis": redis_ok}
