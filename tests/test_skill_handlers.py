"""Unit tests for voice-layer effects and user-facing failure handling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests
from ovos_bus_client.message import Message
from soco.exceptions import MusicServiceAuthException, SoCoException

from skill_sonos_controller import (
    DEFAULT_SETTINGS,
    SonosControllerSkill,
    _as_bool,
)
from skill_sonos_controller.auth import AuthenticationLink
from skill_sonos_controller.constants import DEFAULT_SOURCE, DEFAULT_VOLUME_STEP
from skill_sonos_controller.controller import PlaybackResult
from skill_sonos_controller.exceptions import (
    AmbiguousSpeakerError,
    AuthenticationNotSupportedError,
    AuthenticationRequiredError,
    CategoryNotSupportedError,
    NoResultsError,
    NoSpeakersError,
    ServiceNotFoundError,
    SpeakerNotFoundError,
)


class Settings(dict):
    """Minimal OVOS settings double that records persistence."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.store_count = 0

    def store(self) -> None:
        self.store_count += 1


class SkillHarness:
    """Bind the voice helpers without starting an OVOS message bus."""

    _refresh_household = SonosControllerSkill._refresh_household
    _message_service = SonosControllerSkill._message_service
    _play_from_message = SonosControllerSkill._play_from_message
    _confirm_playback = SonosControllerSkill._confirm_playback
    _run_transport = SonosControllerSkill._run_transport
    _set_playback_option = SonosControllerSkill._set_playback_option
    _change_volume = SonosControllerSkill._change_volume
    _set_mute = SonosControllerSkill._set_mute
    _change_group = SonosControllerSkill._change_group
    _change_home_theater = SonosControllerSkill._change_home_theater
    _speak_track_info = SonosControllerSkill._speak_track_info

    def __init__(self) -> None:
        self.controller = MagicMock()
        self.service = DEFAULT_SOURCE
        self.settings = Settings(DEFAULT_SETTINGS)
        self.lang = "en-US"
        self.duck_enabled = False
        self.playing_confirmation = False
        self.searching_confirmation = False
        self.nato_dict = {"A": "Alfa", "1": "one"}
        self.dialogs: list[tuple[str, dict, dict]] = []
        self.spoken: list[str] = []
        self.yesno = "no"

        speaker = SimpleNamespace(
            player_name="Office",
            volume=12,
            get_current_track_info=lambda: {
                "title": "Imagine",
                "artist": "John Lennon",
            },
            get_speaker_info=lambda: {
                "model_name": "Sonos:Era 100",
                "model_number": "S39",
                "display_version": "81.1",
                "uid": "RINCON_TEST",
                "serial_number": "00-00-00-00-00-00",
                "software_version": "81.1",
                "hardware_version": "1.0",
                "mac_address": "00:00:00:00:00:00",
            },
        )
        self.controller.speakers = (speaker,)
        self.controller.registry.household_services = (
            SimpleNamespace(name="Music Library"),
            SimpleNamespace(name="Spotify"),
        )
        self.controller.refresh.return_value = self.controller.speakers
        self.controller.resolve_speaker.return_value = speaker
        self.controller.coordinators.return_value = (speaker,)
        self.controller.transport_state.return_value = "PLAYING"

    @staticmethod
    def _hydrate_message_entities(_message: Message, _intent: str) -> bool:
        return False

    def speak_dialog(self, dialog: str, data=None, **kwargs) -> None:
        self.dialogs.append((dialog, data or {}, kwargs))

    def speak(self, utterance: str) -> None:
        self.spoken.append(utterance)

    def ask_yesno(self, _dialog: str) -> str:
        return self.yesno


def message(**data) -> Message:
    return Message("skill.intent", data)


def assert_last_dialog(skill: SkillHarness, expected: str) -> None:
    assert skill.dialogs[-1][0] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (" YES ", True),
        ("on", True),
        ("0", False),
        ("false", False),
        (None, False),
    ],
)
def test_legacy_setting_booleans_are_normalized(value, expected):
    assert _as_bool(value) is expected


def test_settings_refresh_uses_safe_defaults_for_empty_values():
    skill = SkillHarness()
    skill.settings.update(
        default_source="  ",
        duck="yes",
        playing_confirmation="true",
        searching_confirmation="off",
    )

    SonosControllerSkill.on_settings_changed(skill)

    assert skill.service == DEFAULT_SOURCE
    assert skill.duck_enabled is True
    assert skill.playing_confirmation is True
    assert skill.searching_confirmation is False
    assert skill._message_service(message(service="  ")) == DEFAULT_SOURCE


def test_runtime_requirements_match_a_local_network_skill():
    requirements = SonosControllerSkill.runtime_requirements

    assert requirements.requires_network is True
    assert requirements.network_before_load is True
    assert requirements.requires_internet is False
    assert requirements.requires_gui is False


def test_discovery_and_service_listing_use_current_household_data():
    skill = SkillHarness()
    skill.yesno = "yes"

    SonosControllerSkill._handle_speaker_discovery(skill, message())
    services = SonosControllerSkill._handle_subscribed_services(skill, message())

    assert services == ["Music Library", "Spotify"]
    assert [dialog for dialog, _data, _kwargs in skill.dialogs] == [
        "sonos.discovery.result",
        "sonos.service.result",
    ]
    assert skill.spoken == ["Office", "Music Library", "Spotify"]


@pytest.mark.parametrize("failure", [OSError("offline"), SoCoException("offline")])
def test_discovery_failures_are_reported(failure):
    skill = SkillHarness()
    skill.controller.refresh.side_effect = failure

    SonosControllerSkill._handle_speaker_discovery(skill, message())

    assert_last_dialog(skill, "error.discovery")


@pytest.mark.parametrize(
    ("category", "query_key", "artist"),
    [
        ("albums", "album", "Michael Jackson"),
        ("artists", "artist", None),
        ("playlists", "playlist", None),
        ("podcasts", "podcast", None),
        ("stations", "station", None),
        ("tracks", "track", "John Lennon"),
    ],
)
def test_every_playback_category_reaches_the_controller(category, query_key, artist):
    skill = SkillHarness()
    skill.playing_confirmation = True
    payload = {
        query_key: "Query",
        "speaker": "Office",
        "service": "Spotify",
    }
    if artist:
        payload["artist"] = artist
    skill.controller.search_and_play.return_value = PlaybackResult(
        title="Result",
        service="Spotify",
        speaker="Office",
        category=category,
        artist=artist,
    )

    skill._play_from_message(message(**payload), category, query_key)

    skill.controller.search_and_play.assert_called_once_with(
        service_name="Spotify",
        speaker_name="Office",
        category=category,
        query="Query",
        artist=artist,
    )
    suffix = "artist" if artist and category in {"albums", "tracks"} else "result"
    assert_last_dialog(skill, f"sonos.{category[:-1]}.{suffix}")


@pytest.mark.parametrize(
    ("handler", "category", "query_key"),
    [
        ("_handle_album", "albums", "album"),
        ("_handle_artist", "artists", "artist"),
        ("_handle_playlist", "playlists", "playlist"),
        ("_handle_podcast", "podcasts", "podcast"),
        ("_handle_station", "stations", "station"),
        ("_handle_track", "tracks", "track"),
    ],
)
def test_playback_intent_handlers_delegate_to_the_shared_path(
    handler, category, query_key
):
    skill = SkillHarness()
    skill._play_from_message = MagicMock()
    source = message()

    getattr(SonosControllerSkill, handler)(skill, source)

    skill._play_from_message.assert_called_once_with(source, category, query_key)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (NoResultsError(), "error.track.artist"),
        (CategoryNotSupportedError(), "error.category"),
        (ServiceNotFoundError(), "error.support"),
        (AuthenticationNotSupportedError(), "error.auth.unsupported"),
        (AuthenticationRequiredError(), "error.auth"),
        (MusicServiceAuthException("auth"), "error.auth"),
        (SpeakerNotFoundError(), "error.speaker"),
        (AmbiguousSpeakerError(), "error.speaker"),
        (NoSpeakersError(), "error.discovery"),
        (OSError("offline"), "error.sonos"),
    ],
)
def test_playback_failures_have_specific_dialogs(failure, expected):
    skill = SkillHarness()
    skill.controller.search_and_play.side_effect = failure

    skill._play_from_message(
        message(
            track="Imagine",
            artist="John Lennon",
            speaker="Office",
            service="Spotify",
        ),
        "tracks",
        "track",
    )

    assert_last_dialog(skill, expected)


def test_zero_volume_warning_precedes_optional_playback_confirmation():
    skill = SkillHarness()
    skill.playing_confirmation = True
    skill.controller.resolve_speaker.return_value.volume = 0
    result = PlaybackResult("Imagine", "Spotify", "Office", "tracks", "John")

    skill._confirm_playback(result)

    assert [dialog for dialog, _data, _kwargs in skill.dialogs] == [
        "sonos.speaker.muted",
        "sonos.track.artist",
    ]


@pytest.mark.parametrize(
    ("command", "state"),
    [
        ("pause", "PLAYING"),
        ("stop", "PLAYING"),
        ("play", "PAUSED_PLAYBACK"),
        ("next", "PLAYING"),
        ("previous", "PLAYING"),
    ],
)
def test_every_transport_command_preserves_its_required_state(command, state):
    skill = SkillHarness()

    skill._run_transport(message(speaker="Office"), command, state)

    skill.controller.run_command.assert_called_once_with(
        command=command,
        speaker="Office",
        required_state=state,
        mode=None,
    )


@pytest.mark.parametrize(
    ("handler", "command", "required_state"),
    [
        ("_handle_pause_music", "pause", "PLAYING"),
        ("_handle_stop_music", "stop", "PLAYING"),
        ("_handle_resume_music", "play", "PAUSED_PLAYBACK"),
        ("_handle_next_music", "next", "PLAYING"),
        ("_handle_previous_music", "previous", "PLAYING"),
    ],
)
def test_transport_intent_handlers_delegate_with_the_correct_state(
    handler, command, required_state
):
    skill = SkillHarness()
    skill._run_transport = MagicMock()
    source = message()

    getattr(SonosControllerSkill, handler)(skill, source)

    if required_state == "PLAYING":
        skill._run_transport.assert_called_once_with(source, command)
    else:
        skill._run_transport.assert_called_once_with(
            source, command, required_state=required_state
        )


@pytest.mark.parametrize(
    ("handler", "helper", "arguments"),
    [
        ("_handle_shuffle_on", "_set_playback_option", ("shuffle", True)),
        ("_handle_shuffle_off", "_set_playback_option", ("shuffle", False)),
        ("_handle_repeat_on", "_set_playback_option", ("repeat", True)),
        ("_handle_repeat_off", "_set_playback_option", ("repeat", False)),
        ("_handle_volume_up", "_change_volume", (DEFAULT_VOLUME_STEP,)),
        ("_handle_volume_down", "_change_volume", (-DEFAULT_VOLUME_STEP,)),
        ("_handle_mute", "_set_mute", (True,)),
        ("_handle_unmute", "_set_mute", (False,)),
        ("_handle_group", "_change_group", ("group",)),
        ("_handle_group_all", "_change_group", ("all",)),
        ("_handle_ungroup", "_change_group", ("ungroup",)),
        ("_handle_tv", "_change_home_theater", ("tv",)),
        ("_handle_night_on", "_change_home_theater", ("night", True)),
        ("_handle_night_off", "_change_home_theater", ("night", False)),
        ("_handle_speech_on", "_change_home_theater", ("speech", True)),
        ("_handle_speech_off", "_change_home_theater", ("speech", False)),
    ],
)
def test_control_intent_handlers_delegate_to_shared_helpers(handler, helper, arguments):
    skill = SkillHarness()
    delegate = MagicMock()
    setattr(skill, helper, delegate)
    source = message()

    getattr(SonosControllerSkill, handler)(skill, source)

    if helper == "_change_group":
        delegate.assert_called_once_with(*arguments, source)
    else:
        delegate.assert_called_once_with(source, *arguments)


@pytest.mark.parametrize(
    ("helper", "arguments", "method", "expected_call"),
    [
        (
            "_set_playback_option",
            ("shuffle", True),
            "set_playback_option",
            ("shuffle", True, "Office"),
        ),
        (
            "_set_playback_option",
            ("repeat", False),
            "set_playback_option",
            ("repeat", False, "Office"),
        ),
        (
            "_change_volume",
            (DEFAULT_VOLUME_STEP,),
            "change_volume",
            (DEFAULT_VOLUME_STEP, "Office"),
        ),
        ("_set_mute", (True,), "set_mute", (True, "Office")),
        ("_change_home_theater", ("tv",), "switch_to_tv", ("Office",)),
        (
            "_change_home_theater",
            ("night", True),
            "set_home_theater_option",
            ("night", True, "Office"),
        ),
        (
            "_change_home_theater",
            ("speech", False),
            "set_home_theater_option",
            ("speech", False, "Office"),
        ),
    ],
)
def test_control_helpers_reach_the_expected_controller_method(
    helper, arguments, method, expected_call
):
    skill = SkillHarness()

    getattr(skill, helper)(message(speaker="Office"), *arguments)

    getattr(skill.controller, method).assert_called_once_with(*expected_call)


def test_every_grouping_operation_reaches_the_controller():
    skill = SkillHarness()

    skill._change_group("group", message(speaker="Office", group_speaker="Kitchen"))
    skill._change_group("all", message(speaker="Office"))
    skill._change_group("ungroup", message(speaker="Office"))

    skill.controller.group_speakers.assert_called_once_with("Office", ("Kitchen",))
    skill.controller.group_all.assert_called_once_with("Office")
    skill.controller.ungroup_speaker.assert_called_once_with("Office")
    with pytest.raises(ValueError, match="Unsupported grouping operation"):
        skill._change_group("invalid", message(speaker="Office"))


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (SpeakerNotFoundError(), "error.speaker"),
        (NoSpeakersError(), "error.discovery"),
        (OSError("offline"), "error.sonos"),
    ],
)
def test_control_failures_have_specific_dialogs(failure, expected):
    skill = SkillHarness()
    skill.controller.change_volume.side_effect = failure

    skill._change_volume(message(speaker="Office"), DEFAULT_VOLUME_STEP)

    assert_last_dialog(skill, expected)


@pytest.mark.parametrize("raw_level", ["", "101", "-1", "twelve point five"])
def test_exact_volume_rejects_missing_out_of_range_and_fractional_values(raw_level):
    skill = SkillHarness()

    SonosControllerSkill._handle_volume_set(
        skill, message(volume=raw_level, speaker="Office", lang="en-US")
    )

    assert_last_dialog(skill, "error.volume")
    skill.controller.set_volume.assert_not_called()


def test_exact_volume_uses_the_locale_aware_number_parser():
    skill = SkillHarness()

    SonosControllerSkill._handle_volume_set(
        skill, message(volume="twelve", speaker="Office", lang="en-US")
    )

    skill.controller.set_volume.assert_called_once_with(12, "Office")


def test_ducking_is_opt_in_and_fail_safe():
    skill = SkillHarness()

    SonosControllerSkill._handle_duck_volume(skill, message())
    skill.controller.duck.assert_not_called()

    skill.duck_enabled = True
    SonosControllerSkill._handle_duck_volume(skill, message())
    SonosControllerSkill._handle_unduck_volume(skill, message())
    skill.controller.duck.assert_called_once_with(DEFAULT_VOLUME_STEP)
    skill.controller.unduck.assert_called_once_with()

    skill.controller.duck.side_effect = NoSpeakersError()
    SonosControllerSkill._handle_duck_volume(skill, message())


@pytest.mark.parametrize(
    ("speaker", "artist_only", "expected_dialog", "expected_spoken"),
    [
        ("Office", False, "sonos.playing", []),
        ("Office", True, None, ["John Lennon"]),
        (None, False, "sonos.playing.on", []),
        (None, True, "sonos.playing.artist.on", []),
    ],
)
def test_track_information_covers_room_and_household_answers(
    speaker, artist_only, expected_dialog, expected_spoken
):
    skill = SkillHarness()

    skill._speak_track_info(message(speaker=speaker), artist_only)

    if expected_dialog:
        assert_last_dialog(skill, expected_dialog)
    assert skill.spoken == expected_spoken


@pytest.mark.parametrize(
    ("detailed", "expected"),
    [(False, "sonos.speaker.info.summary"), (True, "sonos.speaker.info.detailed")],
)
def test_speaker_information_covers_summary_and_detailed_answers(detailed, expected):
    skill = SkillHarness()

    SonosControllerSkill._handle_speaker_info(
        skill, message(speaker="Office", detailed=detailed)
    )

    assert_last_dialog(skill, expected)
    assert skill.dialogs[-1][1]["model_name"] == "Sonos Era 100"


def test_no_active_track_is_reported():
    skill = SkillHarness()
    skill.controller.transport_state.return_value = "STOPPED"

    skill._speak_track_info(message(), artist_only=False)

    assert_last_dialog(skill, "sonos.nothing.playing")


def test_authentication_start_speaks_and_preserves_the_broker_code(monkeypatch):
    skill = SkillHarness()
    provider = SimpleNamespace(
        link_code="provider-code",
        link_device_id="device",
        service_name="Spotify",
    )
    skill.controller.begin_authentication.return_value = (
        provider,
        "https://spotify.example/link",
    )
    broker = MagicMock()
    broker.create.return_value = "A1"
    monkeypatch.setattr(
        "skill_sonos_controller.AuthenticationBroker", lambda _url: broker
    )

    SonosControllerSkill._handle_authenticate(skill, message(service="Spotify"))

    broker.create.assert_called_once_with(
        "https://spotify.example/link",
        "provider-code",
        "device",
        "Spotify",
    )
    assert skill.dialogs == [("sonos.link_code", {"code": "Alfa. one"}, {"wait": True})]


def test_authentication_completion_uses_broker_service_and_clears_code(monkeypatch):
    skill = SkillHarness()
    skill.settings["link_code"] = "AB12"
    broker = MagicMock()
    broker.resolve.return_value = AuthenticationLink(
        code="provider-code", device_id="device", service="Spotify"
    )
    monkeypatch.setattr(
        "skill_sonos_controller.AuthenticationBroker", lambda _url: broker
    )

    SonosControllerSkill._handle_authenticate(skill, message(service="Music Library"))

    skill.controller.complete_authentication.assert_called_once_with(
        "Spotify", "provider-code", "device"
    )
    assert skill.settings["link_code"] == ""
    assert skill.settings.store_count == 1
    broker.delete.assert_called_once_with("AB12")
    assert_last_dialog(skill, "sonos.authenticated")


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (AuthenticationNotSupportedError(), "error.auth.unsupported"),
        (ServiceNotFoundError(), "error.support"),
        (NoSpeakersError(), "error.discovery"),
        (ValueError("bad code"), "error.code"),
        (requests.RequestException("offline"), "error.urlshortener"),
        (SoCoException("offline"), "error.auth"),
    ],
)
def test_authentication_failures_have_specific_dialogs(monkeypatch, failure, expected):
    skill = SkillHarness()
    skill.controller.begin_authentication.side_effect = failure
    monkeypatch.setattr(
        "skill_sonos_controller.AuthenticationBroker", lambda _url: MagicMock()
    )

    SonosControllerSkill._handle_authenticate(skill, message(service="Spotify"))

    assert_last_dialog(skill, expected)
