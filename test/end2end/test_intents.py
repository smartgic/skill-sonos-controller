"""OVOScope tests for every localized Sonos intent.

The real intent service, skill loader, resource files, and handler lifecycle run
inside MiniCroft. Sonos I/O is replaced before the skill is constructed so the
suite is deterministic and can never control speakers on a developer or CI LAN.
"""

# One complete localized utterance per line keeps this intent matrix auditable.
# ruff: noqa: E501

from pathlib import Path
from time import sleep
from types import SimpleNamespace
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

from skill_sonos_controller.constants import SUPPORTED_LOCALES
from skill_sonos_controller.exceptions import NoSpeakersError

SKILL_ID = "skill-sonos-controller.smartgic"
RESOURCE_ROOT = Path(__file__).parents[2] / "skill_sonos_controller" / "locale"
HANDLER_EOF_MESSAGES = [
    "mycroft.skill.handler.complete",
    "mycroft.skill.handler.error",
]

LANGUAGE_TAGS = {
    "ca-es": "ca-ES",
    "da-dk": "da-DK",
    "de-de": "de-DE",
    "en-us": "en-US",
    "es-es": "es-ES",
    "eu-es": "eu-ES",
    "fa-ir": "fa-IR",
    "fr-fr": "fr-FR",
    "gl-es": "gl-ES",
    "it-it": "it-IT",
    "nl-be": "nl-BE",
    "nl-nl": "nl-NL",
    "pl-pl": "pl-PL",
    "pt-br": "pt-BR",
    "pt-pt": "pt-PT",
    "uk-ua": "uk-UA",
}

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

M2V_PROTOTYPE_PIPELINE = [
    "ovos-m2v-prototype-pipeline-high",
    "ovos-m2v-prototype-pipeline-medium",
    "ovos-m2v-prototype-pipeline-low",
]


class OfflineSonosController:
    """Sonos boundary used while OVOScope exercises the voice layer."""

    last_play = None

    def __init__(self) -> None:
        self.speakers = ()
        self.registry = SimpleNamespace(household_services=())

    def refresh(self):
        return ()

    @staticmethod
    def _unavailable(*_args, **_kwargs):
        raise NoSpeakersError("Sonos I/O is disabled in OVOScope")

    begin_authentication = _unavailable
    change_volume = _unavailable
    complete_authentication = _unavailable
    coordinators = _unavailable
    duck = _unavailable
    group_all = _unavailable
    group_speakers = _unavailable
    resolve_speaker = _unavailable
    run_command = _unavailable
    set_home_theater_option = _unavailable
    set_mute = _unavailable
    set_playback_option = _unavailable
    set_volume = _unavailable
    switch_to_tv = _unavailable
    ungroup_speaker = _unavailable
    unduck = _unavailable

    def search_and_play(self, **kwargs):
        type(self).last_play = kwargs
        raise NoSpeakersError("Sonos I/O is disabled in OVOScope")


CASES = {
    "en-US": {
        "sonos.album.intent": "play thriller album by michael jackson from Spotify in office",
        "sonos.authenticate.intent": "authenticate Spotify with sonos",
        "sonos.discovery.intent": "discover my sonos speakers",
        "sonos.next.music.intent": "next song on office",
        "sonos.pause.music.intent": "pause music on office",
        "sonos.playlist.intent": "play road trip playlist from Spotify in office",
        "sonos.podcast.intent": "play the daily podcast from TuneIn in office",
        "sonos.previous.music.intent": "previous song on office",
        "sonos.repeat.off.intent": "disable repeat mode on office",
        "sonos.repeat.on.intent": "enable repeat mode on office",
        "sonos.resume.music.intent": "resume music on office",
        "sonos.service.intent": "list my music services",
        "sonos.shuffle.off.intent": "disable shuffle mode on office",
        "sonos.shuffle.on.intent": "enable shuffle mode on office",
        "sonos.speaker.info.intent": "give me detailed information about office speaker",
        "sonos.stop.music.intent": "stop the music on office",
        "sonos.track.intent": "play song imagine by john lennon from Spotify in office",
        "sonos.volume.down.intent": "volume down on office",
        "sonos.volume.louder.intent": "volume much louder on office",
        "sonos.volume.quieter.intent": "volume much quieter on office",
        "sonos.volume.up.intent": "volume up on office",
        "sonos.what.is.playing.intent": "what is playing on office",
        "sonos.which.artist.intent": "which artist is playing on office",
    },
    "de-DE": {
        "sonos.album.intent": "spiele Thriller Album von Michael Jackson aus Spotify auf Office",
        "sonos.authenticate.intent": "authentifiziere Spotify mit Sonos",
        "sonos.discovery.intent": "finde meine Sonos Lautsprecher",
        "sonos.next.music.intent": "nächste Musik auf Office",
        "sonos.pause.music.intent": "pausiere Musik auf Office",
        "sonos.playlist.intent": "spiele eine Road Trip Playlist aus Spotify auf Office",
        "sonos.podcast.intent": "spiele den Podcast The Daily aus TuneIn auf Office",
        "sonos.previous.music.intent": "letzte Musik auf Office",
        "sonos.repeat.off.intent": "schalte Wiederholung aus auf Office",
        "sonos.repeat.on.intent": "schalte Wiederholung ein auf Office",
        "sonos.resume.music.intent": "setze Musik auf Office fort",
        "sonos.service.intent": "liste meine Musik Services auf",
        "sonos.shuffle.off.intent": "schalte Zufallsmodus aus auf Office",
        "sonos.shuffle.on.intent": "schalte Zufallsmodus ein auf Office",
        "sonos.speaker.info.intent": "gib mir detaillierte Informationen über den Lautsprecher Office",
        "sonos.stop.music.intent": "stoppe die Musik auf Office",
        "sonos.track.intent": "spiele das Lied Imagine von John Lennon über Spotify auf Office",
        "sonos.volume.down.intent": "verringere die Lautstärke auf Office",
        "sonos.volume.louder.intent": "erhöhe die Lautstärke stark auf Office",
        "sonos.volume.quieter.intent": "sehr viel leiser auf Office",
        "sonos.volume.up.intent": "erhöhe die Lautstärke auf Office",
        "sonos.what.is.playing.intent": "was läuft gerade auf Office",
        "sonos.which.artist.intent": "welcher Künstler läuft gerade auf Office",
    },
    "fr-FR": {
        "sonos.album.intent": "joue l'album Thriller de Michael Jackson depuis Spotify sur bureau",
        "sonos.authenticate.intent": "authentifie Spotify avec Sonos",
        "sonos.discovery.intent": "trouve mes enceintes Sonos",
        "sonos.next.music.intent": "chanson suivante sur bureau",
        "sonos.pause.music.intent": "pause la musique sur Office",
        "sonos.playlist.intent": "joue une playlist Road Trip depuis Spotify sur Office",
        "sonos.podcast.intent": "joue le podcast The Daily depuis TuneIn sur bureau",
        "sonos.previous.music.intent": "musique precedente sur Office",
        "sonos.repeat.off.intent": "désactive le mode répétition sur bureau",
        "sonos.repeat.on.intent": "active le mode répétition sur bureau",
        "sonos.resume.music.intent": "reprends la musique sur bureau",
        "sonos.service.intent": "liste mes services de musique",
        "sonos.shuffle.off.intent": "désactive le mode aléatoire sur bureau",
        "sonos.shuffle.on.intent": "active le mode aléatoire sur bureau",
        "sonos.speaker.info.intent": "donne moi des informations détaillées sur l'enceinte Office",
        "sonos.stop.music.intent": "arrête la musique sur bureau",
        "sonos.track.intent": "joue la chanson Imagine de John Lennon depuis Spotify sur bureau",
        "sonos.volume.down.intent": "diminue le volume sur bureau",
        "sonos.volume.louder.intent": "augmente beaucoup le volume sur bureau",
        "sonos.volume.quieter.intent": "diminue beaucoup le volume sur bureau",
        "sonos.volume.up.intent": "augmente le volume sur bureau",
        "sonos.what.is.playing.intent": "quelle est la chanson en cours de lecture sur Office",
        "sonos.which.artist.intent": "quel est l'artiste en cours de lecture sur Office",
    },
    "it-IT": {
        "sonos.album.intent": "riproduci l'album Thriller di Michael Jackson da Spotify in Office",
        "sonos.authenticate.intent": "autentica Spotify con Sonos",
        "sonos.discovery.intent": "trova gli altoparlanti Sonos",
        "sonos.next.music.intent": "prossima canzone in ufficio",
        "sonos.pause.music.intent": "metti in pausa la musica in ufficio",
        "sonos.playlist.intent": "fai partire la playlist Road Trip da Spotify in Office",
        "sonos.podcast.intent": "fai partire il podcast The Daily da TuneIn in Office",
        "sonos.previous.music.intent": "vai alla canzone precedente in Office",
        "sonos.repeat.off.intent": "disabilita la modalità ripeti in Office",
        "sonos.repeat.on.intent": "attiva la modalità ripeti in Office",
        "sonos.resume.music.intent": "riprendi la musica in Office",
        "sonos.service.intent": "elenca i miei servizi di musica",
        "sonos.shuffle.off.intent": "disabilita la modalità riproduzione casuale in Office",
        "sonos.shuffle.on.intent": "attiva la modalità riproduzione casuale in Office",
        "sonos.speaker.info.intent": "dammi informazioni sull'altoparlante Office",
        "sonos.stop.music.intent": "ferma la musica in ufficio",
        "sonos.track.intent": "riproduci la canzone Imagine di John Lennon da Spotify in Office",
        "sonos.volume.down.intent": "diminuisci il volume in ufficio",
        "sonos.volume.louder.intent": "aumenta molto il volume in ufficio",
        "sonos.volume.quieter.intent": "abbassa molto il volume in Office",
        "sonos.volume.up.intent": "aumenta il volume in ufficio",
        "sonos.what.is.playing.intent": "cosa stai riproducendo in ufficio",
        "sonos.which.artist.intent": "quale artista è in riproduzione in ufficio",
    },
}


def generated_locale_cases(locale):
    """Build auditable OVOScope utterances from each localized intent file."""
    intent_root = RESOURCE_ROOT / locale / "intents"
    cases = {}
    for path in sorted(intent_root.glob("*.intent")):
        template = next(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        values = {**SLOT_VALUES, "detailed": DETAILED_VALUES[locale]}
        cases[path.name] = expand(template)[0].format_map(values)
    return cases


assert set(LANGUAGE_TAGS) == set(SUPPORTED_LOCALES)
for locale in SUPPORTED_LOCALES:
    language_tag = LANGUAGE_TAGS[locale]
    CASES[language_tag] = {
        **generated_locale_cases(locale),
        **CASES.get(language_tag, {}),
    }

INTENT_CASES = [
    pytest.param(lang, utterance, intent, id=f"{lang}-{intent}")
    for lang, language_cases in CASES.items()
    for intent, utterance in language_cases.items()
]


class LocalizedMiniCroft:
    """Keep exactly one language/pipeline MiniCroft alive at a time."""

    def __init__(self):
        self.lang = None
        self.pipeline = None
        self.runtime = None

    def get(self, lang, pipeline=PADACIOSO_PIPELINE):
        pipeline = tuple(pipeline)
        if self.lang == lang and self.pipeline == pipeline:
            return self.runtime
        self.stop()
        with patch("skill_sonos_controller.SonosController", OfflineSonosController):
            self.runtime = get_minicroft(
                [SKILL_ID],
                default_pipeline=list(pipeline),
                lang=lang,
                max_wait=240,
            )
        assert SKILL_ID in self.runtime.plugin_skills
        self.runtime.bus.emit(Message("mycroft.skills.train"))
        sleep(0.25)
        self.lang = lang
        self.pipeline = pipeline
        return self.runtime

    def stop(self):
        if self.runtime is not None:
            self.runtime.stop()
        self.lang = None
        self.pipeline = None
        self.runtime = None


def capture_handler(minicroft, source, timeout=30):
    """Capture through handler completion, not the earlier routing EOF.

    Current ovos-core can emit ``ovos.utterance.handled`` after routing but
    before an asynchronous skill handler runs. Waiting for the handler's own
    lifecycle event makes the assertion deterministic across release trains.
    """
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


@pytest.fixture(scope="module")
def minicroft_factory():
    factory = LocalizedMiniCroft()
    try:
        yield factory
    finally:
        factory.stop()


@pytest.mark.parametrize(("lang", "utterance", "expected_intent"), INTENT_CASES)
def test_localized_intent_routes_and_completes(
    minicroft_factory, lang, utterance, expected_intent
):
    minicroft = minicroft_factory.get(lang)
    session = Session(f"sonos-{lang}-{expected_intent}")
    session.lang = lang
    session.pipeline = list(PADACIOSO_PIPELINE)
    source = Message(
        "recognizer_loop:utterance",
        {"utterances": [utterance], "lang": lang},
        {"session": session.serialize()},
    )
    messages = capture_handler(minicroft, source)

    message_types = [message.msg_type for message in messages]
    intent_type = f"{SKILL_ID}:{expected_intent.removesuffix('.intent')}"
    assert intent_type in message_types
    assert "mycroft.skill.handler.start" in message_types
    assert "mycroft.skill.handler.complete" in message_types
    assert "mycroft.skill.handler.error" not in message_types


def test_service_slot_accepts_runtime_advertised_names(minicroft_factory):
    """Provider slots remain open to names not shipped in service.entity."""
    lang = "en-US"
    utterance = "play song test from Community Radio Plus in office"
    minicroft = minicroft_factory.get(lang)
    session = Session("sonos-runtime-provider")
    session.lang = lang
    session.pipeline = list(PADACIOSO_PIPELINE)
    source = Message(
        "recognizer_loop:utterance",
        {"utterances": [utterance], "lang": lang},
        {"session": session.serialize()},
    )
    messages = capture_handler(minicroft, source)

    intent_type = f"{SKILL_ID}:sonos.track"
    matched = next(message for message in messages if message.msg_type == intent_type)
    assert matched.data["service"] == "community radio plus"
    assert "mycroft.skill.handler.error" not in {
        message.msg_type for message in messages
    }


LEGACY_PIPELINE_CASES = [
    pytest.param(
        pipeline_name,
        pipeline,
        utterance,
        intent,
        id=f"{pipeline_name}-{intent}",
    )
    for pipeline_name, pipeline in (
        ("padatious", PADATIOUS_PIPELINE),
        ("m2v-prototype", M2V_PROTOTYPE_PIPELINE),
    )
    for intent, utterance in CASES["en-US"].items()
]


@pytest.mark.parametrize(
    ("pipeline_name", "pipeline", "utterance", "expected_intent"),
    LEGACY_PIPELINE_CASES,
)
def test_complete_english_surface_on_legacy_pipelines(
    minicroft_factory, pipeline_name, pipeline, utterance, expected_intent
):
    """Route every intent through Padatious and trainable model2vec."""
    minicroft = minicroft_factory.get("en-US", pipeline)
    session = Session(f"sonos-{pipeline_name}-{expected_intent}")
    session.lang = "en-US"
    session.pipeline = list(pipeline)
    source = Message(
        "recognizer_loop:utterance",
        {"utterances": [utterance], "lang": "en-US"},
        {"session": session.serialize()},
    )
    messages = capture_handler(minicroft, source)

    message_types = [message.msg_type for message in messages]
    intent_type = f"{SKILL_ID}:{expected_intent.removesuffix('.intent')}"
    if pipeline_name == "m2v-prototype" and intent_type not in message_types:
        reroute = next(
            message
            for message in messages
            if message.msg_type == "sonos.classifier.rerouted"
        )
        assert reroute.data["to"] == expected_intent
    else:
        assert intent_type in message_types
    assert "mycroft.skill.handler.complete" in message_types
    assert "mycroft.skill.handler.error" not in message_types


def test_m2v_classifier_result_is_hydrated_with_freeform_entities(
    minicroft_factory,
):
    """Prove m2v classification reaches the controller with usable slots."""
    pipeline = M2V_PROTOTYPE_PIPELINE
    minicroft = minicroft_factory.get("en-US", pipeline)
    OfflineSonosController.last_play = None
    session = Session("sonos-m2v-entities")
    session.lang = "en-US"
    session.pipeline = list(pipeline)
    source = Message(
        "recognizer_loop:utterance",
        {
            "utterances": ["play song imagine by john lennon from Spotify in office"],
            "lang": "en-US",
        },
        {"session": session.serialize()},
    )
    capture_handler(minicroft, source)

    assert OfflineSonosController.last_play == {
        "artist": "john lennon",
        "category": "tracks",
        "query": "imagine",
        "service_name": "spotify",
        "speaker_name": "office",
    }
