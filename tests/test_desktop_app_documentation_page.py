from __future__ import annotations

from desktop_app.pages.documentation import DOC_SECTIONS


def test_doc_sections_cover_required_topics():
    headings = [heading for heading, _body in DOC_SECTIONS]
    assert "Preparing a Device" in headings
    assert "Running a Batch" in headings
    assert "Understanding Test Statuses" in headings
    assert "Reading Reports & Evidence" in headings


def test_every_doc_section_has_non_empty_body():
    for heading, body in DOC_SECTIONS:
        assert body.strip(), f"section '{heading}' has an empty body"
