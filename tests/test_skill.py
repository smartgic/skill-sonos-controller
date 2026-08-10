"""Focused tests for helpers in the OVOS voice layer."""

from types import SimpleNamespace

import requests
from ovos_bus_client.message import Message

from skill_sonos_controller import SonosControllerSkill, _spelling_alphabet


def test_spelling_alphabet_indexes_standard_named_values_by_system_value():
    values = {
        "'A' as in Alfa": "A",
        "the number one": "1",
    }

    assert _spelling_alphabet(values) == {
        "A": "'A' as in Alfa",
        "1": "the number one",
    }


def test_classifier_only_message_is_hydrated_from_selected_intent_file():
    class Resources:
        @staticmethod
        def load_intent_file(name):
            if name == "sonos.track.intent":
                return ["play song {track} by {artist} from {service} in {speaker}"]
            return []

    class Skill:
        @staticmethod
        def load_lang(**_kwargs):
            return Resources()

    skill = Skill()
    message = Message(
        "skill.intent",
        {
            "confidence": 0.9,
            "lang": "en-US",
            "utterance": ("play song imagine by john lennon from spotify in office"),
        },
    )

    SonosControllerSkill._hydrate_message_entities(skill, message, "sonos.track.intent")

    assert message.data.items() >= {
        ("artist", "john lennon"),
        ("service", "spotify"),
        ("speaker", "office"),
        ("track", "imagine"),
    }


def test_completed_authentication_is_kept_when_link_cleanup_fails(monkeypatch):
    class Settings(dict):
        stored = False

        def store(self):
            self.stored = True

    class Controller:
        completed = None

        def complete_authentication(self, service, code, device_id):
            self.completed = (service, code, device_id)

    class Broker:
        def __init__(self, _url):
            pass

        @staticmethod
        def resolve(_short_code):
            return SimpleNamespace(
                code="provider-code", device_id="device", service="Spotify"
            )

        @staticmethod
        def delete(_short_code):
            raise requests.RequestException("cleanup unavailable")

    class Skill:
        def __init__(self):
            self.settings = Settings(
                link_code="AB12", url_shortener="https://sonos.example"
            )
            self.controller = Controller()
            self.dialogs = []

        @staticmethod
        def _hydrate_message_entities(_message, _intent):
            return False

        @staticmethod
        def _message_service(_message):
            return "Spotify"

        def speak_dialog(self, dialog, **_kwargs):
            self.dialogs.append(dialog)

    monkeypatch.setattr("skill_sonos_controller.AuthenticationBroker", Broker)
    skill = Skill()

    SonosControllerSkill._handle_authenticate(
        skill, Message("skill.intent", {"service": "Spotify"})
    )

    assert skill.controller.completed == ("Spotify", "provider-code", "device")
    assert skill.settings["link_code"] == ""
    assert skill.settings.stored is True
    assert skill.dialogs == ["sonos.authenticated"]
