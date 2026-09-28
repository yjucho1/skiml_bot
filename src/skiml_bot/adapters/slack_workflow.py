"""Trigger a Slack Workflow Builder workflow through its webhook trigger."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

import httpx

Sender = Callable[..., httpx.Response]


class WorkflowTriggerError(RuntimeError):
    """The Slack workflow webhook could not be triggered."""


class SlackWorkflowWebhook:
    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float = 10.0,
        sender: Sender = httpx.post,
    ) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "hooks.slack.com"
            or not parsed.path.startswith("/triggers/")
        ):
            raise ValueError(
                "SLURM_ALERT_WORKFLOW_WEBHOOK_URL must be a Slack workflow webhook "
                "starting with https://hooks.slack.com/triggers/"
            )
        if timeout_seconds <= 0:
            raise ValueError("Slack workflow webhook timeout must be positive")
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._sender = sender

    def trigger(self, reason: str) -> None:
        """Start the workflow with its configured `reason` variable."""
        try:
            response = self._sender(
                self._url,
                json={"reason": reason},
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise WorkflowTriggerError(
                f"Slack workflow webhook request failed ({type(error).__name__})"
            ) from None
        if response.is_error:
            raise WorkflowTriggerError(
                f"Slack workflow webhook returned HTTP {response.status_code}"
            )
