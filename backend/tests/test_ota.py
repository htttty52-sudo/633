from unittest.mock import patch
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Device
from app.ota_models import Firmware, OtaTask, OtaDeviceTask


class TestFirmwareCRUD:
    def test_create_firmware(self, client):
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.1.0",
            "target_model": "RK3588",
            "filename": "firmware-rk3588-v2.1.0.bin",
            "file_size": 15728640,
            "description": "Bug fixes",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == "v2.1.0"
        assert data["target_model"] == "RK3588"
        assert data["filename"] == "firmware-rk3588-v2.1.0.bin"
        assert data["file_size"] == 15728640
        assert len(data["checksum"]) == 64

    def test_list_firmwares(self, client):
        client.post("/api/ota/firmwares/", json={
            "version": "v1.0.0", "target_model": "RK3588",
            "filename": "fw1.bin", "file_size": 1000,
        })
        client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "IMX6",
            "filename": "fw2.bin", "file_size": 2000,
        })
        resp = client.get("/api/ota/firmwares/")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_firmwares_filter_by_model(self, client):
        client.post("/api/ota/firmwares/", json={
            "version": "v1.0.0", "target_model": "RK3588",
            "filename": "fw1.bin", "file_size": 1000,
        })
        client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "IMX6",
            "filename": "fw2.bin", "file_size": 2000,
        })
        resp = client.get("/api/ota/firmwares/?target_model=RK3588")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["firmwares"][0]["target_model"] == "RK3588"

    def test_delete_firmware(self, client):
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v1.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 1000,
        })
        firmware_id = resp.json()["id"]
        del_resp = client.delete(f"/api/ota/firmwares/{firmware_id}")
        assert del_resp.status_code == 204

    def test_delete_firmware_not_found(self, client):
        resp = client.delete("/api/ota/firmwares/999")
        assert resp.status_code == 404


class TestOtaTaskCreation:
    def _create_devices(self, client, model, count):
        for i in range(count):
            client.post("/api/devices/", json={
                "device_id": f"dev-{model}-{i:03d}",
                "model": model,
                "kernel_version": "v1.0.0",
            })

    def _create_firmware(self, client, model):
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0",
            "target_model": model,
            "filename": f"fw-{model}.bin",
            "file_size": 10000,
        })
        return resp.json()["id"]

    def test_create_ota_task_assigns_batches(self, client):
        """10 devices: batch1=1, batch2=4, batch3=5"""
        self._create_devices(client, "RK3588", 10)
        fw_id = self._create_firmware(client, "RK3588")

        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        assert resp.status_code == 201
        data = resp.json()
        assert data["total_devices"] == 10
        assert data["batch1_size"] == 1
        assert data["batch2_size"] == 4
        assert data["batch3_size"] == 5
        assert data["status"] == "batch1_pending"
        assert data["current_batch"] == 1

    def test_create_ota_task_single_device(self, client):
        """1 device: batch1=1, batch2=0, batch3=0"""
        self._create_devices(client, "RK3588", 1)
        fw_id = self._create_firmware(client, "RK3588")

        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        assert resp.status_code == 201
        data = resp.json()
        assert data["batch1_size"] == 1
        assert data["batch2_size"] == 0
        assert data["batch3_size"] == 0

    def test_create_ota_task_no_matching_devices(self, client):
        self._create_devices(client, "IMX6", 5)
        fw_id = self._create_firmware(client, "RK3588")

        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        assert resp.status_code == 400
        assert "No devices found" in resp.json()["detail"]

    def test_create_ota_task_firmware_not_found(self, client):
        resp = client.post("/api/ota/tasks/", json={"firmware_id": 999})
        assert resp.status_code == 404

    def test_device_tasks_created_with_correct_versions(self, client):
        self._create_devices(client, "RK3588", 5)
        fw_id = self._create_firmware(client, "RK3588")

        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
        data = devices_resp.json()
        assert data["total"] == 5
        for dt in data["device_tasks"]:
            assert dt["previous_version"] == "v1.0.0"
            assert dt["target_version"] == "v2.0.0"
            assert dt["status"] == "pending"


class TestBatchedRollout:
    def _setup_task(self, client, device_count=10):
        for i in range(device_count):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        return resp.json()["id"]

    @patch("app.ota_crud.random.random", return_value=0.5)
    def test_full_rollout_all_success(self, mock_random, client):
        task_id = self._setup_task(client, 10)

        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "batch2_pending"

        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "batch3_pending"

        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "success"

    @patch("app.ota_crud.random.random", return_value=0.99)
    def test_batch_failure_sets_batch_failed_status(self, mock_random, client):
        """When any device fails, entire batch is rolled back and task enters batchN_failed"""
        task_id = self._setup_task(client, 10)

        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "batch1_failed"

    @patch("app.ota_crud.random.random", return_value=0.5)
    def test_single_device_completes_after_batch1(self, mock_random, client):
        """Single device: only batch1, task completes immediately"""
        task_id = self._setup_task(client, 1)

        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.json()["status"] == "completed"

    @patch("app.ota_crud.random.random", return_value=0.5)
    def test_batch_requires_manual_confirm_between_each(self, mock_random, client):
        """Each batch transition waits for manual confirmation"""
        task_id = self._setup_task(client, 10)

        resp = client.get(f"/api/ota/tasks/{task_id}")
        assert resp.json()["status"] == "batch1_pending"

        client.post(f"/api/ota/tasks/{task_id}/confirm")
        resp = client.get(f"/api/ota/tasks/{task_id}")
        assert resp.json()["status"] == "batch2_pending"

        client.post(f"/api/ota/tasks/{task_id}/confirm")
        resp = client.get(f"/api/ota/tasks/{task_id}")
        assert resp.json()["status"] == "batch3_pending"

        client.post(f"/api/ota/tasks/{task_id}/confirm")
        resp = client.get(f"/api/ota/tasks/{task_id}")
        assert resp.json()["status"] == "completed"


class TestFullBatchRollback:
    """Key behavior: if ANY device in a batch fails, ALL devices in that batch are rolled back."""

    @patch("app.ota_crud.random.random")
    def test_single_failure_rolls_back_entire_batch(self, mock_random, client):
        """4 devices in batch2: 3 succeed, 1 fails → all 4 rolled back"""
        for i in range(10):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]
        batch2_size = resp.json()["batch2_size"]

        mock_random.return_value = 0.5
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        results = [0.5] * (batch2_size - 1) + [0.99]
        mock_random.side_effect = results
        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.json()["status"] == "batch2_failed"

        detail = client.get(f"/api/ota/tasks/{task_id}").json()
        assert detail["batch2"]["failed"] == batch2_size
        assert detail["batch2"]["success"] == 0

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices?batch_number=2")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "failed"
            device_resp = client.get(f"/api/devices/{dt['device_id']}")
            assert device_resp.json()["kernel_version"] == "v1.0.0"

    @patch("app.ota_crud.random.random")
    def test_rollback_records_reason_for_all_devices(self, mock_random, client):
        """All rolled-back devices get an error_message explaining why"""
        for i in range(10):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]
        batch2_size = resp.json()["batch2_size"]

        mock_random.return_value = 0.5
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        results = [0.5] * (batch2_size - 1) + [0.99]
        mock_random.side_effect = results
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices?batch_number=2")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["error_message"] is not None
            assert len(dt["error_message"]) > 0

    @patch("app.ota_crud.random.random", return_value=0.99)
    def test_all_fail_in_batch_all_rolled_back(self, mock_random, client):
        """All devices fail → all rolled back, versions unchanged"""
        for i in range(5):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        client.post(f"/api/ota/tasks/{task_id}/confirm")

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices?batch_number=1")
        for dt in devices_resp.json()["device_tasks"]:
            device_resp = client.get(f"/api/devices/{dt['device_id']}")
            assert device_resp.json()["kernel_version"] == "v1.0.0"


class TestRetryBatch:
    """Test failed→pending state transition (retry)."""

    @patch("app.ota_crud.random.random")
    def test_retry_resets_failed_devices_to_pending(self, mock_random, client):
        """After failure, retry moves all devices back to pending"""
        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        mock_random.return_value = 0.99
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        task_resp = client.get(f"/api/ota/tasks/{task_id}")
        assert task_resp.json()["status"] == "batch1_failed"

        resp = client.post(f"/api/ota/tasks/{task_id}/retry")
        assert resp.status_code == 200
        assert resp.json()["status"] == "batch1_pending"

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "pending"
            assert dt["error_message"] is None

    @patch("app.ota_crud.random.random")
    def test_retry_then_confirm_succeeds(self, mock_random, client):
        """Full flow: fail → retry → confirm (succeed) → next batch"""
        for i in range(10):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        mock_random.return_value = 0.99
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch1_failed"

        client.post(f"/api/ota/tasks/{task_id}/retry")

        mock_random.return_value = 0.5
        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.json()["status"] == "batch2_pending"

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices?batch_number=1")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "success"

    def test_retry_on_non_failed_state_returns_400(self, client):
        """Cannot retry when task is not in batchN_failed state"""
        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        resp = client.post(f"/api/ota/tasks/{task_id}/retry")
        assert resp.status_code == 400

    @patch("app.ota_crud.random.random")
    def test_multiple_retries_allowed(self, mock_random, client):
        """Can retry multiple times until success"""
        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        mock_random.return_value = 0.99
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        client.post(f"/api/ota/tasks/{task_id}/retry")

        mock_random.return_value = 0.99
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch1_failed"

        client.post(f"/api/ota/tasks/{task_id}/retry")
        mock_random.return_value = 0.5
        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.json()["status"] == "completed"


class TestHeartbeatDuringUpgrade:
    def test_upgrading_device_heartbeat_maintained(self, client, db_session):
        """Devices in upgrading state always get heartbeat updated"""
        from tests.conftest import TestingSessionLocal

        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })

        device = db_session.execute(
            select(Device).where(Device.device_id == "dev-001")
        ).scalar_one()
        device.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
        db_session.commit()

        from app.ota_models import OtaTask, Firmware
        fw = Firmware(
            version="v2.0.0", target_model="RK3588",
            filename="fw.bin", file_size=1000, checksum="abc123",
        )
        db_session.add(fw)
        db_session.flush()

        task = OtaTask(
            id=1, firmware_id=fw.id, target_model="RK3588",
            status="batch1_running", total_devices=1,
            batch1_size=1, batch2_size=0, batch3_size=0, current_batch=1,
        )
        db_session.add(task)
        db_session.flush()

        dt = OtaDeviceTask(
            ota_task_id=1,
            device_id="dev-001",
            batch_number=1,
            status="upgrading",
            previous_version="v1.0.0",
            target_version="v2.0.0",
            started_at=datetime.utcnow(),
        )
        db_session.add(dt)
        db_session.commit()

        with patch("app.scheduler.SessionLocal", TestingSessionLocal):
            from app.scheduler import simulate_heartbeat
            simulate_heartbeat()

        db_session.expire_all()
        device = db_session.execute(
            select(Device).where(Device.device_id == "dev-001")
        ).scalar_one()
        elapsed = (datetime.utcnow() - device.last_heartbeat).total_seconds()
        assert elapsed < 5

    @patch("app.scheduler.random.random", return_value=0.99)
    def test_non_upgrading_device_can_miss_heartbeat(self, mock_random, client, db_session):
        """Non-upgrading device with random > 0.7 does not get heartbeat"""
        from tests.conftest import TestingSessionLocal

        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })

        device = db_session.execute(
            select(Device).where(Device.device_id == "dev-001")
        ).scalar_one()
        old_heartbeat = datetime.utcnow() - timedelta(seconds=10)
        device.last_heartbeat = old_heartbeat
        db_session.commit()

        with patch("app.scheduler.SessionLocal", TestingSessionLocal):
            from app.scheduler import simulate_heartbeat
            simulate_heartbeat()

        db_session.expire_all()
        device = db_session.execute(
            select(Device).where(Device.device_id == "dev-001")
        ).scalar_one()
        assert device.last_heartbeat == old_heartbeat

    def test_heartbeat_independent_of_upgrade_execution(self, client, db_session):
        """Heartbeat runs in its own executor, decoupled from OTA logic"""
        from app.scheduler import scheduler
        executors = scheduler._executors
        assert "heartbeat" in executors


class TestAbortTask:
    def test_abort_stops_further_batches(self, client):
        for i in range(10):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        resp = client.post(f"/api/ota/tasks/{task_id}/abort")
        assert resp.status_code == 200
        assert resp.json()["status"] == "aborted"

        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.status_code == 400

    def test_abort_completed_task_returns_400(self, client):
        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        with patch("app.ota_crud.random.random", return_value=0.5):
            client.post(f"/api/ota/tasks/{task_id}/confirm")

        resp = client.post(f"/api/ota/tasks/{task_id}/abort")
        assert resp.status_code == 400

    @patch("app.ota_crud.random.random", return_value=0.99)
    def test_abort_from_failed_state(self, mock_random, client):
        """Can abort task that is in batchN_failed state"""
        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        client.post(f"/api/ota/tasks/{task_id}/confirm")
        resp = client.post(f"/api/ota/tasks/{task_id}/abort")
        assert resp.status_code == 200
        assert resp.json()["status"] == "aborted"


class TestTaskConfirmValidation:
    @patch("app.ota_crud.random.random", return_value=0.5)
    def test_double_confirm_returns_400(self, mock_random, client):
        """Cannot confirm a batch that has already been processed"""
        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        client.post(f"/api/ota/tasks/{task_id}/confirm")

        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.status_code == 400

    def test_confirm_nonexistent_task(self, client):
        resp = client.post("/api/ota/tasks/999/confirm")
        assert resp.status_code == 404


class TestNetworkConditionSimulation:
    """Simulate packet loss, latency, and partial failures under different network conditions."""

    @patch("app.ota_crud.random.random")
    def test_packet_loss_causes_batch_failure_and_full_rollback(self, mock_random, client):
        """Simulated 30% packet loss: some devices timeout → entire batch rolled back"""
        for i in range(10):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]
        batch1_size = resp.json()["batch1_size"]

        mock_random.return_value = 0.5
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        batch2_size = resp.json()["batch2_size"]
        packet_loss = [0.5, 0.5, 0.99, 0.5]
        mock_random.side_effect = packet_loss[:batch2_size]
        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.json()["status"] == "batch2_failed"

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices?batch_number=2")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "failed"
            device_resp = client.get(f"/api/devices/{dt['device_id']}")
            assert device_resp.json()["kernel_version"] == "v1.0.0"

    @patch("app.ota_crud.random.random")
    def test_high_latency_batch_retry_then_success(self, mock_random, client):
        """Simulate: high latency causes timeout on first attempt, retry succeeds"""
        for i in range(5):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        mock_random.return_value = 0.99
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch1_failed"

        client.post(f"/api/ota/tasks/{task_id}/retry")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch1_pending"

        mock_random.return_value = 0.5
        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.json()["status"] in ("batch2_pending", "completed")

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices?batch_number=1")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "success"
            device_resp = client.get(f"/api/devices/{dt['device_id']}")
            assert device_resp.json()["kernel_version"] == "v2.0.0"

    @patch("app.ota_crud.random.random")
    def test_intermittent_failure_across_multiple_batches(self, mock_random, client):
        """Batch1 succeeds, batch2 fails (packet loss), retry batch2, batch3 succeeds"""
        for i in range(10):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]
        batch2_size = resp.json()["batch2_size"]
        batch3_size = resp.json()["batch3_size"]

        mock_random.return_value = 0.5
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        mock_random.side_effect = [0.99] * batch2_size
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch2_failed"

        client.post(f"/api/ota/tasks/{task_id}/retry")

        mock_random.side_effect = [0.5] * batch2_size
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch3_pending"

        mock_random.side_effect = [0.5] * batch3_size
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "completed"

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "success"
            device_resp = client.get(f"/api/devices/{dt['device_id']}")
            assert device_resp.json()["kernel_version"] == "v2.0.0"

    @patch("app.ota_crud.random.random")
    def test_complete_network_failure_all_batches_rollback(self, mock_random, client):
        """100% packet loss on all attempts, retry exhaustion pattern"""
        for i in range(5):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        mock_random.return_value = 0.99
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch1_failed"

        client.post(f"/api/ota/tasks/{task_id}/retry")
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch1_failed"

        client.post(f"/api/ota/tasks/{task_id}/retry")
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert client.get(f"/api/ota/tasks/{task_id}").json()["status"] == "batch1_failed"

        resp = client.post(f"/api/ota/tasks/{task_id}/abort")
        assert resp.json()["status"] == "aborted"

        for i in range(5):
            device_resp = client.get(f"/api/devices/dev-{i:03d}")
            assert device_resp.json()["kernel_version"] == "v1.0.0"

    @patch("app.ota_crud.random.random")
    def test_queue_retry_preserves_device_state(self, mock_random, client):
        """After retry, device versions remain at previous_version (no partial state)"""
        for i in range(10):
            client.post("/api/devices/", json={
                "device_id": f"dev-{i:03d}",
                "model": "RK3588",
                "kernel_version": "v1.0.0",
            })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]
        batch2_size = resp.json()["batch2_size"]

        mock_random.return_value = 0.5
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        mock_random.side_effect = [0.5] * (batch2_size - 1) + [0.99]
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        for i in range(10):
            device_resp = client.get(f"/api/devices/dev-{i:03d}")
            version = device_resp.json()["kernel_version"]
            devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
            dt_map = {d["device_id"]: d for d in devices_resp.json()["device_tasks"]}
            dt = dt_map.get(f"dev-{i:03d}")
            if dt and dt["batch_number"] == 1:
                assert version == "v2.0.0"
            else:
                assert version == "v1.0.0"

        client.post(f"/api/ota/tasks/{task_id}/retry")
        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices?batch_number=2")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "pending"
            assert dt["error_message"] is None


class TestOtaTaskDetail:
    def test_get_task_detail_with_batch_stats(self, client):
        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        detail_resp = client.get(f"/api/ota/tasks/{task_id}")
        assert detail_resp.status_code == 200
        data = detail_resp.json()
        assert "batch1" in data
        assert "batch2" in data
        assert "batch3" in data
        assert data["batch1"]["pending"] == 1
        assert data["batch1"]["total"] == 1

    def test_list_ota_tasks(self, client):
        client.post("/api/devices/", json={
            "device_id": "dev-001",
            "model": "RK3588",
            "kernel_version": "v1.0.0",
        })
        resp = client.post("/api/ota/firmwares/", json={
            "version": "v2.0.0", "target_model": "RK3588",
            "filename": "fw.bin", "file_size": 10000,
        })
        fw_id = resp.json()["id"]
        client.post("/api/ota/tasks/", json={"firmware_id": fw_id})

        resp = client.get("/api/ota/tasks/")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
