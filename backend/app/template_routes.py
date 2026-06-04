from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.template_crud import (
    create_template, get_template, get_templates, update_template, delete_template,
    create_binding, get_bindings, get_binding, delete_binding,
    create_deployment, get_deployments,
    TemplateNotFoundError, BindingNotFoundError, DuplicateBindingError,
)
from app.template_engine import (
    render_template, compute_config_hash, get_device_variables,
    validate_template_syntax, TemplateRenderError,
)
from app.template_schemas import (
    TemplateCreate, TemplateUpdate, TemplateResponse, TemplateListResponse,
    BindingCreate, BindingResponse, BindingListResponse,
    RenderRequest, RenderResponse,
    ValidateRequest, ValidateResponse,
    DeployRequest, DeploymentTaskResponse, DeploymentListResponse,
    CompareResponse,
)
from sqlalchemy import select

router = APIRouter(prefix="/api", tags=["templates"])


# --- Template CRUD ---

@router.post("/templates/", response_model=TemplateResponse, status_code=201)
def api_create_template(data: TemplateCreate, db: Session = Depends(get_db)):
    try:
        template = create_template(db, data)
    except Exception:
        raise HTTPException(status_code=409, detail="Template with this name already exists")
    return template


@router.get("/templates/", response_model=TemplateListResponse)
def api_list_templates(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    templates, total = get_templates(db, skip=skip, limit=limit)
    return TemplateListResponse(total=total, templates=templates)


@router.get("/templates/{template_id}", response_model=TemplateResponse)
def api_get_template(template_id: int, db: Session = Depends(get_db)):
    template = get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    return template


@router.put("/templates/{template_id}", response_model=TemplateResponse)
def api_update_template(template_id: int, data: TemplateUpdate, db: Session = Depends(get_db)):
    template = update_template(db, template_id, data)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    return template


@router.delete("/templates/{template_id}", status_code=204)
def api_delete_template(template_id: int, db: Session = Depends(get_db)):
    if not delete_template(db, template_id):
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")


# --- Render & Validate ---

@router.post("/templates/render-preview", response_model=RenderResponse)
def api_render_preview(data: RenderRequest, db: Session = Depends(get_db)):
    template = get_template(db, data.template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {data.template_id} not found")

    stmt = select(Device).where(Device.device_id == data.device_id)
    device = db.execute(stmt).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{data.device_id}' not found")

    variables = get_device_variables(device)
    try:
        rendered = render_template(template.content, variables)
    except TemplateRenderError as e:
        raise HTTPException(status_code=422, detail={
            "error_type": e.error_type,
            "message": e.message,
            "details": e.details,
        })

    config_hash = compute_config_hash(rendered)
    return RenderResponse(rendered_content=rendered, config_hash=config_hash, variables_used=variables)


@router.post("/templates/validate", response_model=ValidateResponse)
def api_validate_template(data: ValidateRequest):
    valid, error = validate_template_syntax(data.content)
    return ValidateResponse(valid=valid, error=error)


# --- Bindings ---

@router.post("/bindings/", response_model=BindingResponse, status_code=201)
def api_create_binding(data: BindingCreate, db: Session = Depends(get_db)):
    try:
        binding = create_binding(db, data)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateBindingError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return binding


@router.get("/bindings/", response_model=BindingListResponse)
def api_list_bindings(device_id: str = None, template_id: int = None,
                      skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    bindings, total = get_bindings(db, device_id=device_id, template_id=template_id, skip=skip, limit=limit)
    return BindingListResponse(total=total, bindings=bindings)


@router.delete("/bindings/{binding_id}", status_code=204)
def api_delete_binding(binding_id: int, db: Session = Depends(get_db)):
    if not delete_binding(db, binding_id):
        raise HTTPException(status_code=404, detail=f"Binding {binding_id} not found")


@router.get("/bindings/{binding_id}/compare", response_model=CompareResponse)
def api_compare_binding(binding_id: int, db: Session = Depends(get_db)):
    binding = get_binding(db, binding_id)
    if not binding:
        raise HTTPException(status_code=404, detail=f"Binding {binding_id} not found")
    is_match = (
        binding.expected_config_hash is not None
        and binding.expected_config_hash == binding.current_config_hash
    )
    return CompareResponse(
        binding_id=binding.id,
        device_id=binding.device_id,
        expected_config_hash=binding.expected_config_hash,
        current_config_hash=binding.current_config_hash,
        is_match=is_match,
    )


# --- Deployments ---

@router.post("/deployments/", response_model=DeploymentTaskResponse, status_code=201)
def api_create_deployment(data: DeployRequest, db: Session = Depends(get_db)):
    try:
        task = create_deployment(db, data.binding_id)
    except BindingNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return task


@router.get("/deployments/", response_model=DeploymentListResponse)
def api_list_deployments(binding_id: int = None, skip: int = 0, limit: int = 50,
                         db: Session = Depends(get_db)):
    deployments, total = get_deployments(db, binding_id=binding_id, skip=skip, limit=limit)
    return DeploymentListResponse(total=total, deployments=deployments)
