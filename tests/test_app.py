from datetime import datetime, timezone

from skiml_bot.app import _meeting_blocks
from skiml_bot.meetings import MeetingProposal, TimeSlot


def test_meeting_candidate_buttons_have_unique_action_ids() -> None:
    proposal = MeetingProposal(
        id="proposal-1",
        slots=tuple(
            TimeSlot(
                start=datetime(2026, 9, 2, hour, tzinfo=timezone.utc),
                end=datetime(2026, 9, 2, hour + 1, tzinfo=timezone.utc),
            )
            for hour in (1, 2, 3)
        ),
    )

    blocks = _meeting_blocks(proposal, "Asia/Seoul")
    action_ids = [element["action_id"] for element in blocks[1]["elements"]]

    assert len(action_ids) == len(set(action_ids))
