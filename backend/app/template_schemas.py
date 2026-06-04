from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    content: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Template name cannot be empty")
        return v.strip()

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Template content cannot be empty")
        return v


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: str
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    total: int
    templates: list[TemplateResponse]


class BindingCreate(BaseModel):
    template_id: int
    device_id: str


class BindingResponse(BaseModel):
    id: int
    template_id: int
    device_id: str
    expected_config_hash: Optional[str]
    current_config_hash: Optional[str]
    bound_at: datetime

    model_config = {"from_attributes": True}


class BindingListResponse(BaseModel):
    total: int
    bindings: list[BindingResponse]


class RenderRequest(BaseModel):
    template_id: int
    device_id: str


class RenderResponse(BaseModel):
    rendered_content: str
    config_hash: str
    variables_used: dict


class ValidateRequest(BaseModel):
    content: str


class ValidateResponse(BaseModel):
    valid: bool
    error: Optional[str] = None


class DeployRequest(BaseModel):
    binding_id: int


class DeploymentTaskResponse(BaseModel):
    id: int
    binding_id: int
    status: str
    rendered_content: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DeploymentListResponse(BaseModel):
    total: int
    deployments: list[DeploymentTaskResponse]


class CompareResponse(BaseModel):
    binding_id: int
    device_id: str
    expected_config_hash: Optional[str]
    current_config_hash: Optional[str]
    is_match: bool
