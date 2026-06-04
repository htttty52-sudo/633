import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routes import router
from app.template_routes import router as template_router
from app.ota_routes import router as ota_router
from app.scheduler import start_scheduler, stop_scheduler
import app.template_models  # noqa: F401 - ensure tables are created
import app.ota_models  # noqa: F401 - ensure tables are created

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="嵌入式Linux系统构建与配置平台",
    description="设备管理API - 支持设备CRUD和心跳模拟",
    version="1.0.0",
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


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
