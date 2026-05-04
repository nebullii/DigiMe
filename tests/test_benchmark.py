from pathlib import Path

from digime.benchmark.replay import classify_behavior, load_replay_cases, run_replay_benchmark
from digime.agent.conversation import analyze_conversation


def test_load_replay_cases_reads_benchmark_file() -> None:
    cases = load_replay_cases(Path("benchmarks/replay_cases.json"))

    assert len(cases) >= 5
    assert cases[0].name == "direct_greeting"


def test_run_replay_benchmark_passes_starter_corpus() -> None:
    cases = load_replay_cases(Path("benchmarks/replay_cases.json"))
    results = run_replay_benchmark(cases, timezone_name="America/New_York")

    assert results
    assert all(result.passed for result in results)


def test_classify_behavior_returns_meeting_clarify_for_partial_request() -> None:
    cases = load_replay_cases(Path("benchmarks/replay_cases.json"))
    case = next(item for item in cases if item.name == "meeting_request_missing_time")
    state = analyze_conversation(
        case.turns,
        latest_message_id=case.latest_message_id,
        bot_names={"DigiMe"},
    )

    assert classify_behavior(case, state, timezone_name="America/New_York") == "meeting_clarify"
