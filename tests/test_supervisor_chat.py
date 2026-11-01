import pytest
from src.ui.supervisor_chat import extract_text_from_chunk, sanitize_displayed_message


def test_extract_text_from_plain_string():
    assert extract_text_from_chunk("Hello world") == "Hello world"


def test_extract_text_from_gemini_chunks():
    # Test LangChain ChatGoogleGenerativeAI chunk format
    chunk_1 = [{'type': 'text', 'text': 'Here is the audit', 'index': 0}]
    chunk_2 = [{'type': 'text', 'text': ' timeline:', 'index': 0}]
    chunk_signature = [{'type': 'text', 'text': '', 'extras': {'signature': 'AbCdEf123'}}]

    assert extract_text_from_chunk(chunk_1) == "Here is the audit"
    assert extract_text_from_chunk(chunk_2) == " timeline:"
    assert extract_text_from_chunk(chunk_signature) == ""


def test_extract_text_from_message_chunk_object():
    class DummyChunk:
        def __init__(self, content):
            self.content = content

    chunk = DummyChunk([{'type': 'text', 'text': 'Timeline event'}])
    assert extract_text_from_chunk(chunk) == "Timeline event"


def test_sanitize_displayed_message():
    raw_serialized = (
        "[{'type': 'text', 'text': 'Here is the audit', 'index': 0}]"
        "[{'type': 'text', 'text': ' timeline detailing the actions taken on Case CASE-2026-1007, in chronological order:\\n\\n* ', 'index': 0}]"
        "[{'type': 'text', 'text': '2026-11-01 06:29:13 UTC \\n* Actor: ', 'index': 0}]"
        "[{'type': 'text', 'text': ' intake_agent \\n * Action: ', 'index': 0}]"
        "[{'type': 'text', 'text': '', 'extras': {'signature': 'EvUNCvINAWkUfROZMB/...'}}]"
    )
    cleaned = sanitize_displayed_message(raw_serialized)
    assert "Here is the audit timeline detailing the actions" in cleaned
    assert "2026-11-01 06:29:13 UTC" in cleaned
    assert "intake_agent" in cleaned
    assert "EvUNCvINAWkUfROZMB" not in cleaned
    assert "[{'type':" not in cleaned


def test_sanitize_normal_message():
    normal = "**Audit Timeline:**\n- 2026-11-01 10:00:00: Event"
    assert sanitize_displayed_message(normal) == normal

