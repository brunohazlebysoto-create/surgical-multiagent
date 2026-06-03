from docx import Document
from app.services.docx_generator import parse_inline_formatting
import pytest

@pytest.fixture
def empty_paragraph():
    doc = Document()
    return doc.add_paragraph()

def test_parse_inline_formatting_plain_text(empty_paragraph):
    """Test plain text without any bold formatting."""
    text = "This is a plain text without bold."
    parse_inline_formatting(empty_paragraph, text)

    assert len(empty_paragraph.runs) == 1
    assert empty_paragraph.runs[0].text == "This is a plain text without bold."
    assert empty_paragraph.runs[0].bold is None # Python-docx sets bold to None by default for normal text

def test_parse_inline_formatting_single_bold(empty_paragraph):
    """Test text with a single bold segment."""
    text = "This is **bold** text."
    parse_inline_formatting(empty_paragraph, text)

    assert len(empty_paragraph.runs) == 3
    assert empty_paragraph.runs[0].text == "This is "
    assert empty_paragraph.runs[0].bold is None

    assert empty_paragraph.runs[1].text == "bold"
    assert empty_paragraph.runs[1].bold is True

    assert empty_paragraph.runs[2].text == " text."
    assert empty_paragraph.runs[2].bold is None

def test_parse_inline_formatting_multiple_bold(empty_paragraph):
    """Test text with multiple bold segments."""
    text = "**First** and **second**."
    parse_inline_formatting(empty_paragraph, text)

    runs = empty_paragraph.runs
    assert len(runs) == 5

    # re.split includes empty string at the beginning because ** is at the start
    assert runs[0].text == ""
    assert runs[0].bold is None

    assert runs[1].text == "First"
    assert runs[1].bold is True

    assert runs[2].text == " and "
    assert runs[2].bold is None

    assert runs[3].text == "second"
    assert runs[3].bold is True

    assert runs[4].text == "."
    assert runs[4].bold is None

def test_parse_inline_formatting_all_bold(empty_paragraph):
    """Test text that is completely wrapped in bold tags."""
    text = "**completely bold**"
    parse_inline_formatting(empty_paragraph, text)

    runs = empty_paragraph.runs
    assert len(runs) == 3

    assert runs[0].text == ""
    assert runs[1].text == "completely bold"
    assert runs[1].bold is True
    assert runs[2].text == ""

def test_parse_inline_formatting_consecutive_bold(empty_paragraph):
    """Test consecutive bold segments."""
    text = "**one****two**"
    parse_inline_formatting(empty_paragraph, text)

    runs = empty_paragraph.runs
    assert len(runs) == 5

    assert runs[0].text == ""
    assert runs[1].text == "one"
    assert runs[1].bold is True
    assert runs[2].text == ""
    assert runs[3].text == "two"
    assert runs[3].bold is True
    assert runs[4].text == ""

def test_parse_inline_formatting_malformed_bold(empty_paragraph):
    """Test malformed bold tags (e.g. single asterisk)."""
    text = "This is *not bold* and ** this is unclosed"
    parse_inline_formatting(empty_paragraph, text)

    runs = empty_paragraph.runs
    assert len(runs) == 1
    assert runs[0].text == "This is *not bold* and ** this is unclosed"
    assert runs[0].bold is None

def test_parse_inline_formatting_empty_string(empty_paragraph):
    """Test with an empty string."""
    text = ""
    parse_inline_formatting(empty_paragraph, text)

    assert len(empty_paragraph.runs) == 1
    assert empty_paragraph.runs[0].text == ""
    assert empty_paragraph.runs[0].bold is None
