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
    def test_full_rollout_all_fail(self, mock_random, client):
        task_id = self._setup_task(client, 10)

        client.post(f"/api/ota/tasks/{task_id}/confirm")
        client.post(f"/api/ota/tasks/{task_id}/confirm")
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
        for dt in devices_resp.json()["device_tasks"]:
            assert dt["status"] == "failed"
            assert dt["error_message"] is not None

    @patch("app.ota_crud.random.random")
    def test_partial_failure_in_batch(self, mock_random, client):
        """Batch2 has 4 devices: first 2 succeed, last 2 fail"""
        task_id = self._setup_task(client, 10)

        mock_random.return_value = 0.5
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        call_results = [0.5, 0.5, 0.99, 0.99]
        mock_random.side_effect = call_results
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        detail_resp = client.get(f"/api/ota/tasks/{task_id}")
        data = detail_resp.json()
        assert data["batch2"]["success"] == 2
        assert data["batch2"]["failed"] == 2

    @patch("app.ota_crud.random.random", return_value=0.5)
    def test_single_device_completes_after_batch1(self, mock_random, client):
        """Single device: only batch1, task completes immediately"""
        task_id = self._setup_task(client, 1)

        resp = client.post(f"/api/ota/tasks/{task_id}/confirm")
        assert resp.json()["status"] == "completed"


class TestRollbackLogic:
    @patch("app.ota_crud.random.random", return_value=0.99)
    def test_failed_device_version_reverted(self, mock_random, client, db_session):
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

        device_resp = client.get("/api/devices/dev-001")
        assert device_resp.json()["kernel_version"] == "v1.0.0"

    @patch("app.ota_crud.random.random", return_value=0.1)
    def test_successful_device_version_updated(self, mock_random, client):
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

        device_resp = client.get("/api/devices/dev-001")
        assert device_resp.json()["kernel_version"] == "v2.0.0"

    @patch("app.ota_crud.random.random", return_value=0.99)
    def test_rollback_records_error_message(self, mock_random, client):
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

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
        dt = devices_resp.json()["device_tasks"][0]
        assert dt["status"] == "failed"
        assert dt["error_message"] is not None
        assert len(dt["error_message"]) > 0


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


class TestTaskConfirmValidation:
    @patch("app.ota_crud.random.random", return_value=0.5)
    def test_double_confirm_returns_400(self, mock_random, client):
        """Cannot confirm a batch that's already running or completed"""
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
    @patch("app.ota_crud.random.random")
    def test_mixed_success_rates_across_batches(self, mock_random, client):
        """Simulate: batch1 all succeed, batch2 mixed, batch3 all fail"""
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

        mock_random.return_value = 0.5
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]
        batch1_size = resp.json()["batch1_size"]
        batch2_size = resp.json()["batch2_size"]
        batch3_size = resp.json()["batch3_size"]

        mock_random.side_effect = [0.1] * batch1_size
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        mixed = [0.1, 0.99] * (batch2_size // 2 + 1)
        mock_random.side_effect = mixed[:batch2_size]
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        mock_random.side_effect = [0.99] * batch3_size
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        detail_resp = client.get(f"/api/ota/tasks/{task_id}")
        data = detail_resp.json()

        assert data["batch1"]["success"] == batch1_size
        assert data["batch1"]["failed"] == 0

        assert data["batch2"]["success"] >= 1
        assert data["batch2"]["failed"] >= 1

        assert data["batch3"]["failed"] == batch3_size
        assert data["batch3"]["success"] == 0

    @patch("app.ota_crud.random.random")
    def test_version_consistency_after_mixed_results(self, mock_random, client):
        """After mixed upgrades, verify device versions are correct"""
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

        mock_random.return_value = 0.5
        resp = client.post("/api/ota/tasks/", json={"firmware_id": fw_id})
        task_id = resp.json()["id"]

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
        all_device_tasks = devices_resp.json()["device_tasks"]
        total = len(all_device_tasks)

        outcomes = [0.1 if i % 2 == 0 else 0.99 for i in range(total)]
        mock_random.side_effect = outcomes[:1]
        client.post(f"/api/ota/tasks/{task_id}/confirm")

        batch2_size = resp.json()["batch2_size"]
        batch3_size = resp.json()["batch3_size"]

        if batch2_size > 0:
            mock_random.side_effect = outcomes[1:1 + batch2_size]
            client.post(f"/api/ota/tasks/{task_id}/confirm")

        if batch3_size > 0:
            mock_random.side_effect = outcomes[1 + batch2_size:]
            client.post(f"/api/ota/tasks/{task_id}/confirm")

        devices_resp = client.get(f"/api/ota/tasks/{task_id}/devices")
        for dt in devices_resp.json()["device_tasks"]:
            device_resp = client.get(f"/api/devices/{dt['device_id']}")
            device_version = device_resp.json()["kernel_version"]
            if dt["status"] == "success":
                assert device_version == "v2.0.0"
            elif dt["status"] == "failed":
                assert device_version == "v1.0.0"


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
