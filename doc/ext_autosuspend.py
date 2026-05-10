"""Sphinx extension for autosuspend check documentation.

This extension dynamically generates documentation for autosuspend checks
by discovering check classes and extracting their docstrings and config_params.
"""

import inspect
import re
import sys
from pathlib import Path
from typing import Any

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import ViewList
from sphinx.application import Sphinx
from sphinx.util.nodes import nested_parse_with_titles

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autosuspend import discover_available_checks
from autosuspend.checks import Activity, Wakeup
from autosuspend.config import ParameterSchema

_GOOGLE_SECTION_RE = re.compile(r"^[A-Z][A-Za-z ]*:$")


def render_google_docstring(doc: str) -> list[str]:
    """Convert a Google-style docstring to RST lines for use in generated docs.

    Handles the ``Requires:`` custom section by emitting a ``.. rubric::``
    directive followed by the section body indented under it.  All other
    content is passed through verbatim.

    After ``inspect.cleandoc`` all indentation is stripped, so section body
    lines cannot be detected by indentation.  Instead the body is consumed
    until the next Google-style section header (a line matching
    ``^[A-Z][A-Za-z ]*:$``) or end of string.
    """
    lines = doc.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "Requires:":
            out.append(".. rubric:: Requires")
            out.append("")
            i += 1
            # Consume optional blank line after section header
            if i < len(lines) and lines[i].strip() == "":
                i += 1
            # Consume body until the next Google-style section header or EOF
            while i < len(lines):
                body_line = lines[i]
                if _GOOGLE_SECTION_RE.match(body_line.strip()):
                    break
                out.append(body_line if body_line.strip() else "")
                i += 1
            out.append("")
        else:
            out.append(line)
            i += 1
    return out


def format_default_value(param: ParameterSchema) -> str:
    """Format the default value for display."""
    if param.default is None:
        return ""
    if isinstance(param.default, bool):
        return f"``{str(param.default).lower()}``"
    if isinstance(param.default, str):
        return f"``{param.default}``"
    if isinstance(param.default, (list, tuple)):
        formatted_items = ", ".join(f"``{item}``" for item in param.default)
        return formatted_items
    return f"``{param.default}``"


def generate_option_rst(param: ParameterSchema, program_name: str) -> list[str]:
    """Generate RST lines for a single option."""
    lines = []
    lines.append(f".. option:: {param.name}")
    lines.append("")

    description = param.description
    if param.default is not None:
        default_str = format_default_value(param)
        if default_str:
            # Add default at the end with proper punctuation
            if not description.endswith("."):
                description += "."
            description = f"{description} Default: {default_str}."

    # Indent description properly
    for line in description.split("\n"):
        lines.append(f"   {line}")
    lines.append("")

    if param.enum_values is not None:
        formatted = ", ".join(f"``{v}``" for v in param.enum_values)
        lines.append(f"   Allowed values: {formatted}.")
        lines.append("")

    if param.minimum is not None and param.maximum is not None:
        lines.append(
            f"   Value must be between ``{param.minimum}`` and ``{param.maximum}``."
        )
        lines.append("")
    elif param.minimum is not None:
        lines.append(f"   Value must be at least ``{param.minimum}``.")
        lines.append("")
    elif param.maximum is not None:
        lines.append(f"   Value must be at most ``{param.maximum}``.")
        lines.append("")

    return lines


class AutosuspendChecksDirective(Directive):
    """Directive to generate documentation for all autosuspend checks."""

    has_content = False
    required_arguments = 1  # 'activity' or 'wakeup'
    optional_arguments = 0

    def run(self) -> list[nodes.Node]:
        check_type = self.arguments[0]

        if check_type == "activity":
            checks = discover_available_checks("activity", Activity)
            title = "Available activity checks"
            check_prefix = "check"
        elif check_type == "wakeup":
            checks = discover_available_checks("wakeup", Wakeup)
            title = "Available wake up checks"
            check_prefix = "wakeup"
        else:
            raise self.error(
                f"Unknown check type: {check_type!r}. Expected 'activity' or 'wakeup'."
            )

        # Sort checks by name (keys are already the effective names/aliases)
        sorted_checks = sorted(checks.items(), key=lambda x: x[0])

        # Generate RST content
        rst = ViewList()

        # Add header - don't duplicate the label since it's already in the RST file
        rst.append(title, "<autosuspend>")
        rst.append("#" * len(title), "<autosuspend>")
        rst.append("", "<autosuspend>")

        if check_type == "activity":
            rst.append(
                "The following checks for activity are currently implemented.",
                "<autosuspend>",
            )
        else:
            rst.append(
                "The following checks for wake up times are currently implemented.",
                "<autosuspend>",
            )
        rst.append(
            "Each of them is described with its available configuration options and required optional dependencies.",
            "<autosuspend>",
        )
        rst.append("", "<autosuspend>")

        # Add each check
        for class_name, check_class in sorted_checks:
            # Create reference label
            label_name = self._to_kebab_case(class_name)
            rst.append(f".. _{check_prefix}-{label_name}:", "<autosuspend>")
            rst.append("", "<autosuspend>")

            # Add title
            rst.append(class_name, "<autosuspend>")
            rst.append("*" * len(class_name), "<autosuspend>")
            rst.append("", "<autosuspend>")

            # Add program directive for option linking
            rst.append(f".. program:: {check_prefix}-{label_name}", "<autosuspend>")
            rst.append("", "<autosuspend>")

            # Add docstring
            if check_class.__doc__:
                doc = inspect.cleandoc(check_class.__doc__)
                for line in render_google_docstring(doc):
                    rst.append(line, "<autosuspend>")
                rst.append("", "<autosuspend>")

            # Add Options section if there are config parameters
            if check_class.config_parameters:
                rst.append("Options", "<autosuspend>")
                rst.append("=======", "<autosuspend>")
                rst.append("", "<autosuspend>")

                for param in check_class.config_parameters:
                    for line in generate_option_rst(
                        param, f"{check_prefix}-{label_name}"
                    ):
                        rst.append(line, "<autosuspend>")

        # Parse the RST
        node = nodes.section()
        node.document = self.state.document
        nested_parse_with_titles(self.state, rst, node)

        return node.children

    def _to_kebab_case(self, name: str) -> str:
        """Convert PascalCase to kebab-case."""
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1-\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1-\2", s1).lower()


def setup(app: Sphinx) -> dict[str, Any]:
    """Set up the Sphinx extension."""
    app.add_directive("autosuspend-checks", AutosuspendChecksDirective)

    return {
        "version": "0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
