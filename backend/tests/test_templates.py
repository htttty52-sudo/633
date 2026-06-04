import pytest
from datetime import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Device
from app.template_models import ConfigTemplate, TemplateBinding, DeploymentTask
from app.template_engine import render_template, compute_config_hash, validate_template_syntax, TemplateRenderError

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


@pytest.fixture
def sample_device(client):
    client.post("/api/devices/", json={
        "device_id": "dev-001",
        "model": "RK3588",
        "kernel_version": "5.10.110",
    })
    return "dev-001"


@pytest.fixture
def sample_template(client):
    resp = client.post("/api/templates/", json={
        "name": "network-config",
        "description": "Network configuration template",
        "content": "hostname: \"{{ device_id }}\"\nmodel: \"{{ model }}\"\nkernel: \"{{ kernel_version }}\"",
    })
    return resp.json()


VALID_TEMPLATE_CONTENT = "hostname: \"{{ device_id }}\"\nmodel: \"{{ model }}\"\nkernel: \"{{ kernel_version }}\""


class TestTemplateCRUD:
    def test_create_template(self, client):
        resp = client.post("/api/templates/", json={
            "name": "test-template",
            "description": "A test template",
            "content": VALID_TEMPLATE_CONTENT,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-template"
        assert data["description"] == "A test template"
        assert data["content"] == VALID_TEMPLATE_CONTENT
        assert "id" in data

    def test_create_template_duplicate_name(self, client):
        client.post("/api/templates/", json={
            "name": "dup-template",
            "description": "",
            "content": "key: value",
        })
        resp = client.post("/api/templates/", json={
            "name": "dup-template",
            "description": "",
            "content": "key: value2",
        })
        assert resp.status_code == 409

    def test_create_template_empty_content(self, client):
        resp = client.post("/api/templates/", json={
            "name": "empty",
            "description": "",
            "content": "   ",
        })
        assert resp.status_code == 422

    def test_get_template(self, client, sample_template):
        template_id = sample_template["id"]
        resp = client.get(f"/api/templates/{template_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "network-config"

    def test_get_template_not_found(self, client):
        resp = client.get("/api/templates/9999")
        assert resp.status_code == 404

    def test_list_templates(self, client):
        client.post("/api/templates/", json={"name": "t1", "content": "a: 1"})
        client.post("/api/templates/", json={"name": "t2", "content": "b: 2"})
        resp = client.get("/api/templates/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["templates"]) == 2

    def test_update_template(self, client, sample_template):
        template_id = sample_template["id"]
        resp = client.put(f"/api/templates/{template_id}", json={
            "description": "Updated description",
        })
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_delete_template(self, client, sample_template):
        template_id = sample_template["id"]
        resp = client.delete(f"/api/templates/{template_id}")
        assert resp.status_code == 204
        resp = client.get(f"/api/templates/{template_id}")
        assert resp.status_code == 404


class TestTemplateBinding:
    def test_create_binding(self, client, sample_device, sample_template):
        resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["template_id"] == sample_template["id"]
        assert data["device_id"] == sample_device
        assert data["expected_config_hash"] is not None
        assert data["current_config_hash"] is not None
        assert data["expected_config_hash"] != data["current_config_hash"]

    def test_create_binding_duplicate(self, client, sample_device, sample_template):
        client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        assert resp.status_code == 409

    def test_create_binding_template_not_found(self, client, sample_device):
        resp = client.post("/api/bindings/", json={
            "template_id": 9999,
            "device_id": sample_device,
        })
        assert resp.status_code == 404

    def test_create_binding_device_not_found(self, client, sample_template):
        resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": "nonexistent-device",
        })
        assert resp.status_code == 404

    def test_list_bindings_by_device(self, client, sample_device, sample_template):
        client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        resp = client.get(f"/api/bindings/?device_id={sample_device}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_delete_binding(self, client, sample_device, sample_template):
        resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        binding_id = resp.json()["id"]
        resp = client.delete(f"/api/bindings/{binding_id}")
        assert resp.status_code == 204


class TestTemplateRendering:
    def test_render_valid_template(self, client, sample_device, sample_template):
        resp = client.post("/api/templates/render-preview", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "dev-001" in data["rendered_content"]
        assert "RK3588" in data["rendered_content"]
        assert data["config_hash"] is not None
        assert data["variables_used"]["device_id"] == "dev-001"

    def test_render_missing_variable(self, client, sample_device):
        resp = client.post("/api/templates/", json={
            "name": "bad-vars",
            "content": "host: \"{{ nonexistent_var }}\"",
        })
        template_id = resp.json()["id"]
        resp = client.post("/api/templates/render-preview", json={
            "template_id": template_id,
            "device_id": sample_device,
        })
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error_type"] == "missing_variable"
        assert "available_variables" in detail["details"]

    def test_render_syntax_error(self, client, sample_device):
        resp = client.post("/api/templates/", json={
            "name": "bad-syntax",
            "content": "host: \"{{ device_id\"",
        })
        template_id = resp.json()["id"]
        resp = client.post("/api/templates/render-preview", json={
            "template_id": template_id,
            "device_id": sample_device,
        })
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error_type"] == "syntax_error"

    def test_validate_valid_syntax(self, client):
        resp = client.post("/api/templates/validate", json={
            "content": "host: \"{{ device_id }}\"",
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_validate_invalid_syntax(self, client):
        resp = client.post("/api/templates/validate", json={
            "content": "host: \"{% if %}\"",
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert resp.json()["error"] is not None

    def test_hash_determinism(self):
        content = "hostname: dev-001\nmodel: RK3588"
        hash1 = compute_config_hash(content)
        hash2 = compute_config_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_render_engine_directly(self):
        content = "name: \"{{ device_id }}\""
        result = render_template(content, {"device_id": "test-dev"})
        assert result == 'name: "test-dev"'


class TestDeployment:
    @patch("app.template_crud.random.random", return_value=0.5)
    def test_deployment_success(self, mock_random, client, sample_device, sample_template):
        bind_resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        binding_id = bind_resp.json()["id"]

        resp = client.post("/api/deployments/", json={"binding_id": binding_id})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        assert data["rendered_content"] is not None
        assert data["error_message"] is None

    @patch("app.template_crud.random.random", return_value=0.9)
    def test_deployment_failure(self, mock_random, client, sample_device, sample_template):
        bind_resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        binding_id = bind_resp.json()["id"]

        resp = client.post("/api/deployments/", json={"binding_id": binding_id})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error_message"] is not None

    @patch("app.template_crud.random.random", return_value=0.5)
    def test_deployment_updates_hash(self, mock_random, client, sample_device, sample_template):
        bind_resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        binding_id = bind_resp.json()["id"]

        client.post("/api/deployments/", json={"binding_id": binding_id})

        compare_resp = client.get(f"/api/bindings/{binding_id}/compare")
        assert compare_resp.status_code == 200
        assert compare_resp.json()["is_match"] is True

    @patch("app.template_crud.random.random", return_value=0.9)
    def test_deployment_failure_no_hash_update(self, mock_random, client, sample_device, sample_template):
        bind_resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        binding_id = bind_resp.json()["id"]

        client.post("/api/deployments/", json={"binding_id": binding_id})

        compare_resp = client.get(f"/api/bindings/{binding_id}/compare")
        assert compare_resp.status_code == 200
        assert compare_resp.json()["is_match"] is False

    def test_deployment_binding_not_found(self, client):
        resp = client.post("/api/deployments/", json={"binding_id": 9999})
        assert resp.status_code == 404

    def test_list_deployments(self, client, sample_device, sample_template):
        bind_resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        binding_id = bind_resp.json()["id"]
        client.post("/api/deployments/", json={"binding_id": binding_id})
        client.post("/api/deployments/", json={"binding_id": binding_id})

        resp = client.get(f"/api/deployments/?binding_id={binding_id}")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2


class TestHashComparison:
    def test_compare_mismatch_on_creation(self, client, sample_device, sample_template):
        bind_resp = client.post("/api/bindings/", json={
            "template_id": sample_template["id"],
            "device_id": sample_device,
        })
        binding_id = bind_resp.json()["id"]

        resp = client.get(f"/api/bindings/{binding_id}/compare")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_match"] is False
        assert data["expected_config_hash"] is not None
        assert data["current_config_hash"] is not None

    def test_compare_not_found(self, client):
        resp = client.get("/api/bindings/9999/compare")
        assert resp.status_code == 404
