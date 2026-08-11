"""Deterministic OVOScope coverage for the complete Sonos voice surface.

The real intent service, skill loader, resource files, and handler lifecycle run
inside MiniCroft. A recording controller replaces SoCo before construction, so
these tests verify intent side effects without discovering or changing speakers.
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_spec_tools.expansion import expand
from ovoscope import (
    PADACIOSO_PIPELINE,
    PADATIOUS_PIPELINE,
    CaptureSession,
    get_minicroft,
)

from skill_sonos_controller import SonosControllerSkill
from skill_sonos_controller.constants import (
    DEFAULT_SOURCE,
    DEFAULT_VOLUME_STEP,
    LARGE_VOLUME_STEP,
    SUPPORTED_LOCALES,
)
from skill_sonos_controller.controller import PlaybackResult

SKILL_ID = "skill-sonos-controller.smartgic"
RESOURCE_ROOT = Path(__file__).parents[2] / "skill_sonos_controller" / "locale"
HANDLER_EOF_MESSAGES = [
    "mycroft.skill.handler.complete",
    "mycroft.skill.handler.error",
]
M2V_PROTOTYPE_PIPELINE = [
    "ovos-m2v-prototype-pipeline-high",
    "ovos-m2v-prototype-pipeline-medium",
    "ovos-m2v-prototype-pipeline-low",
]

SLOT_VALUES = {
    "album": "Thriller",
    "artist": "Michael Jackson",
    "group_speaker": "Kitchen",
    "playlist": "Road Trip",
    "podcast": "The Daily",
    "service": "Spotify",
    "speaker": "Office",
    "station": "CBC Radio One",
    "track": "Imagine",
    "volume": "12",
}

# ``detailed`` is a free-form slot rather than an entity resource, so each test
# locale needs a representative localized value.
DETAILED_VALUES = {
    "ca-es": "detallada",
    "da-dk": "detaljerede",
    "de-de": "detaillierte",
    "en-us": "detailed",
    "es-es": "detallada",
    "eu-es": "zehatza",
    "fa-ir": "کامل",
    "fr-fr": "détaillées",
    "gl-es": "detallada",
    "it-it": "dettagliate",
    "nl-be": "gedetailleerde",
    "nl-nl": "gedetailleerde",
    "pl-pl": "szczegółowe",
    "pt-br": "detalhadas",
    "pt-pt": "detalhadas",
    "uk-ua": "докладну",
}


class OfflineSpeaker:
    """Small player double for successful informational handlers."""

    player_name = "Office"
    volume = 12

    @staticmethod
    def get_current_track_info() -> dict[str, str]:
        return {"title": "Imagine", "artist": "John Lennon"}

    @staticmethod
    def get_speaker_info() -> dict[str, str]:
        return {
            "model_name": "Sonos:Test",
            "model_number": "S00",
            "display_version": "1.0",
            "uid": "RINCON_TEST",
            "serial_number": "00-00-00-00-00-00",
            "software_version": "1.0",
            "hardware_version": "1.0",
            "mac_address": "00:00:00:00:00:00",
        }


class OfflineSonosController:
    """Record the voice layer's successful calls without touching the LAN."""

    calls: ClassVar[list[tuple[str, tuple[Any, ...], dict[str, Any]]]] = []

    def __init__(self) -> None:
        self.speakers = (OfflineSpeaker(),)
        self.registry = SimpleNamespace(
            household_services=(SimpleNamespace(name="Music Library"),)
        )

    @classmethod
    def reset(cls) -> None:
        cls.calls.clear()

    @classmethod
    def record(cls, name: str, *args: Any, **kwargs: Any) -> None:
        cls.calls.append((name, args, kwargs))

    def refresh(self) -> tuple[OfflineSpeaker, ...]:
        self.record("refresh")
        return self.speakers

    def begin_authentication(self, service: str):
        self.record("begin_authentication", service)
        provider = SimpleNamespace(
            link_code="",
            link_device_id=None,
            service_name=service,
        )
        return provider, ""

    def complete_authentication(
        self, service: str, code: str, device_id: str | None
    ) -> None:
        self.record("complete_authentication", service, code, device_id)

    def change_volume(self, delta: int, speaker: str | None = None) -> int:
        self.record("change_volume", delta, speaker)
        return 1

    def coordinators(self, state: str | None = None) -> tuple[OfflineSpeaker, ...]:
        self.record("coordinators", state)
        return self.speakers

    def duck(self, amount: int) -> None:
        self.record("duck", amount)

    def group_all(self, coordinator: str) -> int:
        self.record("group_all", coordinator)
        return 1

    def group_speakers(self, coordinator: str, members) -> int:
        self.record("group_speakers", coordinator, tuple(members))
        return 1

    def resolve_speaker(
        self, speaker: str | None, coordinator: bool = True
    ) -> OfflineSpeaker:
        self.record("resolve_speaker", speaker, coordinator)
        return self.speakers[0]

    def run_command(self, **kwargs: Any) -> int:
        self.record("run_command", **kwargs)
        return 1

    def search_and_play(self, **kwargs: Any) -> PlaybackResult:
        self.record("search_and_play", **kwargs)
        return PlaybackResult(
            title=str(kwargs["query"]),
            service=str(kwargs["service_name"]),
            speaker=str(kwargs["speaker_name"] or "Office"),
            category=str(kwargs["category"]),
            artist=kwargs.get("artist"),
        )

    def set_home_theater_option(self, option: str, enabled: bool, speaker: str) -> int:
        self.record("set_home_theater_option", option, enabled, speaker)
        return 1

    def set_mute(self, muted: bool, speaker: str | None = None) -> int:
        self.record("set_mute", muted, speaker)
        return 1

    def set_playback_option(
        self, option: str, enabled: bool, speaker: str | None = None
    ) -> int:
        self.record("set_playback_option", option, enabled, speaker)
        return 1

    def set_volume(self, level: int, speaker: str | None = None) -> int:
        self.record("set_volume", level, speaker)
        return 1

    def switch_to_tv(self, speaker: str) -> int:
        self.record("switch_to_tv", speaker)
        return 1

    def transport_state(self, _device: OfflineSpeaker) -> str:
        self.record("transport_state")
        return "PLAYING"

    def ungroup_speaker(self, speaker: str) -> int:
        self.record("ungroup_speaker", speaker)
        return 1

    def unduck(self) -> None:
        self.record("unduck")


EXPECTED_CONTROLLER_CALL = {
    "sonos.album.intent": "search_and_play",
    "sonos.artist.intent": "search_and_play",
    "sonos.authenticate.intent": "begin_authentication",
    "sonos.discovery.intent": "refresh",
    "sonos.group.all.intent": "group_all",
    "sonos.group.intent": "group_speakers",
    "sonos.mute.intent": "set_mute",
    "sonos.next.music.intent": "run_command",
    "sonos.night.off.intent": "set_home_theater_option",
    "sonos.night.on.intent": "set_home_theater_option",
    "sonos.pause.music.intent": "run_command",
    "sonos.playlist.intent": "search_and_play",
    "sonos.podcast.intent": "search_and_play",
    "sonos.previous.music.intent": "run_command",
    "sonos.repeat.off.intent": "set_playback_option",
    "sonos.repeat.on.intent": "set_playback_option",
    "sonos.resume.music.intent": "run_command",
    "sonos.service.intent": None,
    "sonos.shuffle.off.intent": "set_playback_option",
    "sonos.shuffle.on.intent": "set_playback_option",
    "sonos.speaker.info.intent": "resolve_speaker",
    "sonos.speech.off.intent": "set_home_theater_option",
    "sonos.speech.on.intent": "set_home_theater_option",
    "sonos.station.intent": "search_and_play",
    "sonos.stop.music.intent": "run_command",
    "sonos.track.intent": "search_and_play",
    "sonos.tv.intent": "switch_to_tv",
    "sonos.ungroup.intent": "ungroup_speaker",
    "sonos.unmute.intent": "set_mute",
    "sonos.volume.down.intent": "change_volume",
    "sonos.volume.louder.intent": "change_volume",
    "sonos.volume.quieter.intent": "change_volume",
    "sonos.volume.set.intent": "set_volume",
    "sonos.volume.up.intent": "change_volume",
    "sonos.what.is.playing.intent": ("resolve_speaker", "coordinators"),
    "sonos.which.artist.intent": ("resolve_speaker", "coordinators"),
}


def language_tag(locale: str) -> str:
    """Convert a packaged lowercase locale to canonical BCP-47 casing."""
    language, territory = locale.split("-", maxsplit=1)
    return f"{language}-{territory.upper()}"


def decline_prompt(_skill: SonosControllerSkill, *_args: Any, **_kwargs: Any) -> str:
    """Answer optional list prompts without confusing OVOS method inspection."""
    return "no"


def generated_locale_cases(locale: str):
    """Generate one executable example from every localized template line."""
    intent_root = RESOURCE_ROOT / locale / "intents"
    values = {**SLOT_VALUES, "detailed": DETAILED_VALUES[locale]}
    cases = []
    for path in sorted(intent_root.glob("*.intent")):
        for line_number, raw_template in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            template = raw_template.strip()
            if not template:
                continue
            expansions = expand(template)
            assert expansions, f"{path}:{line_number} has no expansions"
            utterance = expansions[0].format_map(values)
            cases.append((utterance, path.name, line_number))
    return cases


assert set(DETAILED_VALUES) == set(SUPPORTED_LOCALES)
TEMPLATE_CASES = {
    language_tag(locale): generated_locale_cases(locale) for locale in SUPPORTED_LOCALES
}
INTENT_CASES = [
    pytest.param(
        lang,
        utterance,
        intent,
        id=f"{lang}-{intent}-line-{line_number}",
    )
    for lang, language_cases in TEMPLATE_CASES.items()
    for utterance, intent, line_number in language_cases
]


class LocalizedMiniCroft:
    """Keep exactly one language/pipeline MiniCroft alive at a time."""

    def __init__(self) -> None:
        self.lang: str | None = None
        self.pipeline: tuple[str, ...] | None = None
        self.runtime = None
        self.patches = []

    def get(self, lang: str, pipeline=PADACIOSO_PIPELINE):
        requested_pipeline = tuple(pipeline)
        if self.lang == lang and self.pipeline == requested_pipeline:
            return self.runtime
        self.stop()
        self.patches = [
            patch("skill_sonos_controller.SonosController", OfflineSonosController),
            patch.object(SonosControllerSkill, "ask_yesno", decline_prompt),
        ]
        for active_patch in self.patches:
            active_patch.start()
        try:
            self.runtime = get_minicroft(
                [SKILL_ID],
                default_pipeline=list(requested_pipeline),
                lang=lang,
                max_wait=240,
            )
        except Exception:
            self.stop()
            raise
        assert SKILL_ID in self.runtime.plugin_skills
        self.runtime.bus.emit(Message("mycroft.skills.train"))
        sleep(0.25)
        self.lang = lang
        self.pipeline = requested_pipeline
        return self.runtime

    def stop(self) -> None:
        if self.runtime is not None:
            self.runtime.stop()
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.lang = None
        self.pipeline = None
        self.runtime = None
        self.patches = []


def capture_handler(minicroft, source: Message, timeout: int = 30):
    """Capture until the asynchronous skill handler itself completes."""
    capture = CaptureSession(minicroft, eof_msgs=HANDLER_EOF_MESSAGES)
    try:
        completed = capture.capture(source, timeout=timeout)
    finally:
        messages = capture.finish()
    if completed is not None:
        assert completed, f"handler did not finish within {timeout} seconds"
    assert not getattr(capture, "timed_out", False)
    message_types = {message.msg_type for message in messages}
    assert "mycroft.skill.handler.complete" in message_types
    assert "mycroft.skill.handler.error" not in message_types
    return messages


def utterance_message(utterance: str, lang: str, pipeline, session_id: str) -> Message:
    """Build a pipeline-specific utterance message with an isolated session."""
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(pipeline)
    return Message(
        "recognizer_loop:utterance",
        {"utterances": [utterance], "lang": lang},
        {"session": session.serialize()},
    )


def assert_controller_effect(expected_intent: str) -> None:
    """Prove the routed handler reached its expected integration boundary."""
    expected = EXPECTED_CONTROLLER_CALL[expected_intent]
    if expected is None:
        return
    expected_calls = (expected,) if isinstance(expected, str) else expected
    actual_calls = [name for name, _args, _kwargs in OfflineSonosController.calls]
    assert any(call in actual_calls for call in expected_calls), (
        f"{expected_intent} did not call one of {expected_calls}: {actual_calls}"
    )


@pytest.fixture(scope="module")
def minicroft_factory():
    factory = LocalizedMiniCroft()
    try:
        yield factory
    finally:
        factory.stop()


@pytest.mark.parametrize(("lang", "utterance", "expected_intent"), INTENT_CASES)
def test_every_localized_template_routes_and_runs_its_handler(
    minicroft_factory, lang, utterance, expected_intent
):
    """Exercise every non-empty intent template, not just one per intent."""
    minicroft = minicroft_factory.get(lang)
    OfflineSonosController.reset()
    source = utterance_message(
        utterance,
        lang,
        PADACIOSO_PIPELINE,
        f"sonos-{lang}-{expected_intent}",
    )
    messages = capture_handler(minicroft, source)

    message_types = [message.msg_type for message in messages]
    intent_type = f"{SKILL_ID}:{expected_intent.removesuffix('.intent')}"
    assert intent_type in message_types
    assert "mycroft.skill.handler.start" in message_types
    assert_controller_effect(expected_intent)


def test_service_slot_accepts_runtime_advertised_names(minicroft_factory):
    """Provider slots remain open to names not shipped in service.entity."""
    lang = "en-US"
    utterance = "play song test from Community Radio Plus in office"
    minicroft = minicroft_factory.get(lang)
    OfflineSonosController.reset()
    source = utterance_message(
        utterance,
        lang,
        PADACIOSO_PIPELINE,
        "sonos-runtime-provider",
    )
    messages = capture_handler(minicroft, source)

    intent_type = f"{SKILL_ID}:sonos.track"
    matched = next(message for message in messages if message.msg_type == intent_type)
    assert matched.data["service"] == "community radio plus"
    search = next(
        kwargs
        for name, _args, kwargs in OfflineSonosController.calls
        if name == "search_and_play"
    )
    assert search["service_name"] == "community radio plus"


LEGACY_PIPELINE_CASES = [
    pytest.param(
        pipeline_name,
        pipeline,
        utterance,
        intent,
        id=f"{pipeline_name}-{intent}-line-{line_number}",
    )
    for pipeline_name, pipeline in (
        ("padatious", PADATIOUS_PIPELINE),
        ("m2v-prototype", M2V_PROTOTYPE_PIPELINE),
    )
    for utterance, intent, line_number in TEMPLATE_CASES["en-US"]
]


@pytest.mark.parametrize(
    ("pipeline_name", "pipeline", "utterance", "expected_intent"),
    LEGACY_PIPELINE_CASES,
)
def test_every_english_template_on_alternate_pipelines(
    minicroft_factory, pipeline_name, pipeline, utterance, expected_intent
):
    """Route every English template through Padatious and model2vec."""
    minicroft = minicroft_factory.get("en-US", pipeline)
    OfflineSonosController.reset()
    source = utterance_message(
        utterance,
        "en-US",
        pipeline,
        f"sonos-{pipeline_name}-{expected_intent}",
    )
    messages = capture_handler(minicroft, source)

    message_types = [message.msg_type for message in messages]
    intent_types = {
        f"{SKILL_ID}:{expected_intent}",
        f"{SKILL_ID}:{expected_intent.removesuffix('.intent')}",
    }
    if pipeline_name == "m2v-prototype" and intent_types.isdisjoint(message_types):
        reroute = next(
            message
            for message in messages
            if message.msg_type == "sonos.classifier.rerouted"
        )
        assert reroute.data["to"] == expected_intent
    else:
        assert not intent_types.isdisjoint(message_types)
    assert_controller_effect(expected_intent)


def test_m2v_classifier_hydrates_freeform_entities(minicroft_factory):
    """Prove model2vec classification reaches playback with usable slots."""
    pipeline = M2V_PROTOTYPE_PIPELINE
    minicroft = minicroft_factory.get("en-US", pipeline)
    OfflineSonosController.reset()
    source = utterance_message(
        "play song imagine by john lennon from Spotify in office",
        "en-US",
        pipeline,
        "sonos-m2v-entities",
    )
    capture_handler(minicroft, source)

    search = next(
        kwargs
        for name, _args, kwargs in OfflineSonosController.calls
        if name == "search_and_play"
    )
    assert search == {
        "artist": "john lennon",
        "category": "tracks",
        "query": "imagine",
        "service_name": "spotify",
        "speaker_name": "office",
    }


@pytest.mark.parametrize(
    ("event", "command", "required_state"),
    [
        ("mycroft.audio.service.stop", "stop", "PLAYING"),
        ("mycroft.audio.service.next", "next", "PLAYING"),
        ("mycroft.audio.service.prev", "previous", "PLAYING"),
        ("mycroft.audio.service.pause", "pause", "PLAYING"),
        ("mycroft.audio.service.resume", "play", "PAUSED_PLAYBACK"),
    ],
)
def test_common_audio_bus_controls_reach_sonos(
    minicroft_factory, event, command, required_state
):
    """Exercise every non-utterance transport event registered by the skill."""
    minicroft = minicroft_factory.get("en-US")
    OfflineSonosController.reset()
    minicroft.bus.emit(Message(event))

    deadline = monotonic() + 5
    while monotonic() < deadline and not OfflineSonosController.calls:
        sleep(0.05)
    call = next(
        kwargs
        for name, _args, kwargs in OfflineSonosController.calls
        if name == "run_command"
    )
    assert call == {
        "command": command,
        "speaker": None,
        "required_state": required_state,
        "mode": None,
    }


def test_default_service_is_used_when_provider_slot_is_absent(minicroft_factory):
    """Verify the configured fallback crosses the complete intent pipeline."""
    minicroft = minicroft_factory.get("en-US")
    OfflineSonosController.reset()
    source = utterance_message(
        "play song imagine in office",
        "en-US",
        PADACIOSO_PIPELINE,
        "sonos-default-provider",
    )
    capture_handler(minicroft, source)

    search = next(
        kwargs
        for name, _args, kwargs in OfflineSonosController.calls
        if name == "search_and_play"
    )
    assert search["service_name"] == DEFAULT_SOURCE
    assert search["speaker_name"] == "office"
    assert search["query"] == "imagine"
    assert search["category"] == "tracks"


def test_relative_volume_intents_keep_distinct_steps(minicroft_factory):
    """Protect the semantic difference between normal and large adjustments."""
    minicroft = minicroft_factory.get("en-US")
    cases = {
        "volume up on office": DEFAULT_VOLUME_STEP,
        "volume down on office": -DEFAULT_VOLUME_STEP,
        "volume much louder on office": LARGE_VOLUME_STEP,
        "volume much quieter on office": -LARGE_VOLUME_STEP,
    }
    for utterance, expected_delta in cases.items():
        OfflineSonosController.reset()
        source = utterance_message(
            utterance,
            "en-US",
            PADACIOSO_PIPELINE,
            f"sonos-volume-{expected_delta}",
        )
        capture_handler(minicroft, source)
        call = next(
            args
            for name, args, _kwargs in OfflineSonosController.calls
            if name == "change_volume"
        )
        assert call == (expected_delta, "office")
