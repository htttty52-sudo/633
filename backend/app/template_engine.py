import hashlib
from typing import Optional

import jinja2
import yaml


class TemplateRenderError(Exception):
    def __init__(self, error_type: str, message: str, details: dict = None):
        self.error_type = error_type
        self.message = message
        self.details = details or {}
        super().__init__(message)


def get_device_variables(device) -> dict:
    return {
        "device_id": device.device_id,
        "model": device.model,
        "kernel_version": device.kernel_version,
        "is_online": device.is_online,
    }


def validate_template_syntax(content: str) -> tuple[bool, Optional[str]]:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    try:
        env.parse(content)
        return True, None
    except jinja2.TemplateSyntaxError as e:
        return False, f"Line {e.lineno}: {e.message}"


def render_template(template_content: str, variables: dict) -> str:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)

    try:
        template = env.from_string(template_content)
    except jinja2.TemplateSyntaxError as e:
        raise TemplateRenderError(
            error_type="syntax_error",
            message=f"Template syntax error at line {e.lineno}: {e.message}",
            details={"line": e.lineno, "description": e.message},
        )

    try:
        rendered = template.render(**variables)
    except jinja2.UndefinedError as e:
        raise TemplateRenderError(
            error_type="missing_variable",
            message=str(e),
            details={"available_variables": list(variables.keys())},
        )

    try:
        yaml.safe_load(rendered)
    except yaml.YAMLError as e:
        raise TemplateRenderError(
            error_type="invalid_yaml_output",
            message=f"Rendered output is not valid YAML: {e}",
            details={"rendered_content": rendered},
        )

    return rendered


def compute_config_hash(rendered_content: str) -> str:
    return hashlib.sha256(rendered_content.encode("utf-8")).hexdigest()
