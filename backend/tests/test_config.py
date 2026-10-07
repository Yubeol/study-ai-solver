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


def test_ocr_det_model_requires_rec_model():
    with pytest.raises(ValidationError):
        make(ocr_det_model="PP-OCRv5_mobile_det")
    s = make(ocr_det_model="PP-OCRv5_mobile_det", ocr_rec_model="korean_PP-OCRv5_mobile_rec")
    assert s.ocr_lang == "korean"


def test_empty_ocr_model_dir_is_none():
    assert make(ocr_model_dir="").ocr_model_dir is None


def test_search_corpus_default_and_values():
    assert make().search_corpus == "mixed"
    assert make(search_corpus="team_text").search_corpus == "team_text"
    with pytest.raises(ValidationError):
        make(search_corpus="blocks")


def test_asset_url_template():
    assert make().asset_url("a/b.jpg") is None
    s = make(asset_url_template=" https://cdn.example/{key} ")
    assert s.asset_url("a/b.jpg") == "https://cdn.example/a/b.jpg"
    assert s.asset_url(None) is None
    with pytest.raises(ValidationError):
        make(asset_url_template="https://cdn.example/")
