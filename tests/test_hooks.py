from hooks import *


def test_generate_recommended_questions_real_call() -> None:
    hook = LoopEndRecommendQuestionsHook()
    recent_pairs = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮你的吗？"},
    ]

    questions = hook._generate_recommended_questions(recent_pairs)
    print(f"\nreal generated questions: {questions}")

    assert isinstance(questions, list)
    assert len(questions) == 3
