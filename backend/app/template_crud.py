import random
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Device
from app.template_models import ConfigTemplate, TemplateBinding, DeploymentTask
from app.template_engine import (
    render_template, compute_config_hash, get_device_variables,
    TemplateRenderError, compute_field_diff_count, simulate_device_config,
)
from app.template_schemas import TemplateCreate, TemplateUpdate, BindingCreate


class TemplateNotFoundError(Exception):
    def __init__(self, template_id: int):
        self.template_id = template_id
        super().__init__(f"Template {template_id} not found")


class BindingNotFoundError(Exception):
    def __init__(self, binding_id: int):
        self.binding_id = binding_id
        super().__init__(f"Binding {binding_id} not found")


class DuplicateBindingError(Exception):
    def __init__(self, template_id: int, device_id: str):
        self.template_id = template_id
        self.device_id = device_id
        super().__init__(f"Template {template_id} is already bound to device {device_id}")


SIMULATED_FAILURE_MESSAGES = [
    "Connection timeout: device unreachable",
    "Flash write error: sector verification failed",
    "Checksum verification failed after write",
    "Device rejected configuration: incompatible format",
    "Transfer interrupted: partial write detected",
]


def create_template(db: Session, data: TemplateCreate) -> ConfigTemplate:
    template = ConfigTemplate(
        name=data.name,
        description=data.description,
        content=data.content,
    )
    db.add(template)
    try:
        db.commit()
        db.refresh(template)
    except IntegrityError:
        db.rollback()
        raise
    return template


def get_template(db: Session, template_id: int) -> Optional[ConfigTemplate]:
    stmt = select(ConfigTemplate).where(ConfigTemplate.id == template_id)
    return db.execute(stmt).scalar_one_or_none()


def get_templates(db: Session, skip: int = 0, limit: int = 50) -> tuple[list[ConfigTemplate], int]:
    count_stmt = select(func.count()).select_from(ConfigTemplate)
    total = db.execute(count_stmt).scalar()

    stmt = select(ConfigTemplate).order_by(ConfigTemplate.created_at.desc()).offset(skip).limit(limit)
    templates = list(db.execute(stmt).scalars().all())
    return templates, total


def update_template(db: Session, template_id: int, data: TemplateUpdate) -> Optional[ConfigTemplate]:
    template = get_template(db, template_id)
    if not template:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)

    if "content" in update_data:
        _recalculate_binding_hashes(db, template)

    db.commit()
    db.refresh(template)
    return template


def _recalculate_binding_hashes(db: Session, template: ConfigTemplate):
    stmt = select(TemplateBinding).where(TemplateBinding.template_id == template.id)
    bindings = list(db.execute(stmt).scalars().all())
    for binding in bindings:
        device_stmt = select(Device).where(Device.device_id == binding.device_id)
        device = db.execute(device_stmt).scalar_one_or_none()
        if not device:
            continue
        variables = get_device_variables(device)
        try:
            rendered = render_template(template.content, variables)
            new_hash = compute_config_hash(rendered)
            binding.expected_config_hash = new_hash
            binding.rendered_config = rendered
            # Recompute field diff against current config
            binding.drift_field_count = compute_field_diff_count(rendered, binding.current_config)
            # Immediately sync to Redis
            from app.dashboard_crud import cache_expected_hash
            cache_expected_hash(binding.device_id, new_hash)
        except TemplateRenderError:
            binding.expected_config_hash = None
            binding.rendered_config = None
            binding.drift_field_count = 0


def delete_template(db: Session, template_id: int) -> bool:
    template = get_template(db, template_id)
    if not template:
        return False
    db.delete(template)
    db.commit()
    return True


def create_binding(db: Session, data: BindingCreate) -> TemplateBinding:
    template = get_template(db, data.template_id)
    if not template:
        raise TemplateNotFoundError(data.template_id)

    device_stmt = select(Device).where(Device.device_id == data.device_id)
    device = db.execute(device_stmt).scalar_one_or_none()
    if not device:
        from app.crud import DuplicateDeviceError
        raise ValueError(f"Device '{data.device_id}' not found")

    variables = get_device_variables(device)
    rendered = None
    expected_hash = None
    try:
        rendered = render_template(template.content, variables)
        expected_hash = compute_config_hash(rendered)
    except TemplateRenderError:
        pass

    # Simulate device current config with random field mutations
    drift_fields = random.randint(0, 5)
    if rendered and drift_fields > 0:
        current_cfg = simulate_device_config(rendered, drift_fields)
    else:
        current_cfg = rendered
        drift_fields = 0

    current_hash = compute_config_hash(current_cfg) if current_cfg else None
    actual_diff = compute_field_diff_count(rendered, current_cfg) if rendered and current_cfg else 0

    binding = TemplateBinding(
        template_id=data.template_id,
        device_id=data.device_id,
        expected_config_hash=expected_hash,
        current_config_hash=current_hash,
        rendered_config=rendered,
        current_config=current_cfg,
        drift_field_count=actual_diff,
    )
    db.add(binding)
    try:
        db.commit()
        db.refresh(binding)
    except IntegrityError:
        db.rollback()
        raise DuplicateBindingError(data.template_id, data.device_id)

    # Immediately cache expected hash in Redis
    if expected_hash:
        from app.dashboard_crud import cache_expected_hash
        cache_expected_hash(data.device_id, expected_hash)

    return binding


def get_bindings(db: Session, device_id: Optional[str] = None, template_id: Optional[int] = None,
                 skip: int = 0, limit: int = 50) -> tuple[list[TemplateBinding], int]:
    stmt = select(TemplateBinding)
    count_stmt = select(func.count()).select_from(TemplateBinding)

    if device_id:
        stmt = stmt.where(TemplateBinding.device_id == device_id)
        count_stmt = count_stmt.where(TemplateBinding.device_id == device_id)
    if template_id:
        stmt = stmt.where(TemplateBinding.template_id == template_id)
        count_stmt = count_stmt.where(TemplateBinding.template_id == template_id)

    total = db.execute(count_stmt).scalar()
    stmt = stmt.order_by(TemplateBinding.bound_at.desc()).offset(skip).limit(limit)
    bindings = list(db.execute(stmt).scalars().all())
    return bindings, total


def get_binding(db: Session, binding_id: int) -> Optional[TemplateBinding]:
    stmt = select(TemplateBinding).where(TemplateBinding.id == binding_id)
    return db.execute(stmt).scalar_one_or_none()


def delete_binding(db: Session, binding_id: int) -> bool:
    binding = get_binding(db, binding_id)
    if not binding:
        return False
    device_id = binding.device_id
    db.delete(binding)
    db.commit()

    # Immediately remove expected hash from Redis
    from app.dashboard_crud import remove_expected_hash
    remove_expected_hash(device_id)

    return True


def create_deployment(db: Session, binding_id: int) -> DeploymentTask:
    binding = get_binding(db, binding_id)
    if not binding:
        raise BindingNotFoundError(binding_id)

    template = get_template(db, binding.template_id)
    device_stmt = select(Device).where(Device.device_id == binding.device_id)
    device = db.execute(device_stmt).scalar_one_or_none()

    task = DeploymentTask(binding_id=binding_id, status="pending")
    db.add(task)
    db.flush()

    try:
        variables = get_device_variables(device)
        rendered = render_template(template.content, variables)
        task.rendered_content = rendered
    except TemplateRenderError as e:
        task.status = "failed"
        task.error_message = f"Render error: {e.message}"
        task.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
        return task

    if random.random() < 0.7:
        task.status = "success"
        task.completed_at = datetime.utcnow()
        binding.current_config_hash = binding.expected_config_hash
    else:
        task.status = "failed"
        task.error_message = random.choice(SIMULATED_FAILURE_MESSAGES)
        task.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(task)
    return task


def get_deployments(db: Session, binding_id: Optional[int] = None,
                    skip: int = 0, limit: int = 50) -> tuple[list[DeploymentTask], int]:
    stmt = select(DeploymentTask)
    count_stmt = select(func.count()).select_from(DeploymentTask)

    if binding_id:
        stmt = stmt.where(DeploymentTask.binding_id == binding_id)
        count_stmt = count_stmt.where(DeploymentTask.binding_id == binding_id)

    total = db.execute(count_stmt).scalar()
    stmt = stmt.order_by(DeploymentTask.created_at.desc()).offset(skip).limit(limit)
    deployments = list(db.execute(stmt).scalars().all())
    return deployments, total
