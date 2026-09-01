from skiml_bot.config import Settings


def test_disabled_integrations_do_not_require_their_credentials(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("NOTION_TOKEN", "ntn-test")
    monkeypatch.setenv("NOTION_ROOT_PAGE_IDS", "root-page")
    monkeypatch.setenv("SKIML_FEATURES", "knowledge")
    for name in (
        "GOOGLE_OAUTH_TOKEN_FILE",
        "SLURM_SSH_TARGET",
        "SLURM_SSH_IDENTITY_FILE",
        "SLURM_SSH_KNOWN_HOSTS_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.enabled_features == frozenset({"knowledge"})
    assert settings.google_oauth_token_file is None
    assert settings.slurm_ssh_target is None


def test_meetings_require_shared_calendar_oauth_token(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SKIML_FEATURES", "meetings")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", "/secure/calendar-token.json")

    settings = Settings.from_env()

    assert settings.google_oauth_token_file == "/secure/calendar-token.json"


def test_server_status_requires_only_ssh_target(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SKIML_FEATURES", "server_status")
    monkeypatch.setenv("SLURM_SSH_TARGET", "bot-user@login.example.edu")
    monkeypatch.setenv("SLURM_SSH_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("SLURM_STATUS_CHANNEL_ID", "C0123456789")
    monkeypatch.setenv("SLURM_STATUS_INTERVAL_SECONDS", "1800")
    monkeypatch.setenv("SLURM_STATUS_START_AT", "2026-09-01T15:00:00+09:00")

    settings = Settings.from_env()

    assert settings.slurm_ssh_target == "bot-user@login.example.edu"
    assert settings.slurm_ssh_timeout_seconds == 7
    assert settings.slurm_status_channel_id == "C0123456789"
    assert settings.slurm_status_interval_seconds == 1800
    assert settings.slurm_status_start_at.isoformat() == "2026-09-01T15:00:00+09:00"
