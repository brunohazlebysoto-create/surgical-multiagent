import os
import importlib
import pytest
from unittest.mock import patch
import app.core.config as config
from app.core.config import Settings

@pytest.fixture(autouse=True)
def restore_config():
    # Record original environment and reload module at the end
    original_env = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(original_env)
    importlib.reload(config)

@pytest.fixture(autouse=True)
def mock_load_dotenv():
    with patch('app.core.config.load_dotenv'):
        yield

def test_settings_default_values():
    # Limpiamos el entorno para que no lea keys residuales
    with pytest.MonkeyPatch.context() as m:
        m.delenv("GEMINI_API_KEY", raising=False)
        m.delenv("APP_NAME", raising=False)
        m.delenv("DEBUG", raising=False)
        settings = Settings(_env_file=None)
        assert settings.app_name == "Surgical Multi-Agent Pipeline"
        assert settings.debug is False
        assert settings.gemini_api_key == ""

def test_settings_custom_values():
    with pytest.MonkeyPatch.context() as m:
        m.setenv("GEMINI_API_KEY", "test-key-123")
        m.setenv("APP_NAME", "Custom App Name")
        m.setenv("DEBUG", "true")
        settings = Settings(_env_file=None)
        assert settings.app_name == "Custom App Name"
        assert settings.debug is True
        assert settings.gemini_api_key == "test-key-123"

def test_settings_load_env_file(tmp_path):
    env_content = """
APP_NAME=Loaded From Env
DEBUG=true
GEMINI_API_KEY=env-file-key
"""
    env_file = tmp_path / ".env"
    env_file.write_text(env_content)

    with pytest.MonkeyPatch.context() as m:
        # Asegurarnos de que no haya variables de entorno afectando
        m.delenv("GEMINI_API_KEY", raising=False)
        m.delenv("APP_NAME", raising=False)
        m.delenv("DEBUG", raising=False)

        settings = Settings(_env_file=str(env_file))
        assert settings.app_name == "Loaded From Env"
        assert settings.debug is True
        assert settings.gemini_api_key == "env-file-key"

def test_config_globals_default_values():
    with patch.dict(os.environ, {}, clear=True):
        importlib.reload(config)
        assert config.GEMINI_API_KEYS == []
        assert config.GEMINI_API_KEY == ""
        assert config.GEMINI_MODEL == "gemini-2.5-flash"
        assert config.ACCESS_PASSWORD == ""
        assert config.GEMINI_MAX_CONCURRENT_CALLS == 3
        assert config.GEMINI_PAUSE_SECONDS == 4.5

def test_config_globals_single_gemini_key():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}, clear=True):
        importlib.reload(config)
        assert config.GEMINI_API_KEYS == ["test_key"]
        assert config.GEMINI_API_KEY == "test_key"

def test_config_globals_multiple_gemini_keys():
    with patch.dict(os.environ, {"GEMINI_API_KEYS": "key1, key2 ,key3 "}, clear=True):
        importlib.reload(config)
        assert config.GEMINI_API_KEYS == ["key1", "key2", "key3"]
        assert config.GEMINI_API_KEY == "key1"

def test_config_globals_both_gemini_keys_provided():
    with patch.dict(os.environ, {
        "GEMINI_API_KEYS": "key_a, key_b",
        "GEMINI_API_KEY": "key_ignored"
    }, clear=True):
        importlib.reload(config)
        assert config.GEMINI_API_KEYS == ["key_a", "key_b"]
        assert config.GEMINI_API_KEY == "key_a"

def test_config_globals_empty_gemini_keys():
    with patch.dict(os.environ, {"GEMINI_API_KEYS": ",, "}, clear=True):
        importlib.reload(config)
        assert config.GEMINI_API_KEYS == []
        assert config.GEMINI_API_KEY == ""

def test_config_globals_other_settings():
    with patch.dict(os.environ, {
        "GEMINI_MODEL": "custom-model",
        "ACCESS_PASSWORD": "secret_password"
    }, clear=True):
        importlib.reload(config)
        assert config.GEMINI_MODEL == "custom-model"
        assert config.ACCESS_PASSWORD == "secret_password"
