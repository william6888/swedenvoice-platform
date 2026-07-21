"""Read-only .env-loader: vanlig syntax utan muterande dotenv-beroende."""

import os

from env_loader import load_env_file


def test_load_env_file_supports_quotes_export_and_comments(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        """
# comment
PLAIN=value
export SPACED = "hello world"
SINGLE='abc#123'
INLINE=value-2  # trailing comment
INVALID-KEY=no
""",
        encoding="utf-8",
    )
    for key in ("PLAIN", "SPACED", "SINGLE", "INLINE"):
        monkeypatch.delenv(key, raising=False)

    assert load_env_file(path) is True
    assert os.environ["PLAIN"] == "value"
    assert os.environ["SPACED"] == "hello world"
    assert os.environ["SINGLE"] == "abc#123"
    assert os.environ["INLINE"] == "value-2"
    assert "INVALID-KEY" not in os.environ


def test_load_env_file_does_not_override_by_default(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("EXISTING=from-file\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "from-process")

    load_env_file(path)
    assert os.environ["EXISTING"] == "from-process"

    load_env_file(path, override=True)
    assert os.environ["EXISTING"] == "from-file"


def test_missing_env_file_is_nonfatal(tmp_path):
    assert load_env_file(tmp_path / "missing.env") is False
