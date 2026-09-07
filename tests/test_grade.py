"""Unit tests for officeqa bench grading and observability metrics."""

import json
from pathlib import Path

from officeqa.bench.grade import (
    _parse_verdict,
    _summarize,
    generate_markdown_report,
)


def test_parse_verdict_correct():
    raw_json = json.dumps({
        "correctness": "correct",
        "numeric_match": True,
        "groundedness": "grounded",
        "error_category": None,
        "rationale": "The answer matches the gold value 273.28 exactly.",
    })
    verdict = _parse_verdict(raw_json)
    assert verdict.correctness == "correct"
    assert verdict.numeric_match is True
    assert verdict.groundedness == "grounded"
    assert verdict.error_category is None


def test_parse_verdict_visual_chart_error():
    raw_json = json.dumps({
        "correctness": "incorrect",
        "numeric_match": False,
        "groundedness": "ungrounded",
        "error_category": "missing_ocr_or_visual_chart",
        "rationale": "Question asks for local maxima on page 5 line plots, but plots are not present in OCR transcript.",
    })
    verdict = _parse_verdict(raw_json)
    assert verdict.correctness == "incorrect"
    assert verdict.error_category == "missing_ocr_or_visual_chart"


def test_parse_verdict_calculation_error():
    raw_json = json.dumps({
        "correctness": "incorrect",
        "numeric_match": False,
        "groundedness": "grounded",
        "error_category": "calculation_or_math_error",
        "rationale": "The agent extracted the right numbers from Table FFO-3 but computed CAGR as 5.2% instead of 7.8%.",
    })
    verdict = _parse_verdict(raw_json)
    assert verdict.correctness == "incorrect"
    assert verdict.error_category == "calculation_or_math_error"


def test_parse_verdict_retrieval_error():
    raw_json = json.dumps({
        "correctness": "incorrect",
        "numeric_match": False,
        "groundedness": "ungrounded",
        "error_category": "retrieval_or_lookup_error",
        "rationale": "The agent looked at Table 1 instead of Table 2 for Internal Revenue collections.",
    })
    verdict = _parse_verdict(raw_json)
    assert verdict.correctness == "incorrect"
    assert verdict.error_category == "retrieval_or_lookup_error"


def test_parse_verdict_halted_error():
    raw_json = json.dumps({
        "correctness": "incorrect",
        "numeric_match": None,
        "groundedness": "ungrounded",
        "error_category": "halted_or_empty_response",
        "rationale": "The agent timed out and did not emit a substantive final answer.",
    })
    verdict = _parse_verdict(raw_json)
    assert verdict.correctness == "incorrect"
    assert verdict.error_category == "halted_or_empty_response"


def test_parse_verdict_guardrail_resets_error_category():
    # If numeric match is true and rationale affirms exact match, verdict becomes correct and error_category is None
    raw_json = json.dumps({
        "correctness": "incorrect",
        "numeric_match": True,
        "groundedness": "partial",
        "error_category": "calculation_or_math_error",
        "rationale": "The agent answer exactly matches the gold number 264.632.",
    })
    verdict = _parse_verdict(raw_json)
    assert verdict.correctness == "correct"
    assert verdict.error_category is None


def test_summarize_with_ocr_adjustment():
    scores = [
        {
            "officeqa_id": "UID0001",
            "correctness": "correct",
            "numeric_match": True,
            "groundedness": "grounded",
            "error_category": None,
            "n_tool_calls": 3,
            "input_tokens": 1000,
            "output_tokens": 200,
        },
        {
            "officeqa_id": "UID0002",
            "correctness": "correct",
            "numeric_match": True,
            "groundedness": "grounded",
            "error_category": None,
            "n_tool_calls": 2,
            "input_tokens": 800,
            "output_tokens": 150,
        },
        {
            "officeqa_id": "UID0030",  # Visual chart question
            "correctness": "incorrect",
            "numeric_match": False,
            "groundedness": "ungrounded",
            "error_category": "missing_ocr_or_visual_chart",
            "n_tool_calls": 1,
            "input_tokens": 500,
            "output_tokens": 50,
        },
        {
            "officeqa_id": "UID0004",
            "correctness": "incorrect",
            "numeric_match": False,
            "groundedness": "grounded",
            "error_category": "calculation_or_math_error",
            "n_tool_calls": 4,
            "input_tokens": 1200,
            "output_tokens": 300,
        },
    ]

    summary = _summarize(scores)
    assert summary["n"] == 4
    assert summary["correct"] == 2
    assert summary["incorrect"] == 2
    assert summary["accuracy_correct"] == 0.5
    # OCR-adjusted accuracy (excluding UID0030: 2 correct out of 3 questions)
    assert summary["ocr_errors"] == 1
    assert summary["ocr_adjusted_n"] == 3
    assert summary["ocr_adjusted_accuracy_correct"] == 0.667
    assert summary["error_breakdown"]["missing_ocr_or_visual_chart"] == 1
    assert summary["error_breakdown"]["calculation_or_math_error"] == 1
    assert summary["error_breakdown"]["retrieval_or_lookup_error"] == 0


def test_generate_markdown_report(tmp_path: Path):
    scores = [
        {
            "financebench_id": "UID0001",
            "doc_name": "treasury_1980",
            "question": "What was total outlay?",
            "gold_answer": "100",
            "agent_answer": "100",
            "correctness": "correct",
            "numeric_match": True,
            "groundedness": "grounded",
            "error_category": None,
            "rationale": "Exact match",
            "n_tool_calls": 2,
            "input_tokens": 1000,
            "output_tokens": 100,
        },
        {
            "financebench_id": "UID0030",
            "doc_name": "treasury_1990",
            "question": "How many local maxima in line plot?",
            "gold_answer": "18",
            "agent_answer": "Cannot see image",
            "correctness": "incorrect",
            "numeric_match": False,
            "groundedness": "ungrounded",
            "error_category": "missing_ocr_or_visual_chart",
            "rationale": "Line plot missing in OCR",
            "n_tool_calls": 1,
            "input_tokens": 500,
            "output_tokens": 50,
        },
    ]
    summary = _summarize(scores)
    out_file = tmp_path / "test_report.md"
    generate_markdown_report(scores, summary, report_path=out_file)

    content = out_file.read_text(encoding="utf-8")
    assert "OCR-Adjusted Exact Correct" in content
    assert "## Error Category Breakdown" in content
    assert "`missing_ocr_or_visual_chart`" in content


if __name__ == "__main__":
    import tempfile

    test_parse_verdict_correct()
    test_parse_verdict_visual_chart_error()
    test_parse_verdict_calculation_error()
    test_parse_verdict_retrieval_error()
    test_parse_verdict_halted_error()
    test_parse_verdict_guardrail_resets_error_category()
    test_summarize_with_ocr_adjustment()
    with tempfile.TemporaryDirectory() as td:
        test_generate_markdown_report(Path(td))
    print("All officeqa grade unit tests passed!")

