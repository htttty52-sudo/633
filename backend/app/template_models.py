from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConfigTemplate(Base):
    __tablename__ = "config_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=True, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TemplateBinding(Base):
    __tablename__ = "template_bindings"
    __table_args__ = (
        UniqueConstraint("template_id", "device_id", name="uq_template_device"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("config_templates.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id"), nullable=False)
    expected_config_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    current_config_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    drift_field_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bound_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeploymentTask(Base):
    __tablename__ = "deployment_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    binding_id: Mapped[int] = mapped_column(Integer, ForeignKey("template_bindings.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    rendered_content: Mapped[str] = mapped_column(Text, nullable=True)
    error_message: Mapped[str] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
