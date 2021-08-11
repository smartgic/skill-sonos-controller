"""Sonos controller entrypoint skill
"""
import logging
from mycroft import MycroftSkill, intent_handler
from mycroft.configuration import Configuration
from .utils import authentication, discovery, subscribed_services, \
    check_service, run_command, get_track
from .search import search
from .constants import DEFAULT_VOL_INCREMENT, LOUDER_QUIETER


class SonosController(MycroftSkill):
    """This is the place where all the magic happens for the Sonos
    controller skill.
    """
    def __init__(self):
        """Constructor method
        """
        MycroftSkill.__init__(self)

        # Initialize variables with empty or None values
        self.speakers = []
        self.services = []
        self.service = None
        self.nato_dict = None
        self.settings_change_callback = None
        self.code = None
        self.duck = None

        # Override SoCo logging level to match Mycroft configuration
        config = Configuration.get(remote=False)
        logging.getLogger(__name__).setLevel(config.get('log_level', 'INFO'))

    def _setup(self):
        """Provision initialized variables and retrieve configuration
        from home.mycroft.ai.
        """
        # By default the Music Library service is used
        self.service = self.settings.get('default_source', 'music library')
        self.code = self.settings.get('link_code')
        # Initiate NATO dict
        # https://en.wikipedia.org/wiki/NATO_phonetic_alphabet
        self.nato_dict = self.translate_namedvalues('codes')
        self.duck = self.settings.get('duck')

        if self.duck:
            # Manage Sonos volume when wakeword is detected
            # https://tinyurl.com/244286w8
            self.add_event("recognizer_loop:record_begin",
                           self._handle_volume_down)
            self.add_event("recognizer_loop:record_end",
                           self._handle_volume_up)

    @intent_handler('sonos.discovery.intent')
    def _handle_speaker_discovery(self):
        """Handle the Sonos devices discovery triggered by intents

        It's only used by the user to get the device names, the main discovery
        is automatically triggered during the skill initialization.
        """
        discovery(self)
        if self.speakers:
            self.speak_dialog('sonos.discovery', data={
                              'total': len(self.speakers)})
            list_device = self.ask_yesno('sonos.list')
            if list_device == 'yes':
                for speaker in self.speakers:
                    self.speak(speaker.player_name.lower())

    @intent_handler('sonos.service.intent')
    def _handle_subscribed_services(self):
        """Handle the subscribed services listing triggerd by intents

        It's only used by the user to get the service that are subscribed by
        the Sonos devices. The service detection is performed during the
        skill initialization.

        :return: A list of services
        :rtype: list
        """
        if self.services:
            self.speak_dialog('sonos.service', data={
                              'total': len(self.services)})
            list_service = self.ask_yesno('sonos.list')
            if list_service == 'yes':
                for service in self.services:
                    self.speak(service)
            return self.services

        self.log.warning('no subscription found for any music service')
        self.speak_dialog('error.service')

        return None

    @intent_handler('sonos.playlist.intent')
    def _handle_playlist(self, message):
        """Handle the playlist integration which include the search and
        the dispatch on the Sonos speakers(s).

        :param message: List of registered utterances
        :type message: dict
        """
        service = self.service
        playlist = message.data.get('playlist')
        speaker = message.data.get('speaker')
        if message.data.get('service'):
            service = check_service(self, message.data.get('service'))

        search(self, service, speaker, 'playlists', playlist=playlist)

    @intent_handler('sonos.album.intent')
    def _handle_album(self, message):
        """Handle the album integration which include the search and
        the dispatch on the Sonos speakers(s).

        :param message: List of registered utterances
        :type message: dict
        """
        service = self.service
        artist = None
        album = message.data.get('album')
        speaker = message.data.get('speaker')
        if message.data.get('service'):
            service = check_service(self, message.data.get('service'))
        if message.data.get('artist'):
            artist = message.data.get('artist')

        search(self, service, speaker, 'albums', artist=artist, album=album)

    @intent_handler('sonos.track.intent')
    def _handle_track(self, message):
        """Handle the track integration which include the search and
        the dispatch on the Sonos speakers(s).

        :param message: List of registered utterances
        :type message: dict
        """
        service = self.service
        artist = None
        track = message.data.get('track')
        speaker = message.data.get('speaker')
        if message.data.get('service'):
            service = check_service(self, message.data.get('service'))
        if message.data.get('artist'):
            artist = message.data.get('artist')

        search(self, service, speaker, 'tracks', artist=artist, track=track)

    @intent_handler('sonos.pause.music.intent')
    def _handle_pause_music(self, message):
        """Handle pause music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='pause',
                    speaker=message.data.get('speaker'))

    @intent_handler('sonos.stop.music.intent')
    def _handle_stop_music(self, message):
        """Handle stop music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='stop',
                    speaker=message.data.get('speaker'))

    @intent_handler('sonos.resume.music.intent')
    def _handle_resume_music(self, message):
        """Handle resume music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='play',
                    speaker=message.data.get('speaker'),
                    state='PAUSED_PLAYBACK')

    @intent_handler('sonos.next.music.intent')
    def _handle_next_music(self, message):
        """Handle next music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='next',
                    speaker=message.data.get('speaker'))

    @intent_handler('sonos.previous.music.intent')
    def _handle_previous_music(self, message):
        """Handle previous music command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='previous',
                    speaker=message.data.get('speaker'))

    @intent_handler('sonos.volume.up.intent')
    def _handle_volume_up(self, message):
        """Handle volume up command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='vol-up',
                    speaker=message.data.get('speaker'),
                    extras=DEFAULT_VOL_INCREMENT)

    @intent_handler('sonos.volume.down.intent')
    def _handle_volume_down(self, message):
        """Handle volume down command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='vol-down',
                    speaker=message.data.get('speaker'),
                    extras=DEFAULT_VOL_INCREMENT)

    @intent_handler('sonos.volume.louder.intent')
    def _handle_volume_louder(self, message):
        """Handle volume louder command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='vol-up',
                    speaker=message.data.get('speaker'),
                    extras=LOUDER_QUIETER)

    @intent_handler('sonos.volume.quieter.intent')
    def _handle_volume_quieter(self, message):
        """Handle volume quieter command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='vol-down',
                    speaker=message.data.get('speaker'),
                    extras=LOUDER_QUIETER)

    @intent_handler('sonos.shuffle.on.intent')
    def _handle_shuffle_on(self, message):
        """Handle shuffe mode on command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='mode',
                    speaker=message.data.get('speaker'),
                    extras='shuffle_norepeat')

    @intent_handler('sonos.shuffle.off.intent')
    def _handle_shuffle_off(self, message):
        """Handle shuffe mode off command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='mode',
                    speaker=message.data.get('speaker'),
                    extras='normal')

    @intent_handler('sonos.repeat.on.intent')
    def _handle_repeat_on(self, message):
        """Handle repeat mode on command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='mode',
                    speaker=message.data.get('speaker'),
                    extras='repeat_all')

    @intent_handler('sonos.repeat.off.intent')
    def _handle_repeat_off(self, message):
        """Handle repeat mode off command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        run_command(self, command='mode',
                    speaker=message.data.get('speaker'),
                    extras='normal')

    @intent_handler('sonos.what.is.playing.intent')
    def _handle_what_is_playing(self, message):
        """Handle what is playing command on Sonos speakers.

        :param message: Contains the utterance, the variables, etc...
        :type message: object
        """
        get_track(self, message.data.get('speaker'))

    def _entity(self):
        """Register the Padatious entitiies
        """
        self.register_entity_file('service.entity')

    def initialize(self):
        """The initialize method is called after the Skill is fully
        constructed and registered with the system. It is used to perform
        any final setup for the Skill including accessing Skill settings.
        https://tinyurl.com/4pevkdhj
        """
        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()

    def on_settings_changed(self):
        """Each Mycroft device will check for updates to a users settings
        regularly, and write these to the Skills settings.json.
        https://tinyurl.com/f2bkymw
        """
        self._setup()
        authentication(self)
        self._entity()
        discovery(self)
        subscribed_services(self)


def create_skill():
    """Main function to register the skill
    """
    return SonosController()
