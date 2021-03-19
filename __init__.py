"""Sonos controller entrypoint skill
"""
from mycroft import MycroftSkill, intent_handler
from .utils import authentication, discovery, get_state, \
    get_category, subscribed_services, check_speaker, check_service, \
    run_command
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
            self.add_event("recognizer_loop:record_begin", self._volume_down)
            self.add_event("recognizer_loop:record_end", self._volume_up)

    def _volume_down(self):
        """Reduce volume on Sonos when "recognizer_loop:wakeword" is
        detected in the bus.
        """
        run_command(self, command='vol-down', speaker=None,
                    extras=DEFAULT_VOL_INCREMENT)

    def _volume_up(self):
        """Raise volume on Sonos when "recognizer_loop:record_end" is
        detected in the bus.
        """
        run_command(self, command='vol-up', speaker=None,
                    extras=DEFAULT_VOL_INCREMENT)

    @intent_handler('sonos.discovery.intent')
    def handle_speaker_discovery(self):
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
    def handle_subscribed_services(self):
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
    def handle_playlist(self, message):
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
    def handle_album(self, message):
        """Handle the album integration which include the search and
        the dispatch on the Sonos speakers(s).

        :param message: List of registered utterances
        :type message: dict
        """
        service = self.service
        album = message.data.get('album')
        speaker = message.data.get('speaker')
        if message.data.get('service'):
            service = check_service(self, message.data.get('service'))

        search(self, service, speaker, 'albums', album=album)

    @intent_handler('sonos.track.intent')
    def handle_track(self, message):
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

    @intent_handler('sonos.command.intent')
    def handle_command(self, message):
        """Handle the commands to pass to Sonos devices triggered by intents

        The list of the available commands is registered withing the
        command.entity file.

        :param message: List of registered utterances
        :type message: dict
        """
        get_command = message.data.get('command')
        speaker = message.data.get('speaker')
        device_name = None
        command = None

        self.log.debug('==== Entering in handle_command() ====')
        self.log.debug('==== get_command: {} ===='.format(get_command))
        self.log.debug('==== speaker: {} ===='.format(speaker))
        self.log.debug('==== message dict: {} ===='.format(message))

        if speaker:
            self.log.debug('==== speaker is defined ====')
            # Check if the speaker exists before running the command
            device_name = check_speaker(self, speaker)
            self.log.debug('==== device_name: {} ===='.format(device_name))

        # Translate command values from spoken language to English
        translation = self.translate_namedvalues('commands')
        for vocal, translate in translation.items():
            if vocal == get_command:
                command = translate

        self.log.debug('==== command: {} ===='.format(command))

        # List of supported commands with their arguments handle by the
        # run_command() function.
        commands = [
            {'pause': {'command': 'pause', 'device': device_name}},
            {'stop': {'command': 'stop', 'device': device_name}},
            {'resume': {'command': 'play',
                        'device': device_name,
                        'state': 'PAUSED_PLAYBACK'}},
            {'louder': {'command': 'vol-up', 'device': device_name,
                        'extras': DEFAULT_VOL_INCREMENT}},
            {'volume up': {'command': 'vol-up', 'device': device_name,
                           'extras': DEFAULT_VOL_INCREMENT}},
            {'much louder': {'command': 'vol-up', 'device': device_name,
                             'extras': LOUDER_QUIETER}},
            {'volume down': {'command': 'vol-down', 'device': device_name,
                             'extras': DEFAULT_VOL_INCREMENT}},
            {'quieter': {'command': 'vol-down', 'device': device_name,
                         'extras': DEFAULT_VOL_INCREMENT}},
            {'much quieter': {'command': 'vol-down', 'device': device_name,
                              'extras': LOUDER_QUIETER}},
            {'what is playing': {'command': 'get-track',
                                 'device': device_name}},
            {'next': {'command': 'next', 'device': device_name}},
            {'previous': {'command': 'previous', 'device': device_name}},
            {'shuffle on': {'command': 'mode',
                            'device': device_name,
                            'extras': 'shuffle_norepeat'}},
            {'shuffle off': {'command': 'mode',
                             'device': device_name, 'extras': 'normal'}},
            {'repeat on': {'command': 'mode',
                           'device': device_name, 'extras': 'repeat_all'}},
            {'repeat off': {'command': 'mode',
                            'device': device_name, 'extras': 'normal'}}
        ]

        for i in commands:
            if command in i:
                self.log.debug('==== command found: {} ===='.format(command))
                self.log.debug('==== commands dict: {} ===='.format(i))
                # Execute the requested command based on provided parameters
                run_command(self, command=i[command]['command'],
                            speaker=i[command]['device'],
                            state=i[command].get('state', 'playing'),
                            extras=i[command].get('extras', None))

    @intent_handler('sonos.what.is.playing.intent')
    def handle_what_is_playing(self, message):
        speaker = message.data.get('speaker')
        device_name = None
        if speaker:
            # Check if the speaker exists before running the command
            device_name = check_speaker(self, speaker)
        run_command(self, command='get-track', speaker=device_name,)

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
