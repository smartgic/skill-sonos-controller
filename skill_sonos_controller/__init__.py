"""OpenVoiceOS skill for controlling a Sonos household."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

import requests
from ovos_bus_client.message import Message
from ovos_number_parser import extract_number
from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills import OVOSSkill
from padacioso import IntentContainer
from soco.exceptions import MusicServiceAuthException, SoCoException

from .auth import AuthenticationBroker
from .constants import (
    DEFAULT_SOURCE,
    DEFAULT_URL_SHORTENER,
    DEFAULT_VOLUME_STEP,
    LARGE_VOLUME_STEP,
)
from .controller import PlaybackResult, SonosController, normalize_name
from .exceptions import (
    AmbiguousSpeakerError,
    AuthenticationNotSupportedError,
    AuthenticationRequiredError,
    CategoryNotSupportedError,
    NoResultsError,
    NoSpeakersError,
    ServiceNotFoundError,
    SpeakerNotFoundError,
)

DEFAULT_SETTINGS = {
    "default_source": DEFAULT_SOURCE,
    "link_code": "",
    "duck": False,
    "playing_confirmation": False,
    "searching_confirmation": True,
    "url_shortener": DEFAULT_URL_SHORTENER,
}

Handler = TypeVar("Handler", bound=Callable[..., Any])
CLASSIFIER_INTENT_HANDLERS: dict[str, str] = {}


def sonos_intent_handler(intent_file: str) -> Callable[[Handler], Handler]:
    """Register an OVOS intent and its model2vec hydration handler together."""

    def decorate(handler: Handler) -> Handler:
        CLASSIFIER_INTENT_HANDLERS[intent_file] = handler.__name__
        return cast(Handler, intent_handler(intent_file)(handler))

    return decorate


def _as_bool(value: Any) -> bool:
    """Handle booleans from both JSON and legacy string-valued settings."""
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def _spelling_alphabet(values: dict[str, str]) -> dict[str, str]:
    """Index standard OVOS display/system values by the code character."""
    return {
        str(system_value).upper(): str(spoken_value)
        for spoken_value, system_value in values.items()
        if str(system_value).strip()
    }


class SonosControllerSkill(OVOSSkill):
    """Control local Sonos speakers and their configured music services."""

    def __init__(
        self, bus: Any | None = None, skill_id: str = "", **kwargs: Any
    ) -> None:
        # Domain state is available before OVOS starts registering the skill.
        self.controller = SonosController()
        self.service = DEFAULT_SOURCE
        self.duck_enabled = False
        self.playing_confirmation = False
        self.searching_confirmation = True
        self.nato_dict: dict[str, str] = {}
        self._entity_parsers: dict[str, IntentContainer] = {}
        super().__init__(bus=bus, skill_id=skill_id, **kwargs)

        # The current OVOS loader supplies both values. Keeping unbound
        # construction side-effect free also helps plugin discovery tools.
        if not self.is_fully_initialized:
            self._initial_settings.update(DEFAULT_SETTINGS)
            return

        self.settings.merge(DEFAULT_SETTINGS, new_only=True)
        self.nato_dict = _spelling_alphabet(
            self.resources.load_named_value_file("codes") or {}
        )
        self.register_entity_file("service.entity")
        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()
        self._register_audio_events()

        self._refresh_household(announce=False)

    @classproperty
    def runtime_requirements(self) -> RuntimeRequirements:
        """Sonos control needs LAN access, but local playback works offline."""
        return RuntimeRequirements(
            internet_before_load=False,
            network_before_load=True,
            gui_before_load=False,
            requires_internet=False,
            requires_network=True,
            requires_gui=False,
            no_internet_fallback=True,
            no_network_fallback=False,
            no_gui_fallback=True,
        )

    def _register_audio_events(self) -> None:
        """Register bus handlers exactly once during construction."""
        self.add_event("recognizer_loop:record_begin", self._handle_duck_volume)
        self.add_event("recognizer_loop:record_end", self._handle_unduck_volume)
        self.add_event("mycroft.audio.service.stop", self._handle_stop_music)
        self.add_event("mycroft.audio.service.next", self._handle_next_music)
        self.add_event("mycroft.audio.service.prev", self._handle_previous_music)
        self.add_event("mycroft.audio.service.pause", self._handle_pause_music)
        self.add_event("mycroft.audio.service.resume", self._handle_resume_music)

    def on_settings_changed(self) -> None:
        """Reload inexpensive settings without rediscovery or event duplication."""
        configured_service = str(
            self.settings.get("default_source", DEFAULT_SOURCE)
        ).strip()
        self.service = configured_service or DEFAULT_SOURCE
        self.duck_enabled = _as_bool(self.settings.get("duck", False))
        self.playing_confirmation = _as_bool(
            self.settings.get("playing_confirmation", False)
        )
        self.searching_confirmation = _as_bool(
            self.settings.get("searching_confirmation", True)
        )

    def _refresh_household(self, announce: bool) -> bool:
        try:
            speakers = self.controller.refresh()
        except (OSError, SoCoException, requests.RequestException) as error:
            LOG.warning("Sonos discovery failed: %s", error)
            speakers = ()
        if not speakers:
            if announce:
                self.speak_dialog("error.discovery")
            return False
        return True

    @sonos_intent_handler("sonos.discovery.intent")
    def _handle_speaker_discovery(self, message: Message) -> None:
        """Refresh and optionally list Sonos rooms."""
        if self._hydrate_message_entities(message, "sonos.discovery.intent"):
            return
        if not self._refresh_household(announce=True):
            return
        self.speak_dialog(
            "sonos.discovery.result",
            data={"total": len(self.controller.speakers)},
        )
        if self.ask_yesno("sonos.list") == "yes":
            for speaker in self.controller.speakers:
                self.speak(speaker.player_name)

    @sonos_intent_handler("sonos.service.intent")
    def _handle_subscribed_services(self, message: Message) -> list[str] | None:
        """List services dynamically discovered for this Sonos household."""
        if self._hydrate_message_entities(message, "sonos.service.intent"):
            return None
        if not self.controller.speakers and not self._refresh_household(announce=True):
            return None
        services = [
            service.name for service in self.controller.registry.household_services
        ]
        if not services:
            self.speak_dialog("error.service")
            return None
        self.speak_dialog("sonos.service.result", data={"total": len(services)})
        if self.ask_yesno("sonos.list") == "yes":
            for service in services:
                self.speak(service)
        return services

    def _message_service(self, message: Message) -> str:
        requested_service = str(message.data.get("service") or "").strip()
        return requested_service or self.service or DEFAULT_SOURCE

    def _entity_parser(self, lang: str) -> IntentContainer:
        """Return the cached local parser used to hydrate classifier results."""
        cache_key = lang.casefold()
        parser = self._entity_parsers.get(cache_key)
        if parser is None:
            resources = self.load_lang(lang=lang)
            parser = IntentContainer(n_workers=1)
            for candidate in CLASSIFIER_INTENT_HANDLERS:
                parser.add_intent(
                    candidate,
                    resources.load_intent_file(candidate),
                )
            self._entity_parsers[cache_key] = parser
        return parser

    def _hydrate_message_entities(self, message: Message, intent_file: str) -> bool:
        """Verify a classifier label and recover its free-form slots.

        Padacioso and Padatious already return entities. Model2vec prototype
        pipelines intentionally classify registered templates but do not
        extract their free-form slots. A local template match also corrects a
        semantic-model collision before the selected handler changes Sonos.

        Returns True when the message was rerouted to a different handler.
        """
        generic = {"confidence", "lang", "utterance", "utterances"}
        if set(message.data) - generic:
            return False
        utterance = str(message.data.get("utterance") or "").strip()
        if not utterance:
            utterances = message.data.get("utterances") or []
            utterance = str(utterances[0] if utterances else "").strip()
        if not utterance:
            return False
        lang = str(message.data.get("lang") or getattr(message, "lang", self.lang))
        try:
            parser = self._entity_parser(lang)
            match = parser.calc_intent(utterance) or {}
            entities = match.get("entities") or {}
            for name, value in entities.items():
                key = {"groupspeaker": "group_speaker"}.get(name, name)
                message.data.setdefault(key, value)
            matched_intent = str(match.get("name") or "")
            if matched_intent and matched_intent != intent_file:
                self.bus.emit(
                    Message(
                        "sonos.classifier.rerouted",
                        {"from": intent_file, "to": matched_intent},
                        message.context,
                    )
                )
                handler = getattr(self, CLASSIFIER_INTENT_HANDLERS[matched_intent])
                handler(message)
                return True
        except (OSError, RuntimeError, ValueError) as error:
            LOG.warning("Unable to extract %s entities: %s", intent_file, error)
        return False

    def _play_from_message(
        self,
        message: Message,
        category: str,
        query_key: str,
    ) -> None:
        if self._hydrate_message_entities(message, f"sonos.{category[:-1]}.intent"):
            return
        service = self._message_service(message)
        query = str(message.data.get(query_key) or "").strip()
        speaker = str(message.data.get("speaker") or "").strip()
        artist = (
            message.data.get("artist") if category in {"albums", "tracks"} else None
        )
        if self.searching_confirmation:
            self.speak_dialog("sonos.searching", data={"service": service})
        try:
            result = self.controller.search_and_play(
                service_name=service,
                speaker_name=speaker,
                category=category,
                query=query,
                artist=str(artist).strip() if artist else None,
            )
        except NoResultsError:
            dialog = {
                "albums": "error.album.artist" if artist else "error.album",
                "artists": "error.artist",
                "playlists": "error.playlist",
                "podcasts": "error.podcast",
                "stations": "error.station",
                "tracks": "error.track.artist" if artist else "error.track",
            }[category]
            data = {query_key: query}
            if artist:
                data["artist"] = artist
            self.speak_dialog(dialog, data=data)
        except CategoryNotSupportedError:
            self.speak_dialog(
                "error.category", data={"category": category, "service": service}
            )
        except ServiceNotFoundError:
            self.speak_dialog("error.support", data={"service": service})
        except AuthenticationNotSupportedError:
            self.speak_dialog("error.auth.unsupported", data={"service": service})
        except (AuthenticationRequiredError, MusicServiceAuthException):
            self.speak_dialog("error.auth", data={"service": service})
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog("error.speaker", data={"speaker": speaker})
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException, requests.RequestException) as error:
            LOG.exception("Sonos could not play %s: %s", query, error)
            self.speak_dialog("error.sonos")
        else:
            self._confirm_playback(result)

    def _confirm_playback(self, result: PlaybackResult) -> None:
        try:
            device = self.controller.resolve_speaker(result.speaker, coordinator=False)
            if int(device.volume) == 0:
                self.speak_dialog(
                    "sonos.speaker.muted", data={"speaker": result.speaker}
                )
        except (OSError, NoSpeakersError, SpeakerNotFoundError, SoCoException):
            LOG.debug("Unable to read Sonos volume after starting playback")

        if not self.playing_confirmation:
            return
        resource = result.category[:-1]
        dialog = f"sonos.{resource}.result"
        data = {
            resource: result.title,
            "service": result.service,
            "speaker": result.speaker,
        }
        if result.artist and result.category in {"albums", "tracks"}:
            dialog = f"sonos.{resource}.artist"
            data["artist"] = result.artist
        self.speak_dialog(dialog, data=data)

    @sonos_intent_handler("sonos.playlist.intent")
    def _handle_playlist(self, message: Message) -> None:
        self._play_from_message(message, "playlists", "playlist")

    @sonos_intent_handler("sonos.podcast.intent")
    def _handle_podcast(self, message: Message) -> None:
        self._play_from_message(message, "podcasts", "podcast")

    @sonos_intent_handler("sonos.album.intent")
    def _handle_album(self, message: Message) -> None:
        self._play_from_message(message, "albums", "album")

    @sonos_intent_handler("sonos.artist.intent")
    def _handle_artist(self, message: Message) -> None:
        self._play_from_message(message, "artists", "artist")

    @sonos_intent_handler("sonos.station.intent")
    def _handle_station(self, message: Message) -> None:
        self._play_from_message(message, "stations", "station")

    @sonos_intent_handler("sonos.track.intent")
    def _handle_track(self, message: Message) -> None:
        self._play_from_message(message, "tracks", "track")

    def _run_transport(
        self,
        message: Message,
        command: str,
        required_state: str = "PLAYING",
        mode: str | None = None,
    ) -> None:
        intent_name = {
            "next": "sonos.next.music.intent",
            "pause": "sonos.pause.music.intent",
            "previous": "sonos.previous.music.intent",
            "stop": "sonos.stop.music.intent",
        }.get(command, "sonos.resume.music.intent")
        if self._hydrate_message_entities(message, intent_name):
            return
        try:
            self.controller.run_command(
                command=command,
                speaker=message.data.get("speaker"),
                required_state=required_state,
                mode=mode,
            )
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog(
                "error.speaker", data={"speaker": message.data.get("speaker", "")}
            )
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Sonos %s command failed: %s", command, error)
            self.speak_dialog("error.sonos")

    @sonos_intent_handler("sonos.pause.music.intent")
    def _handle_pause_music(self, message: Message) -> None:
        self._run_transport(message, "pause")

    @sonos_intent_handler("sonos.stop.music.intent")
    def _handle_stop_music(self, message: Message) -> None:
        self._run_transport(message, "stop")

    @sonos_intent_handler("sonos.resume.music.intent")
    def _handle_resume_music(self, message: Message) -> None:
        self._run_transport(message, "play", required_state="PAUSED_PLAYBACK")

    @sonos_intent_handler("sonos.next.music.intent")
    def _handle_next_music(self, message: Message) -> None:
        self._run_transport(message, "next")

    @sonos_intent_handler("sonos.previous.music.intent")
    def _handle_previous_music(self, message: Message) -> None:
        self._run_transport(message, "previous")

    @sonos_intent_handler("sonos.shuffle.on.intent")
    def _handle_shuffle_on(self, message: Message) -> None:
        self._set_playback_option(message, "shuffle", True)

    @sonos_intent_handler("sonos.shuffle.off.intent")
    def _handle_shuffle_off(self, message: Message) -> None:
        self._set_playback_option(message, "shuffle", False)

    @sonos_intent_handler("sonos.repeat.on.intent")
    def _handle_repeat_on(self, message: Message) -> None:
        self._set_playback_option(message, "repeat", True)

    @sonos_intent_handler("sonos.repeat.off.intent")
    def _handle_repeat_off(self, message: Message) -> None:
        self._set_playback_option(message, "repeat", False)

    def _set_playback_option(
        self, message: Message, option: str, enabled: bool
    ) -> None:
        state = "on" if enabled else "off"
        if self._hydrate_message_entities(message, f"sonos.{option}.{state}.intent"):
            return
        try:
            self.controller.set_playback_option(
                option, enabled, message.data.get("speaker")
            )
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog(
                "error.speaker", data={"speaker": message.data.get("speaker", "")}
            )
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Sonos %s change failed: %s", option, error)
            self.speak_dialog("error.sonos")

    def _change_volume(self, message: Message, delta: int) -> None:
        intent_name = {
            DEFAULT_VOLUME_STEP: "sonos.volume.up.intent",
            -DEFAULT_VOLUME_STEP: "sonos.volume.down.intent",
            LARGE_VOLUME_STEP: "sonos.volume.louder.intent",
            -LARGE_VOLUME_STEP: "sonos.volume.quieter.intent",
        }[delta]
        if self._hydrate_message_entities(message, intent_name):
            return
        try:
            self.controller.change_volume(delta, message.data.get("speaker"))
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog(
                "error.speaker", data={"speaker": message.data.get("speaker", "")}
            )
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Sonos volume change failed: %s", error)
            self.speak_dialog("error.sonos")

    @sonos_intent_handler("sonos.volume.up.intent")
    def _handle_volume_up(self, message: Message) -> None:
        self._change_volume(message, DEFAULT_VOLUME_STEP)

    @sonos_intent_handler("sonos.volume.down.intent")
    def _handle_volume_down(self, message: Message) -> None:
        self._change_volume(message, -DEFAULT_VOLUME_STEP)

    @sonos_intent_handler("sonos.volume.louder.intent")
    def _handle_volume_louder(self, message: Message) -> None:
        self._change_volume(message, LARGE_VOLUME_STEP)

    @sonos_intent_handler("sonos.volume.quieter.intent")
    def _handle_volume_quieter(self, message: Message) -> None:
        self._change_volume(message, -LARGE_VOLUME_STEP)

    @sonos_intent_handler("sonos.volume.set.intent")
    def _handle_volume_set(self, message: Message) -> None:
        """Set an exact 0-100 volume using OVOS's locale-aware parser."""
        if self._hydrate_message_entities(message, "sonos.volume.set.intent"):
            return
        raw_level = str(message.data.get("volume") or "").strip()
        lang = str(message.data.get("lang") or getattr(message, "lang", self.lang))
        level = extract_number(raw_level, lang=lang)
        if (
            level is False
            or level is None
            or int(level) != level
            or not 0 <= int(level) <= 100
        ):
            self.speak_dialog("error.volume", data={"volume": raw_level})
            return
        try:
            self.controller.set_volume(int(level), message.data.get("speaker"))
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog(
                "error.speaker", data={"speaker": message.data.get("speaker", "")}
            )
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Sonos exact volume change failed: %s", error)
            self.speak_dialog("error.sonos")

    def _set_mute(self, message: Message, muted: bool) -> None:
        intent_name = "sonos.mute.intent" if muted else "sonos.unmute.intent"
        if self._hydrate_message_entities(message, intent_name):
            return
        try:
            self.controller.set_mute(muted, message.data.get("speaker"))
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog(
                "error.speaker", data={"speaker": message.data.get("speaker", "")}
            )
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Sonos mute change failed: %s", error)
            self.speak_dialog("error.sonos")

    @sonos_intent_handler("sonos.mute.intent")
    def _handle_mute(self, message: Message) -> None:
        self._set_mute(message, True)

    @sonos_intent_handler("sonos.unmute.intent")
    def _handle_unmute(self, message: Message) -> None:
        self._set_mute(message, False)

    def _change_group(self, operation: str, message: Message) -> None:
        intent_names = {
            "all": "sonos.group.all.intent",
            "group": "sonos.group.intent",
            "ungroup": "sonos.ungroup.intent",
        }
        if operation not in intent_names:
            raise ValueError(f"Unsupported grouping operation: {operation}")
        intent_name = intent_names[operation]
        if self._hydrate_message_entities(message, intent_name):
            return
        try:
            if operation == "group":
                group_speaker = message.data.get("group_speaker") or message.data.get(
                    "groupspeaker"
                )
                self.controller.group_speakers(
                    str(message.data.get("speaker") or ""),
                    (str(group_speaker or ""),),
                )
            elif operation == "all":
                self.controller.group_all(str(message.data.get("speaker") or ""))
            else:
                self.controller.ungroup_speaker(str(message.data.get("speaker") or ""))
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            speaker = (
                message.data.get("group_speaker")
                or message.data.get("groupspeaker")
                or message.data.get("speaker", "")
            )
            self.speak_dialog("error.speaker", data={"speaker": speaker})
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Sonos grouping failed: %s", error)
            self.speak_dialog("error.sonos")

    @sonos_intent_handler("sonos.group.intent")
    def _handle_group(self, message: Message) -> None:
        self._change_group("group", message)

    @sonos_intent_handler("sonos.group.all.intent")
    def _handle_group_all(self, message: Message) -> None:
        self._change_group("all", message)

    @sonos_intent_handler("sonos.ungroup.intent")
    def _handle_ungroup(self, message: Message) -> None:
        self._change_group("ungroup", message)

    def _change_home_theater(
        self, message: Message, option: str, enabled: bool | None = None
    ) -> None:
        intent_name = (
            "sonos.tv.intent"
            if option == "tv"
            else f"sonos.{option}.{'on' if enabled else 'off'}.intent"
        )
        if self._hydrate_message_entities(message, intent_name):
            return
        speaker = str(message.data.get("speaker") or "")
        try:
            if option == "tv":
                self.controller.switch_to_tv(speaker)
            else:
                self.controller.set_home_theater_option(option, bool(enabled), speaker)
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog("error.speaker", data={"speaker": speaker})
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Sonos home-theater change failed: %s", error)
            self.speak_dialog("error.sonos")

    @sonos_intent_handler("sonos.tv.intent")
    def _handle_tv(self, message: Message) -> None:
        self._change_home_theater(message, "tv")

    @sonos_intent_handler("sonos.night.on.intent")
    def _handle_night_on(self, message: Message) -> None:
        self._change_home_theater(message, "night", True)

    @sonos_intent_handler("sonos.night.off.intent")
    def _handle_night_off(self, message: Message) -> None:
        self._change_home_theater(message, "night", False)

    @sonos_intent_handler("sonos.speech.on.intent")
    def _handle_speech_on(self, message: Message) -> None:
        self._change_home_theater(message, "speech", True)

    @sonos_intent_handler("sonos.speech.off.intent")
    def _handle_speech_off(self, message: Message) -> None:
        self._change_home_theater(message, "speech", False)

    def _handle_duck_volume(self, _: Message) -> None:
        if not self.duck_enabled:
            return
        try:
            self.controller.duck(DEFAULT_VOLUME_STEP)
        except (OSError, SoCoException, NoSpeakersError) as error:
            LOG.debug("Sonos ducking skipped: %s", error)

    def _handle_unduck_volume(self, _: Message) -> None:
        if not self.duck_enabled:
            return
        try:
            self.controller.unduck()
        except (OSError, SoCoException, NoSpeakersError) as error:
            LOG.debug("Sonos volume restore skipped: %s", error)

    @sonos_intent_handler("sonos.what.is.playing.intent")
    def _handle_what_is_playing(self, message: Message) -> None:
        self._speak_track_info(message, artist_only=False)

    @sonos_intent_handler("sonos.which.artist.intent")
    def _handle_which_artist_playing(self, message: Message) -> None:
        self._speak_track_info(message, artist_only=True)

    def _speak_track_info(self, message: Message, artist_only: bool) -> None:
        intent_name = (
            "sonos.which.artist.intent"
            if artist_only
            else "sonos.what.is.playing.intent"
        )
        if self._hydrate_message_entities(message, intent_name):
            return
        try:
            if message.data.get("speaker"):
                devices = (self.controller.resolve_speaker(message.data["speaker"]),)
            else:
                devices = self.controller.coordinators("PLAYING")
            playing = []
            for device in devices:
                if self.controller.transport_state(device) != "PLAYING":
                    continue
                info = device.get_current_track_info()
                if info.get("title") or info.get("artist"):
                    playing.append((device, info))
            if not playing:
                self.speak_dialog("sonos.nothing.playing")
                return
            for device, info in playing:
                if artist_only and message.data.get("speaker"):
                    self.speak(info.get("artist") or info.get("title"))
                elif artist_only:
                    self.speak_dialog(
                        "sonos.playing.artist.on",
                        data={
                            "artist": info.get("artist", ""),
                            "speaker": device.player_name,
                        },
                    )
                elif message.data.get("speaker"):
                    self.speak_dialog(
                        "sonos.playing",
                        data={
                            "title": info.get("title", ""),
                            "artist": info.get("artist", ""),
                        },
                    )
                else:
                    self.speak_dialog(
                        "sonos.playing.on",
                        data={
                            "title": info.get("title", ""),
                            "artist": info.get("artist", ""),
                            "speaker": device.player_name,
                        },
                    )
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog(
                "error.speaker", data={"speaker": message.data.get("speaker", "")}
            )
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Unable to read Sonos track information: %s", error)
            self.speak_dialog("error.sonos")

    @sonos_intent_handler("sonos.speaker.info.intent")
    def _handle_speaker_info(self, message: Message) -> None:
        if self._hydrate_message_entities(message, "sonos.speaker.info.intent"):
            return
        speaker_name = str(message.data.get("speaker") or "")
        try:
            device = self.controller.resolve_speaker(speaker_name, coordinator=False)
            info = device.get_speaker_info()
            model_name = str(info.get("model_name", "Sonos")).replace(":", " ")
            data = {
                "model_name": model_name,
                "model_number": info.get("model_number", ""),
                "display_version": info.get("display_version", ""),
            }
            if message.data.get("detailed"):
                data.update(
                    {
                        "uid": info.get("uid", ""),
                        "serial_number": info.get("serial_number", ""),
                        "software_version": info.get("software_version", ""),
                        "hardware_version": info.get("hardware_version", ""),
                        "mac_address": info.get("mac_address", ""),
                    }
                )
                self.speak_dialog("sonos.speaker.info.detailed", data=data)
            else:
                self.speak_dialog("sonos.speaker.info.summary", data=data)
        except (SpeakerNotFoundError, AmbiguousSpeakerError):
            self.speak_dialog("error.speaker", data={"speaker": speaker_name})
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (OSError, SoCoException) as error:
            LOG.warning("Unable to read Sonos speaker information: %s", error)
            self.speak_dialog("error.sonos")

    @sonos_intent_handler("sonos.authenticate.intent")
    def _handle_authenticate(self, message: Message) -> None:
        """Begin or finish authentication for any compatible SMAPI service."""
        if self._hydrate_message_entities(message, "sonos.authenticate.intent"):
            return
        requested_service = self._message_service(message)
        broker = AuthenticationBroker(
            str(self.settings.get("url_shortener", DEFAULT_URL_SHORTENER))
        )
        short_code = str(self.settings.get("link_code") or "").strip()
        try:
            if short_code:
                link = broker.resolve(short_code)
                service = link.service or requested_service
                if link.service and normalize_name(link.service) != normalize_name(
                    requested_service
                ):
                    LOG.info(
                        "Completing Sonos authentication for brokered service %s",
                        link.service,
                    )
                self.controller.complete_authentication(
                    service, link.code, link.device_id
                )
                self.settings["link_code"] = ""
                self.settings.store()
                try:
                    broker.delete(short_code)
                except requests.RequestException as error:
                    # Authentication already succeeded. A stale short link is
                    # preferable to reporting a false authentication failure.
                    LOG.warning(
                        "Unable to remove completed Sonos authentication link: %s",
                        error,
                    )
                self.speak_dialog("sonos.authenticated")
                return

            provider, registration_url = self.controller.begin_authentication(
                requested_service
            )
            if not registration_url:
                self.speak_dialog("sonos.authenticated")
                return
            short_code = broker.create(
                registration_url,
                provider.link_code,
                provider.link_device_id,
                provider.service_name,
            )
            spoken_code = ". ".join(
                self.nato_dict.get(character.upper(), character)
                for character in short_code
            )
            self.speak_dialog("sonos.link_code", data={"code": spoken_code}, wait=True)
        except AuthenticationNotSupportedError:
            self.speak_dialog(
                "error.auth.unsupported", data={"service": requested_service}
            )
        except ServiceNotFoundError:
            self.speak_dialog("error.support", data={"service": requested_service})
        except NoSpeakersError:
            self.speak_dialog("error.discovery")
        except (ValueError, KeyError):
            self.speak_dialog("error.code", data={"code": short_code})
        except requests.RequestException as error:
            LOG.warning("Sonos authentication broker failed: %s", error)
            self.speak_dialog("error.urlshortener")
        except (OSError, SoCoException) as error:
            LOG.warning("Sonos authentication failed: %s", error)
            self.speak_dialog("error.auth", data={"service": requested_service})


__all__ = ["SonosControllerSkill"]
