"""Tests for the ext_autosuspend Sphinx extension."""

from ext_autosuspend import render_google_docstring


class TestRenderGoogleDocstring:
    """Tests for render_google_docstring."""

    def test_no_requires_section_passthrough(self) -> None:
        doc = """\
A plain docstring.

With multiple paragraphs."""
        result = render_google_docstring(doc)
        assert result == ["A plain docstring.", "", "With multiple paragraphs."]

    def test_requires_section_emits_rubric(self) -> None:
        doc = """\
Description.

Requires:
some-package"""
        result = render_google_docstring(doc)
        assert ".. rubric:: Requires" in result

    def test_requires_blank_line_after_header_consumed(self) -> None:
        doc = """\
Description.

Requires:

some-package"""
        result = render_google_docstring(doc)
        # The blank line between "Requires:" and the body should not produce
        # a doubled blank line in the output immediately after the rubric.
        rubric_idx = result.index(".. rubric:: Requires")
        assert result[rubric_idx + 1] == ""
        assert result[rubric_idx + 2] == "some-package"

    def test_requires_body_stops_at_next_google_section(self) -> None:
        doc = """\
Description.

Requires:
some-package

Note:
A note."""
        result = render_google_docstring(doc)
        # "Note:" is a Google-style section header and must not appear inside
        # the Requires body; it should be passed through as a plain line.
        body_start = result.index(".. rubric:: Requires") + 2
        requires_body = result[body_start:]
        assert "some-package" in requires_body
        assert "Note:" in result

    def test_plain_unindented_body_line_preserved(self) -> None:
        doc = """\
Description.

Requires:
some-package >= 1.0"""
        result = render_google_docstring(doc)
        assert "some-package >= 1.0" in result

    def test_bullet_list_indentation_preserved(self) -> None:
        """Leading spaces on bullet list items must be preserved."""
        doc = """\
Description.

Requires:

  * some-package
  * other-package"""
        result = render_google_docstring(doc)
        assert "  * some-package" in result
        assert "  * other-package" in result

    def test_rst_directive_indentation_preserved(self) -> None:
        """Leading spaces on RST directives inside Requires: must be preserved."""
        doc = """\
Description.

Requires:

  .. code-block:: bash

    pip install foo"""
        result = render_google_docstring(doc)
        assert "  .. code-block:: bash" in result
        assert "    pip install foo" in result

    def test_indented_continuation_preserved(self) -> None:
        """Indented continuation lines must retain their leading whitespace."""
        doc = """\
Description.

Requires:

some-package
  indented continuation"""
        result = render_google_docstring(doc)
        assert "  indented continuation" in result
