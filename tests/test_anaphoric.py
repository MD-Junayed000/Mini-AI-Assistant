"""Anaphoric / coreference resolution helpers in chat.py."""
from __future__ import annotations

from backend.pipeline.chat import (
    _build_retrieval_query,
    _extract_person_antecedent,
    _is_anaphoric_followup,
    _substitute_pronouns,
)


def test_short_pronoun_followup_is_anaphoric():
    assert _is_anaphoric_followup("where he lives") is True
    assert _is_anaphoric_followup("what are his publications") is True
    assert _is_anaphoric_followup("where does he live") is True
    assert _is_anaphoric_followup("is she still working on it?") is True


def test_greetings_and_long_messages_are_not_anaphoric():
    assert _is_anaphoric_followup("hello") is False
    assert _is_anaphoric_followup("thanks") is False
    assert (
        _is_anaphoric_followup(
            "I want a complete rundown of his publications, including preprints, "
            "datasets, and any accompanying code releases."
        )
        is False
    )
    assert _is_anaphoric_followup("what is the weather in Chattogram") is False


def test_extract_antecedent_prefers_assistant_turn():
    history = [
        {"role": "user", "content": "tell me about someone"},
        {
            "role": "assistant",
            "content": "Muhammad Junayed is a researcher from CUET in Chattogram.",
        },
    ]
    assert _extract_person_antecedent(history) == "Muhammad Junayed"


def test_extract_antecedent_falls_back_to_user_turn():
    history = [
        {"role": "user", "content": "who is Anne-Marie Curie"},
        {"role": "assistant", "content": "I don't know based on the available information."},
    ]
    assert _extract_person_antecedent(history) == "Anne-Marie Curie"


def test_substitute_pronouns_he():
    out = _substitute_pronouns("where he lives", "Junayed")
    assert "Junayed" in out and "he" not in out.split()


def test_build_retrieval_query_for_anaphoric():
    history = [
        {"role": "user", "content": "who is junayed"},
        {
            "role": "assistant",
            "content": "Muhammad Junayed is a researcher from CUET in Chattogram.",
        },
    ]
    q = _build_retrieval_query("where he lives", history, is_anaphoric=True)
    assert "Muhammad Junayed" in q
    assert "he" not in q.split()


def test_build_retrieval_query_non_anaphoric_passthrough():
    history = [
        {"role": "assistant", "content": "Junayed is in Chattogram."},
    ]
    q = _build_retrieval_query("what is the weather", history, is_anaphoric=False)
    assert q == "what is the weather"


def test_build_retrieval_query_no_antecedent_passthrough():
    history = [{"role": "assistant", "content": "Sure thing."}]
    q = _build_retrieval_query("where he lives", history, is_anaphoric=True)
    assert q == "where he lives"
