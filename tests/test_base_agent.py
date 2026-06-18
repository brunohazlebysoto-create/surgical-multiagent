import pytest
from app.agents.base import BaseAgent

@pytest.fixture
def base_agent():
    return BaseAgent(name="TestAgent", role="Tester", color="#FFFFFF", icon="🔍")

def test_base_agent_format_log_happy_path(base_agent):
    result = base_agent.format_log(text="This is a test message.", stage="Initialization")
    assert result == {
        "type": "log",
        "agent": "TestAgent",
        "role": "Tester",
        "text": "This is a test message.",
        "stage": "Initialization",
        "color": "#FFFFFF",
        "icon": "🔍"
    }

def test_base_agent_format_log_empty_strings():
    agent = BaseAgent(name="", role="", color="", icon="")
    result = agent.format_log(text="", stage="")
    assert result == {
        "type": "log",
        "agent": "",
        "role": "",
        "text": "",
        "stage": "",
        "color": "",
        "icon": ""
    }

def test_base_agent_format_log_none_values(base_agent):
    # Depending on how the system is used, sometimes None might be passed.
    result = base_agent.format_log(text=None, stage=None)
    assert result == {
        "type": "log",
        "agent": "TestAgent",
        "role": "Tester",
        "text": None,
        "stage": None,
        "color": "#FFFFFF",
        "icon": "🔍"
    }

def test_base_agent_format_log_special_characters(base_agent):
    special_text = "<script>alert('xss');</script> & 😊 \n\t"
    special_stage = "Stage_1: @#$%"
    result = base_agent.format_log(text=special_text, stage=special_stage)
    assert result == {
        "type": "log",
        "agent": "TestAgent",
        "role": "Tester",
        "text": "<script>alert('xss');</script> & 😊 \n\t",
        "stage": "Stage_1: @#$%",
        "color": "#FFFFFF",
        "icon": "🔍"
    }

def test_base_agent_format_log_missing_arguments(base_agent):
    with pytest.raises(TypeError) as excinfo:
        # Missing both arguments
        base_agent.format_log()
    assert "missing 2 required positional arguments" in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:
        # Missing 'stage'
        base_agent.format_log(text="Test")
    assert "missing 1 required positional argument" in str(excinfo.value)

def test_base_agent_format_log_large_text(base_agent):
    large_text = "A" * 100000
    large_stage = "B" * 10000
    result = base_agent.format_log(text=large_text, stage=large_stage)
    assert result == {
        "type": "log",
        "agent": "TestAgent",
        "role": "Tester",
        "text": large_text,
        "stage": large_stage,
        "color": "#FFFFFF",
        "icon": "🔍"
    }
