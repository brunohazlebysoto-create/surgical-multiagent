import pytest
from app.services.document_parser import uuid_hash

def test_uuid_hash_basic():
    name = "test_file.pdf"
    result = uuid_hash(name)
    assert isinstance(result, str)
    assert len(result) == 8

def test_uuid_hash_consistency():
    name = "consistent_name.docx"
    assert uuid_hash(name) == uuid_hash(name)

def test_uuid_hash_different_inputs():
    assert uuid_hash("file1.txt") != uuid_hash("file2.txt")

def test_uuid_hash_empty_string():
    result = uuid_hash("")
    assert isinstance(result, str)
    assert len(result) == 8

def test_uuid_hash_special_characters():
    name = "file_with_special_chars!@#$%^&*()_+.pdf"
    result = uuid_hash(name)
    assert isinstance(result, str)
    assert len(result) == 8

def test_uuid_hash_unicode():
    name = "archivo_con_acentos_áéíóú.pdf"
    result = uuid_hash(name)
    assert isinstance(result, str)
    assert len(result) == 8
