from controller.config import load_env_file


def test_load_env_file_preserves_existing_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "NEW_VALUE=from-file\n"
        "QUOTED='hello world'\n"
        "export EXPORTED=ok\n"
        "EXISTING=from-file\n"
    )
    monkeypatch.setenv("EXISTING", "from-shell")

    load_env_file(env_file)

    assert __import__("os").environ["NEW_VALUE"] == "from-file"
    assert __import__("os").environ["QUOTED"] == "hello world"
    assert __import__("os").environ["EXPORTED"] == "ok"
    assert __import__("os").environ["EXISTING"] == "from-shell"
