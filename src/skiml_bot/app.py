"""Slack Bolt application wiring."""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from skiml_bot.adapters.google_calendar import GoogleOAuthCalendar
from skiml_bot.adapters.notion import NotionWorkspaceSource
from skiml_bot.adapters.openai_text import OpenAITextAssistant
from skiml_bot.adapters.paper_agent import OpenAIPaperResearchAgent
from skiml_bot.adapters.scholarly import ArxivDiscovery, CompositeDiscovery, OpenAlexDiscovery
from skiml_bot.adapters.slack import SlackGateway
from skiml_bot.adapters.ssh_slurm import (
    SlurmCommandError,
    SSHConnectionError,
    SSHSlurmStatusSource,
)
from skiml_bot.config import Settings
from skiml_bot.discussions import DiscussionAssistant
from skiml_bot.knowledge import LabKnowledge
from skiml_bot.meetings import (
    MeetingCoordinator,
    MeetingProposal,
    MeetingRequest,
    is_meeting_request,
)
from skiml_bot.periodic_server_status import PeriodicServerStatusPublisher
from skiml_bot.research import (
    ResearchAssistant,
    SlackMessage,
    has_summary_request,
    is_paper_summary_request,
)
from skiml_bot.server_status import is_server_status_request

MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>")


def build_app(settings: Settings) -> tuple[App, PeriodicServerStatusPublisher | None]:
    app = App(token=settings.slack_bot_token)
    slack = SlackGateway(app.client)
    text_assistant = OpenAITextAssistant(settings.openai_api_key, settings.openai_model)
    paper_agent = OpenAIPaperResearchAgent(
        settings.openai_api_key,
        settings.openai_model,
        discovery=CompositeDiscovery((ArxivDiscovery(), OpenAlexDiscovery())),
    )
    research = ResearchAssistant(paper_agent, slack)
    discussions = DiscussionAssistant(slack, text_assistant, slack)
    knowledge: LabKnowledge | None = None
    if "knowledge" in settings.enabled_features:
        assert settings.notion_token is not None
        knowledge = LabKnowledge(
            NotionWorkspaceSource(settings.notion_token, settings.notion_root_page_ids),
            text_assistant,
        )

    meetings: MeetingCoordinator | None = None
    if "meetings" in settings.enabled_features:
        assert settings.google_oauth_token_file is not None
        meetings = MeetingCoordinator(
            GoogleOAuthCalendar.from_token_file(settings.google_oauth_token_file)
        )

    server_status: SSHSlurmStatusSource | None = None
    if "server_status" in settings.enabled_features:
        assert settings.slurm_ssh_target is not None
        server_status = SSHSlurmStatusSource(
            settings.slurm_ssh_target,
            identity_file=settings.slurm_ssh_identity_file,
            known_hosts_file=settings.slurm_ssh_known_hosts_file,
            timeout_seconds=settings.slurm_ssh_timeout_seconds,
        )

    periodic_status: PeriodicServerStatusPublisher | None = None
    if server_status is not None and settings.slurm_status_channel_id is not None:
        assert settings.slurm_status_start_at is not None
        periodic_status = PeriodicServerStatusPublisher(
            server_status,
            slack,
            channel_id=settings.slurm_status_channel_id,
            interval_seconds=settings.slurm_status_interval_seconds,
            start_at=settings.slurm_status_start_at,
        )

    @app.event("app_mention")
    def handle_mention(event: dict[str, Any], logger: Any) -> None:
        channel_id = str(event["channel"])
        request_ts = str(event["ts"])
        source_thread_ts = str(event["thread_ts"]) if event.get("thread_ts") is not None else None
        raw_text = str(event.get("text", ""))
        command = MENTION_PATTERN.sub("", raw_text).strip()
        try:
            if "쓰레드 요약" in command:
                if source_thread_ts is None:
                    slack.post(channel_id, request_ts, "요약할 쓰레드 안에서 요청해 주세요.")
                else:
                    discussions.summarize(channel_id, request_ts, source_thread_ts)
            elif "채널 요약" in command:
                discussions.summarize(channel_id, request_ts)
            elif is_meeting_request(raw_text):
                if meetings is None:
                    slack.post(
                        channel_id,
                        source_thread_ts or request_ts,
                        "Calendar 연동이 아직 활성화되지 않았습니다.",
                    )
                else:
                    _arrange_meeting(settings, slack, meetings, event, app)
            elif is_server_status_request(raw_text):
                reply_ts = source_thread_ts or request_ts
                if server_status is None:
                    slack.post(
                        channel_id,
                        reply_ts,
                        "연구실 서버 상태 조회가 아직 활성화되지 않았습니다.",
                    )
                else:
                    try:
                        status = server_status.fetch()
                    except SSHConnectionError:
                        logger.exception("Failed to connect to the Slurm master over SSH")
                        slack.post(
                            channel_id,
                            reply_ts,
                            "🔴 Slurm master에 SSH로 접속하지 못했습니다. "
                            "서버 주소, SSH 키와 known_hosts 설정을 확인해 주세요.",
                        )
                    except SlurmCommandError:
                        logger.exception("Failed to query Slurm node status")
                        slack.post(
                            channel_id,
                            reply_ts,
                            "🔴 SSH 접속 후 `sinfo` 조회에 실패했습니다. "
                            "Slurm 상태와 계정 권한을 확인해 주세요.",
                        )
                    else:
                        slack.post(channel_id, reply_ts, status.for_slack())
            elif is_paper_summary_request(raw_text):
                research.handle(
                    SlackMessage(
                        event_id=f"mention:{channel_id}:{request_ts}",
                        channel_id=channel_id,
                        ts=request_ts,
                        text=str(event.get("text", "")),
                        thread_ts=source_thread_ts,
                    )
                )
            elif has_summary_request(command):
                slack.post(
                    channel_id,
                    source_thread_ts or request_ts,
                    "요약할 URL이나 논문 제목을 함께 입력해 주세요. "
                    "예: `@bot 요약해줘 https://...` 또는 `@bot 논문 제목 summary`",
                )
            else:
                if knowledge is None:
                    slack.post(
                        channel_id,
                        source_thread_ts or request_ts,
                        "Notion Q&A가 아직 활성화되지 않았습니다.",
                    )
                    return
                question = re.sub(r"^(노션|notion)\s*", "", command, flags=re.IGNORECASE)
                if not question:
                    slack.post(
                        channel_id,
                        source_thread_ts or request_ts,
                        "질문을 함께 입력해 주세요. 예: `@bot GPU 서버 예약 규칙이 뭐야?`",
                    )
                    return
                answer = knowledge.answer(question)
                slack.post(channel_id, source_thread_ts or request_ts, answer.for_slack())
        except Exception:
            logger.exception("Failed to handle app mention")
            slack.post(
                channel_id,
                source_thread_ts or request_ts,
                "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            )

    @app.action(re.compile(r"^meeting_confirm_\d+$"))
    def confirm_meeting(ack: Any, action: dict[str, Any], respond: Any, logger: Any) -> None:
        ack()
        if meetings is None:
            respond(text="Calendar 연동이 아직 활성화되지 않았습니다.")
            return
        try:
            proposal_id, raw_index = str(action["value"]).split(":", 1)
            event_url = meetings.confirm(
                proposal_id,
                int(raw_index),
                title="연구팀 미팅",
            )
            respond(text=f"✅ 미팅 초대를 생성했습니다: <{event_url}|Google Calendar에서 보기>")
        except Exception:
            logger.exception("Failed to confirm meeting")
            respond(text="미팅 초대를 생성하지 못했습니다. 후보가 만료되었을 수 있습니다.")

    return app, periodic_status


def _arrange_meeting(
    settings: Settings,
    slack: SlackGateway,
    meetings: MeetingCoordinator,
    event: dict[str, Any],
    app: App,
) -> None:
    channel_id = str(event["channel"])
    organizer = slack.user_email(str(event["user"]))
    participants = slack.channel_member_emails(channel_id)
    now = datetime.now(ZoneInfo(settings.timezone))
    window_start = _ceil_to_half_hour(now)
    request = MeetingRequest(
        organizer=organizer,
        participants=participants,
        window_start=window_start,
        window_end=window_start + timedelta(days=7),
        duration_minutes=60,
        working_hour_start=10,
        working_hour_end=18,
    )
    proposal = meetings.arrange(request)
    thread_ts = str(event.get("thread_ts") or event["ts"])
    if not proposal.slots:
        slack.post(channel_id, thread_ts, "향후 7일의 업무시간에 공통으로 가능한 시간이 없습니다.")
        return
    app.client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text="가능한 미팅 시간을 선택해 주세요.",
        blocks=_meeting_blocks(proposal, settings.timezone),
    )


def _meeting_blocks(proposal: MeetingProposal, timezone_name: str) -> list[dict[str, Any]]:
    timezone = ZoneInfo(timezone_name)
    weekdays = ("월", "화", "수", "목", "금", "토", "일")
    options: list[str] = []
    buttons: list[dict[str, Any]] = []
    for index, slot in enumerate(proposal.slots):
        local_start = slot.start.astimezone(timezone)
        local_end = slot.end.astimezone(timezone)
        label = (
            f"{local_start:%m/%d}({weekdays[local_start.weekday()]}) "
            f"{local_start:%H:%M}–{local_end:%H:%M}"
        )
        options.append(f"{index + 1}. {label}")
        buttons.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": f"{index + 1}번 확정"},
                "style": "primary",
                "action_id": f"meeting_confirm_{index}",
                "value": f"{proposal.id}:{index}",
            }
        )
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*채널 멤버 모두 가능한 시간*\n" + "\n".join(options),
            },
        },
        {"type": "actions", "elements": buttons},
    ]


def _ceil_to_half_hour(value: datetime) -> datetime:
    rounded = value.replace(second=0, microsecond=0)
    remainder = rounded.minute % 30
    if remainder:
        rounded += timedelta(minutes=30 - remainder)
    elif value.second or value.microsecond:
        rounded += timedelta(minutes=30)
    return rounded


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    app, periodic_status = build_app(settings)
    stop = threading.Event()
    status_thread: threading.Thread | None = None
    if periodic_status is not None:
        status_thread = threading.Thread(
            target=periodic_status.run,
            args=(stop,),
            name="periodic-server-status",
            daemon=True,
        )
        status_thread.start()
    try:
        SocketModeHandler(app, settings.slack_app_token).start()  # type: ignore[no-untyped-call]
    finally:
        stop.set()
        if status_thread is not None:
            status_thread.join(timeout=5)


if __name__ == "__main__":
    main()
