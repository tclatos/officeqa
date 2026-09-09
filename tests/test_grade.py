"""Unit tests for officeqa bench grading and summary parsing."""

import json

from genai_graph.bench.judge import _parse_judge_json
from genai_graph.bench.models import JudgeVerdict
from genai_graph.bench.summary import compute_bench_summary


def test_parse_verdict_correct():
    raw_json = json.dumps(
        {
            "correctness": "correct",
            "numeric_match": True,
            "groundedness": "grounded",
            "error_category": None,
            "rationale": "The answer matches the gold value 273.28 exactly.",
        }
    )
    data = _parse_judge_json(raw_json)
    verdict = JudgeVerdict.model_validate(data)
    assert verdict.correctness == "correct"
    assert verdict.numeric_match is True
    assert verdict.groundedness == "grounded"
    assert verdict.error_category is None


def test_parse_verdict_visual_chart_error():
    raw_json = json.dumps(
        {
            "correctness": "incorrect",
            "numeric_match": False,
            "groundedness": "ungrounded",
            "error_category": "missing_ocr_or_visual_chart",
            "rationale": "Question asks for local maxima on page 5 line plots, but plots are not present in OCR transcript.",
        }
    )
    data = _parse_judge_json(raw_json)
    verdict = JudgeVerdict.model_validate(data)
    assert verdict.correctness == "incorrect"
    assert verdict.error_category == "missing_ocr_or_visual_chart"


def test_parse_verdict_calculation_error():
    raw_json = json.dumps(
        {
            "correctness": "incorrect",
            "numeric_match": False,
            "groundedness": "grounded",
            "error_category": "calculation_or_math_error",
            "rationale": "The agent extracted the right numbers from Table FFO-3 but computed CAGR as 5.2% instead of 7.8%.",
        }
    )
    data = _parse_judge_json(raw_json)
    verdict = JudgeVerdict.model_validate(data)
    assert verdict.correctness == "incorrect"
    assert verdict.error_category == "calculation_or_math_error"


def test_parse_verdict_retrieval_error():
    raw_json = json.dumps(
        {
            "correctness": "incorrect",
            "numeric_match": False,
            "groundedness": "ungrounded",
            "error_category": "retrieval_or_lookup_error",
            "rationale": "The agent looked at Table 1 instead of Table 2 for Internal Revenue collections.",
        }
    )
    data = _parse_judge_json(raw_json)
    verdict = JudgeVerdict.model_validate(data)
    assert verdict.correctness == "incorrect"
    assert verdict.error_category == "retrieval_or_lookup_error"


def test_parse_verdict_halted_error():
    raw_json = json.dumps(
        {
            "correctness": "incorrect",
            "numeric_match": None,
            "groundedness": "ungrounded",
            "error_category": "halted_or_empty_response",
            "rationale": "The agent timed out and did not emit a substantive final answer.",
        }
    )
    data = _parse_judge_json(raw_json)
    verdict = JudgeVerdict.model_validate(data)
    assert verdict.correctness == "incorrect"
    assert verdict.error_category == "halted_or_empty_response"


def test_summarize_with_ocr_adjustment():
    scores = [
        {
            "id": "UID0001",
            "correctness": "correct",
            "numeric_match": True,
            "groundedness": "grounded",
            "error_category": None,
            "n_tool_calls": 3,
            "input_tokens": 1000,
            "output_tokens": 200,
        },
        {
            "id": "UID0002",
            "correctness": "correct",
            "numeric_match": True,
            "groundedness": "grounded",
            "error_category": None,
            "n_tool_calls": 2,
            "input_tokens": 800,
            "output_tokens": 150,
        },
        {
            "id": "UID0030",  # Visual chart question
            "correctness": "incorrect",
            "numeric_match": False,
            "groundedness": "ungrounded",
            "error_category": "missing_ocr_or_visual_chart",
            "n_tool_calls": 1,
            "input_tokens": 500,
            "output_tokens": 50,
        },
        {
            "id": "UID0004",
            "correctness": "incorrect",
            "numeric_match": False,
            "groundedness": "grounded",
            "error_category": "calculation_or_math_error",
            "n_tool_calls": 4,
            "input_tokens": 1200,
            "output_tokens": 300,
        },
    ]

    summary = compute_bench_summary(scores, profile_name="test_profile")
    assert summary.total_questions == 4
    assert summary.correct == 2
    assert summary.incorrect == 2
    assert summary.accuracy == 0.5
    # OCR-adjusted accuracy (excluding UID0030: 2 correct out of 3 questions)
    assert summary.ocr_errors == 1
    assert summary.ocr_adjusted_n == 3
    assert summary.ocr_adjusted_accuracy == 0.6667
    assert summary.error_breakdown["missing_ocr_or_visual_chart"] == 1
    assert summary.error_breakdown["calculation_or_math_error"] == 1
    assert summary.error_breakdown.get("retrieval_or_lookup_error", 0) == 0


if __name__ == "__main__":
    test_parse_verdict_correct()
    test_parse_verdict_visual_chart_error()
    test_parse_verdict_calculation_error()
    test_parse_verdict_retrieval_error()
    test_parse_verdict_halted_error()
    test_summarize_with_ocr_adjustment()
    print("All officeqa grade unit tests passed!")
