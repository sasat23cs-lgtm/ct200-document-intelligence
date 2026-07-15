import pytest

from app.parser.exceptions import EmptyDocumentError, MalformedTableError
from app.parser.markdown_parser import parse_markdown


def _find(root, heading_substr: str):
    matches = [n for n in root.walk() if heading_substr in n.heading]
    return matches


class TestBasicStructure:
    def test_simple_nesting(self):
        md = "# Title\n\n## A\n\nbody a\n\n### A.1\n\nbody a1\n"
        root = parse_markdown(md)
        h1 = root.children[0]
        assert h1.heading == "Title"
        a = h1.children[0]
        assert a.heading == "A"
        assert "body a" in a.body
        assert a.children[0].heading == "A.1"

    def test_empty_document_raises(self):
        with pytest.raises(EmptyDocumentError):
            parse_markdown("just a paragraph, no headings at all")


class TestDuplicateHeadings:
    """Assignment-required: duplicate heading text must produce two distinct
    node IDs with correct (different) parents."""

    def test_ct200_duplicate_error_codes_headings(self):
        text = open("data/ct200_manual.md").read()
        root = parse_markdown(text)
        matches = _find(root, "Error Codes")
        assert len(matches) == 2
        n1, n2 = matches
        assert n1.logical_node_id != n2.logical_node_id
        assert n1.parent.heading != n2.parent.heading
        assert n1.parent.heading.startswith("4.")
        assert n2.parent.heading.startswith("7.")
        # Distinct content -> distinct hashes.
        assert n1.content_hash != n2.content_hash


class TestHeadingDepthVsLabelMismatch:
    """2.1.1.1 is only one markdown level below 2.1 (### -> ####), even though
    its numeric label implies two levels of nesting. Tree structure must
    follow markdown depth, not the label."""

    def test_ct200_2_1_1_1_is_direct_child_of_2_1(self):
        text = open("data/ct200_manual.md").read()
        root = parse_markdown(text)
        [battery_node] = _find(root, "Battery Life Under Typical Use")
        assert battery_node.parent.heading.startswith("2.1 ")
        assert battery_node.level == 4
        assert battery_node.parent.level == 3


class TestOutOfOrderHeadings:
    """3.4 Auto Shutoff physically precedes 3.3 Result Display in the file.
    Sibling order must follow document position, not the numeric label."""

    def test_ct200_document_order_preserved_despite_label_order(self):
        text = open("data/ct200_manual.md").read()
        root = parse_markdown(text)
        [section_3] = _find(root, "3. Device Operation")
        headings_in_order = [c.heading for c in section_3.children]
        idx_31 = next(i for i, h in enumerate(headings_in_order) if h.startswith("3.1"))
        idx_34 = next(i for i, h in enumerate(headings_in_order) if h.startswith("3.4"))
        idx_33 = next(i for i, h in enumerate(headings_in_order) if h.startswith("3.3"))
        assert idx_31 < idx_34 < idx_33  # document order, not numeric order


class TestTablesAndComments:
    def test_table_preserved_verbatim_in_body(self):
        text = open("data/ct200_manual.md").read()
        root = parse_markdown(text)
        [general_specs] = _find(root, "2.1 General Specifications")
        assert "| Parameter | Value |" in general_specs.body
        assert "| Measurement method | Oscillometric |" in general_specs.body

    def test_html_comment_preserved_on_root(self):
        text = open("data/ct200_manual.md").read()
        root = parse_markdown(text)
        h1 = root.children[0]
        assert "<!-- TODO: confirm with regulatory -->" in h1.body

    def test_malformed_table_raises(self):
        md = (
            "# Title\n\n## Section\n\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 | 3 |\n"  # extra column -> malformed
        )
        with pytest.raises(MalformedTableError):
            parse_markdown(md)


class TestOrderedListPreservedAsBody:
    def test_classification_list_stays_in_parent_body(self):
        text = open("data/ct200_manual.md").read()
        root = parse_markdown(text)
        [result_node] = _find(root, "3.3 Result Display")
        assert "1. Normal: systolic < 120" in result_node.body
        assert result_node.children == []  # not split into separate nodes


class TestLogicalNodeIds:
    def test_logical_ids_are_positional_paths(self):
        md = "# T\n\n## A\n\n## B\n\n### B.1\n"
        root = parse_markdown(md)
        t = root.children[0]
        a, b = t.children
        assert a.logical_node_id == "0.0"
        assert b.logical_node_id == "0.1"
        assert b.children[0].logical_node_id == "0.1.0"
