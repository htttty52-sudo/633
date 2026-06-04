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


def parse_config_fields(config_text: str) -> dict[str, str]:
    """Parse a KEY=VALUE config into a dict. Ignores comments and blank lines."""
    fields = {}
    for line in config_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip()
    return fields


def compute_field_diff_count(expected_config: str, current_config: str) -> int:
    """Compare two configs field-by-field, return number of differing fields."""
    if not expected_config or not current_config:
        return 0
    expected_fields = parse_config_fields(expected_config)
    current_fields = parse_config_fields(current_config)
    all_keys = set(expected_fields.keys()) | set(current_fields.keys())
    diff_count = 0
    for key in all_keys:
        if expected_fields.get(key) != current_fields.get(key):
            diff_count += 1
    return diff_count


def simulate_device_config(rendered_config: str, drift_count: int) -> str:
    """Simulate a device's current config by mutating N random fields from the expected config."""
    if drift_count == 0:
        return rendered_config

    import random
    lines = rendered_config.splitlines()
    mutable_indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            mutable_indices.append(i)

    if not mutable_indices:
        return rendered_config

    to_mutate = random.sample(mutable_indices, min(drift_count, len(mutable_indices)))
    result = lines[:]
    for idx in to_mutate:
        key, _, value = result[idx].partition("=")
        result[idx] = f"{key}=DRIFTED_{random.randint(100, 999)}"

    return "\n".join(result)
