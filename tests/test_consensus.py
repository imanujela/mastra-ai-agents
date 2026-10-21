"""Independent workers disagree; consensus turns that into one answer plus the dissent."""

from mastra_ai_agents.consensus import merge, rank, vote


def test_identical_texts_agree_completely():
    result = vote([{"text": "Oslo"}, {"text": "Oslo"}])

    assert result["winner"] == "Oslo"
    assert result["support"] == 2
    assert result["agreement"] == 1.0
    assert result["dissent"] == []


def test_majority_wins_and_minority_is_kept_as_dissent():
    result = vote([{"text": "short"}, {"text": "short"}, {"text": "long"}])

    assert result["winner"] == "short"
    assert result["support"] == 2
    assert result["dissent"] == ["long"]
    assert result["agreement"] == 0.6667


def test_case_and_whitespace_do_not_split_a_vote():
    result = vote([{"text": "  Short "}, {"text": "short"}])

    assert result["winner"] == "Short"
    assert result["support"] == 2
    assert result["agreement"] == 1.0


def test_a_tie_goes_to_the_first_result_seen():
    result = vote([{"text": "a"}, {"text": "b"}])

    assert result["winner"] == "a"
    assert result["agreement"] == 0.5
    assert result["dissent"] == ["b"]


def test_empty_input_is_named_rather_than_guessed():
    assert vote([]) == {"winner": None, "support": 0, "agreement": 0.0, "dissent": []}


def test_rank_orders_by_score_and_keeps_input_order_on_ties():
    ranked = rank([{"id": "a", "score": 0.5}, {"id": "b", "score": 0.9}, {"id": "c", "score": 0.5}])

    assert [item["id"] for item in ranked] == ["b", "a", "c"]


def test_rank_treats_a_missing_score_as_zero():
    ranked = rank([{"id": "a"}, {"id": "b", "score": 0.1}])

    assert [item["id"] for item in ranked] == ["b", "a"]


def test_merge_best_returns_the_winning_result_whole():
    best = merge([{"text": "a", "score": 0.2}, {"text": "b", "score": 0.8}], strategy="best")

    assert best["text"] == "b"
    assert best["score"] == 0.8
