import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = dict(
    db_host="localhost",
    db_name="db",
    db_user="u",
    db_password="secret-pw",
    db_schema="s1",
    db_app_schema="s1_app",
)


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})


def test_env_loads_both_schemas(settings):
    assert settings.db_schema
    assert settings.db_app_schema
    assert settings.db_schema != settings.db_app_schema


@pytest.mark.parametrize("bad", ["", "Mingyu", "a-b", "a;drop", "1abc", 'x"y'])
def test_invalid_schema_name_rejected(bad):
    with pytest.raises(ValidationError):
        make(db_schema=bad)


def test_judge_provider_defaults_to_none():
    assert make().judge_provider == "none"


def test_unknown_judge_provider_rejected():
    with pytest.raises(ValidationError):
        make(judge_provider="unknown")


def test_password_not_in_repr():
    assert "secret-pw" not in repr(make())
