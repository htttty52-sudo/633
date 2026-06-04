import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:password@localhost:3306/embedded_linux_platform")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "30"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))
HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT", "45"))
OTA_UPGRADE_SUCCESS_RATE = float(os.getenv("OTA_UPGRADE_SUCCESS_RATE", "0.8"))
OTA_BATCH_TIMEOUT = float(os.getenv("OTA_BATCH_TIMEOUT", "30.0"))
OTA_RETRY_BASE_DELAY = int(os.getenv("OTA_RETRY_BASE_DELAY", "10"))
WORKER_GROUP_NAME = os.getenv("WORKER_GROUP_NAME", "ota_workers")
WORKER_HEARTBEAT_INTERVAL = int(os.getenv("WORKER_HEARTBEAT_INTERVAL", "10"))
BATCH_COMPLETION_CHECK_INTERVAL = int(os.getenv("BATCH_COMPLETION_CHECK_INTERVAL", "5"))
