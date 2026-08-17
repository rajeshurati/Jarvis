"""Natural spoken-turn policy tests."""

from jarvis.application.conversation_policy import ConversationPolicy


def test_interruption_prefix_changes_to_latest_intent() -> None:
    intent, changed = ConversationPolicy().latest_intent("Stop talking, what time is it instead?")
    assert changed
    assert intent == "what time is it instead?"


def test_normal_turn_is_preserved() -> None:
    intent, changed = ConversationPolicy().latest_intent("What time is it?")
    assert not changed
    assert intent == "What time is it?"


def test_explicit_new_topic_clears_old_context() -> None:
    intent, changed = ConversationPolicy().latest_intent(
        "New topic: open the calculator"
    )
    assert changed
    assert intent == "open the calculator"


def test_stop_capability_command_is_not_mistaken_for_barge_in() -> None:
    intent, changed = ConversationPolicy().latest_intent("stop room monitoring")
    assert not changed
    assert intent == "stop room monitoring"


def test_markdown_filler_and_long_reply_are_bounded() -> None:
    response = ConversationPolicy(max_words=12).spoken_reply(
        "Understood, Rajesh. **System State**: active. "
        "- First detail about old context that should never keep going forever. "
        "- Second unrelated historical detail."
    )
    assert "**" not in response
    assert "Understood" not in response
    assert len(response.split()) <= 12


def test_empty_model_reply_has_safe_fallback() -> None:
    assert "useful answer" in ConversationPolicy().spoken_reply(" ## ")


def test_model_speaker_label_is_not_read_aloud() -> None:
    assert ConversationPolicy().spoken_reply("Jarvis: I am ready.") == "I am ready."


def test_tiny_trailing_fragment_is_not_read_aloud() -> None:
    response = ConversationPolicy().spoken_reply(
        "The current screen shows the Jarvis control panel. The main."
    )
    assert response == "The current screen shows the Jarvis control panel."


def test_second_sentence_is_dropped_instead_of_cut_mid_sentence() -> None:
    response = ConversationPolicy(max_words=8).spoken_reply(
        "This first sentence is complete. This second sentence is much too long to include."
    )
    assert response == "This first sentence is complete."


def test_long_first_sentence_does_not_end_on_a_connector() -> None:
    response = ConversationPolicy(max_words=8).spoken_reply(
        "The screen shows a browser with ChatGPT and several other applications open."
    )
    assert response == "The screen shows a browser with ChatGPT."


def test_long_first_sentence_prefers_a_complete_comma_clause() -> None:
    response = ConversationPolicy(max_words=14).spoken_reply(
        "The screen shows ChatGPT with the Jarvis project open, alongside many other tabs "
        "that are not relevant to the request."
    )
    assert response == "The screen shows ChatGPT with the Jarvis project open."


def test_incomplete_question_requests_the_rest_without_calling_a_model() -> None:
    policy = ConversationPolicy()
    assert policy.clarification_for("What is?") == "Please finish your question. I am listening."
    assert policy.clarification_for("What is on my screen?") is None
