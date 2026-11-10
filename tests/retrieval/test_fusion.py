from __future__ import annotations

import uuid

from firebrief.retrieval.search import fuse

A = uuid.uuid4()
B = uuid.uuid4()
C = uuid.uuid4()


def test_a_chunk_found_by_both_sides_beats_one_found_by_either() -> None:
    scores = fuse([A, B], [A, C], k=60)

    assert scores[A] > scores[B]
    assert scores[A] > scores[C]


def test_rank_matters() -> None:
    scores = fuse([A, B], [], k=60)

    assert scores[A] > scores[B]


def test_a_chunk_absent_from_both_sides_scores_nothing() -> None:
    scores = fuse([A], [B], k=60)

    assert C not in scores


def test_fusion_is_deterministic() -> None:
    assert fuse([A, B], [B, A]) == fuse([A, B], [B, A])


def test_fusion_of_nothing_is_nothing() -> None:
    assert fuse([], []) == {}


def test_the_score_is_one_over_k_plus_rank() -> None:
    assert fuse([A], [A], k=60) == {A: 2 / 61}
    assert fuse([A], [], k=60) == {A: 1 / 61}


def test_ties_are_broken_by_chunk_id() -> None:
    from firebrief.retrieval.search import order

    low, high = sorted([A, B], key=str)
    scores = {high: 0.5, low: 0.5}

    assert order(scores) == [low, high]
