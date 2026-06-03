import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Device
from app.crud import check_heartbeat_timeout, create_device, update_heartbeat, DuplicateDeviceError
from app.schemas import DeviceCreate

SQLALCHEMY_TEST_URL = "sqlite://"

engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestDeviceCRUD:
    def test_create_device(self, client):
        response = client.post("/api/devices/", json={
            "device_id": "DEV-001",
            "model": "RK3588",
            "kernel_version": "5.10.110"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["device_id"] == "DEV-001"
        assert data["model"] == "RK3588"
        assert data["kernel_version"] == "5.10.110"
        assert data["is_online"] is True

    def test_create_duplicate_device_returns_409(self, client):
        payload = {"device_id": "DEV-DUP", "model": "IMX6", "kernel_version": "4.19.0"}
        client.post("/api/devices/", json=payload)
        response = client.post("/api/devices/", json=payload)
        assert response.status_code == 409

    def test_get_device(self, client):
        client.post("/api/devices/", json={
            "device_id": "DEV-GET",
            "model": "STM32MP1",
            "kernel_version": "5.15.0"
        })
        response = client.get("/api/devices/DEV-GET")
        assert response.status_code == 200
        assert response.json()["device_id"] == "DEV-GET"

    def test_get_nonexistent_device(self, client):
        response = client.get("/api/devices/NOPE")
        assert response.status_code == 404

    def test_list_devices(self, client):
        for i in range(3):
            client.post("/api/devices/", json={
                "device_id": f"DEV-LIST-{i}",
                "model": "Test",
                "kernel_version": "5.0.0"
            })
        response = client.get("/api/devices/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["devices"]) == 3

    def test_filter_online_devices(self, client, db_session):
        client.post("/api/devices/", json={"device_id": "ONLINE-1", "model": "A", "kernel_version": "5.0"})
        client.post("/api/devices/", json={"device_id": "OFFLINE-1", "model": "B", "kernel_version": "5.0"})

        device = db_session.query(Device).filter(Device.device_id == "OFFLINE-1").first()
        device.is_online = False
        db_session.commit()

        response = client.get("/api/devices/?is_online=true")
        assert response.json()["total"] == 1
        assert response.json()["devices"][0]["device_id"] == "ONLINE-1"

        response = client.get("/api/devices/?is_online=false")
        assert response.json()["total"] == 1
        assert response.json()["devices"][0]["device_id"] == "OFFLINE-1"

    def test_update_device(self, client):
        client.post("/api/devices/", json={"device_id": "DEV-UPD", "model": "Old", "kernel_version": "4.0"})
        response = client.put("/api/devices/DEV-UPD", json={"model": "New", "kernel_version": "5.0"})
        assert response.status_code == 200
        assert response.json()["model"] == "New"

    def test_delete_device(self, client):
        client.post("/api/devices/", json={"device_id": "DEV-DEL", "model": "X", "kernel_version": "5.0"})
        response = client.delete("/api/devices/DEV-DEL")
        assert response.status_code == 204
        response = client.get("/api/devices/DEV-DEL")
        assert response.status_code == 404


class TestHeartbeat:
    def test_heartbeat_updates_timestamp(self, client):
        client.post("/api/devices/", json={"device_id": "HB-1", "model": "X", "kernel_version": "5.0"})
        response = client.post("/api/devices/HB-1/heartbeat")
        assert response.status_code == 200
        assert response.json()["is_online"] is True

    def test_heartbeat_timeout_marks_offline(self, db_session):
        """Test: device with stale heartbeat is marked offline after timeout (45s)."""
        device = Device(
            device_id="TIMEOUT-1",
            model="TestModel",
            kernel_version="5.10.0",
            is_online=True,
            last_heartbeat=datetime.utcnow() - timedelta(seconds=60),
        )
        db_session.add(device)
        db_session.commit()

        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 1

        db_session.refresh(device)
        assert device.is_online is False

    def test_heartbeat_within_timeout_stays_online(self, db_session):
        """Test: device with recent heartbeat (within 45s) remains online."""
        device = Device(
            device_id="ALIVE-1",
            model="TestModel",
            kernel_version="5.10.0",
            is_online=True,
            last_heartbeat=datetime.utcnow() - timedelta(seconds=10),
        )
        db_session.add(device)
        db_session.commit()

        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 0

        db_session.refresh(device)
        assert device.is_online is True

    def test_device_recovers_online_after_heartbeat(self, db_session):
        """Test: an offline device is set back online when heartbeat is within threshold."""
        device = Device(
            device_id="RECOVER-1",
            model="TestModel",
            kernel_version="5.10.0",
            is_online=False,
            last_heartbeat=datetime.utcnow() - timedelta(seconds=10),
        )
        db_session.add(device)
        db_session.commit()

        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 0

        db_session.refresh(device)
        assert device.is_online is True

    def test_multiple_devices_timeout(self, db_session):
        """Test: multiple devices with different heartbeat ages relative to 45s threshold."""
        stale_time = datetime.utcnow() - timedelta(seconds=60)
        fresh_time = datetime.utcnow() - timedelta(seconds=5)

        devices = [
            Device(device_id="MULTI-1", model="A", kernel_version="5.0", is_online=True, last_heartbeat=stale_time),
            Device(device_id="MULTI-2", model="B", kernel_version="5.0", is_online=True, last_heartbeat=stale_time),
            Device(device_id="MULTI-3", model="C", kernel_version="5.0", is_online=True, last_heartbeat=fresh_time),
        ]
        db_session.add_all(devices)
        db_session.commit()

        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 2

        for d in devices[:2]:
            db_session.refresh(d)
            assert d.is_online is False
        db_session.refresh(devices[2])
        assert devices[2].is_online is True

    def test_already_offline_not_counted(self, db_session):
        """Already-offline devices with stale heartbeat are not re-counted."""
        device = Device(
            device_id="ALREADY-OFF",
            model="X",
            kernel_version="5.0",
            is_online=False,
            last_heartbeat=datetime.utcnow() - timedelta(seconds=300),
        )
        db_session.add(device)
        db_session.commit()

        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 0
        db_session.refresh(device)
        assert device.is_online is False

    def test_heartbeat_stop_lifecycle(self, db_session):
        """Simulate full lifecycle: device online -> heartbeat stops -> exceeds threshold -> offline.

        Steps:
        1. Create device, send heartbeats - device stays online
        2. Stop sending heartbeats (freeze last_heartbeat in time)
        3. Time passes beyond threshold
        4. check_heartbeat_timeout detects the gap and marks offline
        """
        # Step 1: Device is created and actively heartbeating
        device = Device(
            device_id="LIFECYCLE-1",
            model="RK3588",
            kernel_version="5.10.110",
            is_online=True,
            last_heartbeat=datetime.utcnow(),
        )
        db_session.add(device)
        db_session.commit()

        # Verify: within threshold, device remains online
        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 0
        db_session.refresh(device)
        assert device.is_online is True

        # Step 2: Simulate heartbeat arriving (like the API /heartbeat call)
        device.last_heartbeat = datetime.utcnow()
        db_session.commit()

        # Still online after check
        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 0
        db_session.refresh(device)
        assert device.is_online is True

        # Step 3: Heartbeat STOPS - simulate time passing beyond threshold
        # (set last_heartbeat to 50 seconds ago, exceeding the 45s threshold)
        device.last_heartbeat = datetime.utcnow() - timedelta(seconds=50)
        db_session.commit()

        # Step 4: Timeout check now detects the device is stale
        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 1
        db_session.refresh(device)
        assert device.is_online is False

        # Verify: calling check again does NOT re-count (already offline)
        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 0
        db_session.refresh(device)
        assert device.is_online is False

    def test_heartbeat_stop_then_resume(self, db_session):
        """Device goes offline after heartbeat stops, then comes back online when heartbeat resumes."""
        device = Device(
            device_id="RESUME-1",
            model="IMX6ULL",
            kernel_version="5.4.0",
            is_online=True,
            last_heartbeat=datetime.utcnow() - timedelta(seconds=60),
        )
        db_session.add(device)
        db_session.commit()

        # Heartbeat stopped - exceeds 45s threshold, goes offline
        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 1
        db_session.refresh(device)
        assert device.is_online is False

        # Device sends a new heartbeat (simulating update_heartbeat API call)
        updated = update_heartbeat(db_session, "RESUME-1")
        assert updated.is_online is True
        assert (datetime.utcnow() - updated.last_heartbeat).total_seconds() < 2

        # Next timeout check confirms device is still online
        count = check_heartbeat_timeout(db_session, timeout_seconds=45)
        assert count == 0
        db_session.refresh(device)
        assert device.is_online is True

    def test_heartbeat_stop_via_api_lifecycle(self, client, db_session):
        """Full API-level test: create -> heartbeat -> stop -> check offline via list filter."""
        # Create device via API
        r = client.post("/api/devices/", json={
            "device_id": "API-LIFE-1",
            "model": "STM32MP1",
            "kernel_version": "5.15.0"
        })
        assert r.status_code == 201
        assert r.json()["is_online"] is True

        # Send heartbeat via API - stays online
        r = client.post("/api/devices/API-LIFE-1/heartbeat")
        assert r.status_code == 200
        assert r.json()["is_online"] is True

        # Simulate heartbeat stopping: manually set last_heartbeat to past
        device = db_session.query(Device).filter(Device.device_id == "API-LIFE-1").first()
        device.last_heartbeat = datetime.utcnow() - timedelta(seconds=50)
        db_session.commit()

        # Run timeout check
        check_heartbeat_timeout(db_session, timeout_seconds=45)

        # API list with filter should now show it as offline
        r = client.get("/api/devices/?is_online=false")
        offline_ids = [d["device_id"] for d in r.json()["devices"]]
        assert "API-LIFE-1" in offline_ids

        # Online filter should NOT contain it
        r = client.get("/api/devices/?is_online=true")
        online_ids = [d["device_id"] for d in r.json()["devices"]]
        assert "API-LIFE-1" not in online_ids


class TestConcurrency:
    def test_concurrent_create_same_device_id(self, db_session):
        """Test: concurrent creation of the same device_id - only one succeeds.
        Simulates race condition by attempting sequential creates with same ID.
        In production MySQL, the UNIQUE constraint handles true concurrent inserts.
        """
        device_data = DeviceCreate(device_id="CONCURRENT-1", model="Race", kernel_version="5.0")

        # First create succeeds
        device = create_device(db_session, device_data)
        assert device.device_id == "CONCURRENT-1"

        # Subsequent creates with the same ID raise DuplicateDeviceError
        for _ in range(4):
            with pytest.raises(DuplicateDeviceError):
                session = TestingSessionLocal()
                try:
                    create_device(session, device_data)
                finally:
                    session.close()

    def test_concurrent_create_different_ids(self, client):
        """Test: creation with different IDs all succeed independently."""
        responses = []
        for i in range(10):
            resp = client.post("/api/devices/", json={
                "device_id": f"DIFF-{i}",
                "model": "Concurrent",
                "kernel_version": "5.0"
            })
            responses.append(resp)

        assert all(r.status_code == 201 for r in responses)
        response = client.get("/api/devices/")
        assert response.json()["total"] == 10

    def test_duplicate_device_id_via_api(self, client):
        """Test: API returns 409 with error_code on duplicate device_id."""
        payload = {"device_id": "RACE-1", "model": "X", "kernel_version": "5.0"}
        r1 = client.post("/api/devices/", json=payload)
        assert r1.status_code == 201

        r2 = client.post("/api/devices/", json=payload)
        assert r2.status_code == 409
        detail = r2.json()["detail"]
        assert detail["error_code"] == "DEVICE_ID_DUPLICATE"
        assert detail["device_id"] == "RACE-1"
        assert "already exists" in detail["message"]
