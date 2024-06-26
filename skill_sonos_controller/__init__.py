"""Sonos controller entrypoint skill
"""

import logging
from ovos_bus_client.message import Message
from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills import OVOSSkill
from .utils import (
    authentication,
    discovery,
    subscribed_services,
    check_service,
    run_command,
    get_track_info,
    volume,
    get_volume,
    speaker_info,
)
from .search import search
from .constants import DEFAULT_VOL_INCREMENT, LOUDER_QUIETER


class SonosControllerSkill(OVOSSkill):
    """This is the place where all the magic happens for the Sonos
    controller skill.
    """

    @classproperty
    def runtime_requirements(self):
        """Check for skill functionalities requirements before trying to
        start the skill.
        """
        return RuntimeRequirements(
            internet_before_load=True,
            network_before_load=True,
            gui_before_load=False,
            requires_internet=True,
            requires_network=True,
            requires_gui=False,
            no_internet_fallback=True,
            no_network_fallback=True,
            no_gui_fallback=True,
        )

    def _setup(self):
        """Provision initialized variables and retrieve configuration
        from settings.json file.
        """
        # By default, the Music Library service is used
        self.service = self.settings.get("default_source", "music library")
        self.code = self.settings.get("link_code")
        # Initiate NATO dict
        # https://en.wikipedia.org/wiki/NATO_phonetic_alphabet
        self.nato_dict = self.resources.load_named_value_file("codes")
        self.duck = self.settings.get("duck", False)
        self.playing_confirmation = self.settings.get("playing_confirmation", False)
        self.searching_confirmation = self.settings.get("searching_confirmation", True)

        if self.duck:
            # Manage Sonos volume when wakeword is detected
            # https://openvoiceos.github.io/message_spec/dinkum/
            self.add_event("recognizer_loop:record_begin", self._handle_duck_volume)
            self.add_event("recognizer_loop:record_end", self._handle_unduck_volume)

        # Handle events sent by Mycroft playback skill
        # https://openvoiceos.github.io/message_spec/ovos_audio/#listens-to_1
        self.add_event("mycroft.audio.service.stop", self._handle_stop_music)
        self.add_event("mycroft.audio.service.next", self._handle_next_music)
        self.add_event("mycroft.audio.service.prev", self._handle_previous_music)
        self.add_event("mycroft.audio.service.pause", self._handle_pause_music)
        self.add_event("mycroft.audio.service.resume", self._handle_resume_music)

    @intent_handler("sonos.discovery.intent")
    def _handle_speaker_discovery(self, _):
        """Handle the Sonos devices discovery triggered by intents

        It's only used by the user to get the device names, the main discovery
        is automatically triggered during the skill initialization.
        """
        discovery(self)
        if self.speakers:
            self.speak_dialog("sonos.discovery", data={"total": len(self.speakers)})
            list_device = self.ask_yesno("sonos.list")
            if list_device == "yes":
                for speaker in self.speakers:
                    self.speak(speaker.player_name.lower())

    @intent_handler("sonos.speaker.info.intent")
    def _handle_speaker_info(self, message: Message):
        """Handle the Sonos devices information triggered by intents"""
        speaker_info(self, message.data.get("speaker"), message.data.get("detailed"))

    @intent_handler("sonos.service.intent")
    def _handle_subscribed_services(self, _):
        """Handle the subscribed services listing triggerd by intents

        It's only used by the user to get the service that are subscribed by
        the Sonos devices (from the applications). The service detection is
        performed during the skill initialization.

        :return: A list of services
        :rtype: list
        """
        if self.services:
            self.speak_dialog("sonos.service", data={"total": len(self.services)})
            list_service = self.ask_yesno("sonos.list")
            if list_service == "yes":
                for service in self.services:
                    self.speak(service)
            return self.services

        LOG.warning("no subscription found for any music service")
        self.speak_dialog("error.service")

        return None

    @intent_handler("sonos.playlist.intent")
    def _handle_playlist(self, message: Message):
        """Handle the playlist integration which include the search and
        the dispatch on the Sonos speakers(s).

        :param message: List of registered utterances
        :type message: dict
        """
        service = self.service
        playlist = message.data.get("playlist")
        speaker = message.data.get("speaker")
        if message.data.get("service"):
            service = check_service(self, message.data.get("service"))

        search(self, service, speaker, "playlists", playlist=playlist)

    @intent_handler("sonos.podcast.intent")
    def _handle_podcast(self, message: Message):
        """Handle the podcast integration which include the search and
        the dispatch on the Sonos speakers(s).

        :param message: List of registered utterances
        :type message: dict
        """
        service = self.service
        podcast = message.data.get("podcast")
        speaker = message.data.get("speaker")
        if message.data.get("service"):
            service = check_service(self, message.data.get("service"))

        search(self, service, speaker, "podcasts", podcast=podcast)

    @intent_handler("sonos.album.intent")
    def _handle_album(self, message: Message):
        """Handle the album integration which include the search and
        the dispatch on the Sonos speakers(s).

        :param message: List of registered utterances
        :type message: dict
        """
        service = self.service
        artist = None
        album = message.data.get("album")
        speaker = message.data.get("speaker")
        if message.data.get("service"):
            service = check_service(self, message.data.get("service"))
        if message.data.get("artist"):
            artist = message.data.get("artist")

        search(self, service, speaker, "albums", artist=artist, album=album)

    @intent_handler("sonos.track.intent")
    def _handle_track(self, message: Message):
        """Handle the track integration which include the search and
        the dispatch on the Sonos speakers(s).

        :param message: List of registered utterances
        :type message: dict
        """
        service = self.service
        artist = None
        track = message.data.get("track")
        speaker = message.data.get("speaker")
        if message.data.get("service"):
            service = check_service(self, message.data.get("service"))
        if message.data.get("artist"):
            artist = message.data.get("artist")

        search(self, service, speaker, "tracks", artist=artist, track=track)

    @intent_handler("sonos.pause.music.intent")
    def _handle_pause_music(self, message: Message):
        """Handle pause music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command="pause", speaker=message.data.get("speaker"))

    @intent_handler("sonos.stop.music.intent")
    def _handle_stop_music(self, message: Message):
        """Handle stop music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command="stop", speaker=message.data.get("speaker"))

    @intent_handler("sonos.resume.music.intent")
    def _handle_resume_music(self, message: Message):
        """Handle resume music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(
            self,
            command="play",
            speaker=message.data.get("speaker"),
            state="PAUSED_PLAYBACK",
        )

    @intent_handler("sonos.next.music.intent")
    def _handle_next_music(self, message: Message):
        """Handle next music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command="next", speaker=message.data.get("speaker"))

    @intent_handler("sonos.previous.music.intent")
    def _handle_previous_music(self, message: Message):
        """Handle previous music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command="previous", speaker=message.data.get("speaker"))

    @intent_handler("sonos.volume.up.intent")
    def _handle_volume_up(self, message: Message):
        """Handle volume up command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        volume(
            self,
            way="vol-up",
            speaker=message.data.get("speaker"),
            value=DEFAULT_VOL_INCREMENT,
        )

    @intent_handler("sonos.volume.down.intent")
    def _handle_volume_down(self, message: Message):
        """Handle volume down command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        volume(
            self,
            way="vol-down",
            speaker=message.data.get("speaker"),
            value=DEFAULT_VOL_INCREMENT,
        )

    @intent_handler("sonos.volume.louder.intent")
    def _handle_volume_louder(self, message: Message):
        """Handle volume louder command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        volume(
            self,
            way="vol-up",
            speaker=message.data.get("speaker"),
            value=LOUDER_QUIETER,
        )

    @intent_handler("sonos.volume.quieter.intent")
    def _handle_volume_quieter(self, message: Message):
        """Handle volume quieter command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        volume(
            self,
            way="vol-down",
            speaker=message.data.get("speaker"),
            value=LOUDER_QUIETER,
        )

    def _handle_duck_volume(self, message: Message):
        """Handle the duck volume on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        get_volume(self)
        volume(
            self,
            way="vol-down",
            speaker=message.data.get("speaker"),
            value=DEFAULT_VOL_INCREMENT,
        )

    def _handle_unduck_volume(self, message: Message):
        """Handle the unduck volume on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        volume(
            self,
            way="unduck",
            speaker=message.data.get("speaker"),
            value=self.current_volume,
        )
        self.current_volume = {}

    @intent_handler("sonos.shuffle.on.intent")
    def _handle_shuffle_on(self, message: Message):
        """Handle shuffe mode on command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(
            self,
            command="mode",
            speaker=message.data.get("speaker"),
            extras="shuffle_norepeat",
        )

    @intent_handler("sonos.shuffle.off.intent")
    def _handle_shuffle_off(self, message: Message):
        """Handle shuffe mode off command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(
            self, command="mode", speaker=message.data.get("speaker"), extras="normal"
        )

    @intent_handler("sonos.repeat.on.intent")
    def _handle_repeat_on(self, message: Message):
        """Handle repeat mode on command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(
            self,
            command="mode",
            speaker=message.data.get("speaker"),
            extras="repeat_all",
        )

    @intent_handler("sonos.repeat.off.intent")
    def _handle_repeat_off(self, message: Message):
        """Handle repeat mode off command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(
            self, command="mode", speaker=message.data.get("speaker"), extras="normal"
        )

    @intent_handler("sonos.what.is.playing.intent")
    def _handle_what_is_playing(self, message: Message):
        """Handle what is playing command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        get_track_info(self, message.data.get("speaker"), False)

    @intent_handler("sonos.which.artist.intent")
    def _handle_which_artist_playing(self, message: Message):
        """Handle which artist is playing command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        get_track_info(self, message.data.get("speaker"), True)

    def initialize(self):
        """The initialize method is called after the Skill is fully
        constructed and registered with the system. It is used to perform
        any final setup for the Skill including accessing Skill settings.
        https://openvoiceos.github.io/ovos-technical-manual/skill_structure/#initialize
        """
        # Initialize variables with empty or None values
        self.speakers = []
        self.services = []
        self.service = None
        self.nato_dict = None
        self.code = None
        self.duck = None
        self.playing_confirmation = None
        self.current_volume = {}

        # Override SoCo logging level for discovery and services
        logging.getLogger("soco.discovery").setLevel(logging.WARN)
        logging.getLogger("soco.services").setLevel(logging.WARN)

        self.register_entity_file("service.entity")
        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()

    def on_settings_changed(self):
        """Each Mycroft device will check for updates to a users settings
        regularly, and write these to the Skills settings.json.
        https://openvoiceos.github.io/ovos-technical-manual/skill_settings
        """
        self._setup()
        authentication(self)
        discovery(self)
        subscribed_services(self)
