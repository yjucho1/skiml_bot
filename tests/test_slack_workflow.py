import httpx
import pytest

from skiml_bot.adapters.slack_workflow import SlackWorkflowWebhook, WorkflowTriggerError


def test_workflow_webhook_sends_reason_variable() -> None:
    requests: list[tuple[str, dict[str, str], float]] = []

    def sender(url: str, *, json: dict[str, str], timeout: float) -> httpx.Response:
        requests.append((url, json, timeout))
        return httpx.Response(200)

    webhook = SlackWorkflowWebhook(
        "https://hooks.slack.com/triggers/T123/456/secret",
        sender=sender,
    )

    webhook.trigger("drain 노드 발생")

    assert requests == [
        (
            "https://hooks.slack.com/triggers/T123/456/secret",
            {"reason": "drain 노드 발생"},
            10.0,
        )
    ]


def test_workflow_webhook_rejects_interactive_shortcut_url() -> None:
    with pytest.raises(ValueError, match="hooks.slack.com/triggers"):
        SlackWorkflowWebhook("https://slack.com/shortcuts/F123/secret")


def test_workflow_webhook_does_not_expose_secret_when_request_fails() -> None:
    def sender(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(500)

    webhook = SlackWorkflowWebhook(
        "https://hooks.slack.com/triggers/T123/456/top-secret",
        sender=sender,
    )

    with pytest.raises(WorkflowTriggerError, match="HTTP 500") as caught:
        webhook.trigger("접속 안됨")

    assert "top-secret" not in str(caught.value)
