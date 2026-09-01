from dataclasses import dataclass

from skiml_bot.knowledge import KnowledgeDocument, LabKnowledge


@dataclass
class FakeKnowledgeSource:
    def search(self, question: str) -> tuple[KnowledgeDocument, ...]:
        assert question == "GPU 서버 예약 규칙이 뭐야?"
        return (
            KnowledgeDocument(
                title="GPU 서버 이용 안내",
                url="https://notion.so/lab/gpu-guide",
                content="GPU는 작업 시작 전에 예약 채널에서 노드와 시간을 예약한다.",
            ),
        )


@dataclass
class FakeAnswerGenerator:
    def answer(self, question: str, documents: tuple[KnowledgeDocument, ...]) -> str:
        assert documents[0].title == "GPU 서버 이용 안내"
        return "작업 전에 예약 채널에서 사용할 노드와 시간을 예약해야 합니다."


def test_notion_answer_always_includes_the_supporting_page() -> None:
    knowledge = LabKnowledge(FakeKnowledgeSource(), FakeAnswerGenerator())

    answer = knowledge.answer("GPU 서버 예약 규칙이 뭐야?")

    assert answer.text == "작업 전에 예약 채널에서 사용할 노드와 시간을 예약해야 합니다."
    assert answer.sources == (("GPU 서버 이용 안내", "https://notion.so/lab/gpu-guide"),)
    assert "https://notion.so/lab/gpu-guide" in answer.for_slack()
