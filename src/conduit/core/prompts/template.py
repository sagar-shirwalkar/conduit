"""Jinja2-based prompt template rendering."""

from __future__ import annotations

from typing import Any

import jinja2

from conduit.common.errors import ValidationError


# Sandboxed Jinja2 environment — no file access, limited builtins
_ENV = jinja2.sandbox.SandboxedEnvironment(
    undefined=jinja2.StrictUndefined,
    autoescape=False,
)


def render_template(template_str: str, variables: dict[str, Any]) -> str:
    """
    Render a Jinja2 template with the given variables

    Uses a sandboxed environment with strict undefined behavior

    Raises:
        ValidationError: If template is invalid or required variable is missing
    """
    try:
        template = _ENV.from_string(template_str)
        return template.render(**variables)
    except jinja2.UndefinedError as e:
        raise ValidationError(
            f"Missing required template variable: {e}",
            details={"provided_variables": list(variables.keys())},
        ) from e
    except jinja2.TemplateSyntaxError as e:
        raise ValidationError(
            f"Invalid template syntax: {e}",
            details={"line": e.lineno},
        ) from e
    except jinja2.SecurityError as e:
        raise ValidationError(f"Template security violation: {e}") from e


def validate_template(template_str: str) -> list[str]:
    """
    Validate a template and return the list of undeclared variables.

    Returns:
        List of variable names referenced in the template
    """
    try:
        ast = _ENV.parse(template_str)
        return sorted(jinja2.meta.find_undeclared_variables(ast))
    except jinja2.TemplateSyntaxError as e:
        raise ValidationError(
            f"Invalid template syntax: {e}",
            details={"line": e.lineno},
        ) from e