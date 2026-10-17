from app.config import load_local_env


def test_local_env_only_loads_allowed_keys_and_preserves_process_env(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("AMD_MODEL_ID=file-model\nUNTRUSTED_SWITCH=yes\nAMD_API_KEY='file-key'\n", encoding="utf-8")
    monkeypatch.setenv("AMD_MODEL_ID", "process-model")
    monkeypatch.delenv("AMD_API_KEY", raising=False)
    monkeypatch.delenv("UNTRUSTED_SWITCH", raising=False)
    load_local_env(path)
    import os
    assert os.environ["AMD_MODEL_ID"] == "process-model"
    assert os.environ["AMD_API_KEY"] == "file-key"
    assert "UNTRUSTED_SWITCH" not in os.environ
