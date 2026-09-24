import itertools

from epilocate_review_server.app.review_logic import consensus_status, recommend_diag, recommend_tie


def test_all_256_tie_observation_combinations_follow_frozen_rule():
    keys = ("texture", "noise", "artifact", "coverage")
    for values in itertools.product(("A", "B", "SAME", "UNSURE"), repeat=4):
        observations = dict(zip(keys, values))
        result = recommend_tie(observations)
        a_count = values.count("A")
        b_count = values.count("B")
        if a_count >= 2 and b_count == 0:
            assert (result.decision, result.selected_position) == ("SELECT_ONE_CANDIDATE", "A")
        elif b_count >= 2 and a_count == 0:
            assert (result.decision, result.selected_position) == ("SELECT_ONE_CANDIDATE", "B")
        else:
            assert (result.decision, result.selected_position) == ("DEFER", None)


def test_all_27_diag_observation_combinations_follow_frozen_rule():
    keys = ("diag_coverage", "diag_artifact", "diag_use")
    for values in itertools.product(("YES", "NO", "UNSURE"), repeat=3):
        result = recommend_diag(dict(zip(keys, values)))
        if values == ("YES", "YES", "YES"):
            assert result.decision == "INCLUDE_REVIEW_SERIES"
        elif "NO" in values:
            assert result.decision == "EXCLUDE_PATIENT"
        else:
            assert result.decision == "DEFER"


def test_consensus_compares_real_uid_and_never_auto_finalizes():
    base = {"status": "SUBMITTED", "decision": "SELECT_ONE_CANDIDATE"}
    result = consensus_status(
        [
            {**base, "selected_series_uid": "uid-1"},
            {**base, "selected_series_uid": "uid-1"},
        ]
    )
    assert result == {
        "status": "CONSENSUS",
        "has_defer": False,
        "decision": "SELECT_ONE_CANDIDATE",
        "selected_series_uid": "uid-1",
    }
    assert "final" not in result
    assert consensus_status([{**base, "selected_series_uid": "uid-1"}])["status"] == "WAITING"
    assert consensus_status(
        [{**base, "selected_series_uid": "uid-1"}, {**base, "selected_series_uid": "uid-2"}]
    )["status"] == "CONFLICT"
