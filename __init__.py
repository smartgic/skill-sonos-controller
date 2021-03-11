"""Sonos controller entrypoint skill
"""
from mycroft import MycroftSkill, intent_handler
from .utils import authentication, discovery, get_state, \
    get_category, subscribed_services, check_speaker, check_service, \
    run_command, get_track
from .search import search


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
        self.service = self.settings.get('default_source', 'Music Library')
        self.code = self.settings.get('link_code')
        # Initiate NATO dict
        # https://en.wikipedia.org/wiki/NATO_phonetic_alphabet
        self.nato_dict = self.translate_namedvalues('codes')

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

    @ intent_handler('sonos.album.intent')
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

    @ intent_handler('sonos.track.intent')
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

    @ intent_handler('sonos.command.intent')
    def handle_command(self, message):
        """Handle the commands to pass to Sonos devices triggered by intents

        The list of the available commands is registered withing the
        command.entity file.

        :param message: List of registered utterances
        :type message: dict
        """
        get_command = message.data.get('command')
        speaker = message.data.get('speaker', False)
        device_name = None
        if speaker:
            # Check if the speaker exists before running the command
            device_name = check_speaker(self, speaker)

        # Translate command values from spoken language to English
        translation = self.translate_namedvalues('commands')
        command = None
        for vocal, translate in translation.items():
            self.log.debug('|||||||||| {}'.format(vocal))
            self.log.debug('########## {}'.format(translate))
            if vocal == get_command:
                command = translate

        self.log.debug('========== {}'.format(translation))
        self.log.debug('++++++++++ {}'.format(command))

        if command == 'pause':
            run_command(self, 'pause', device_name)
        elif command == 'stop music':
            run_command(self, 'stop', device_name)
        elif command == 'resume music':
            run_command(self, 'play', device_name, 'PAUSED_PLAYBACK')
        elif command in ('louder', 'volume up', 'much louder'):
            value = 10
            if command == 'much louder':
                value = 30
            run_command(self, 'vol-up', device_name, extras=value)
        elif command in ('volume down', 'quieter', 'much quieter'):
            value = 10
            if command == 'much quieter':
                value = 30
            run_command(self, 'vol-down', device_name, extras=value)
        elif command == 'what is playing':
            get_track(self, device_name)
        elif command in ('next music', 'previous music'):
            cmd = 'next'
            if command == 'previous music':
                cmd = 'previous'
            run_command(self, cmd, device_name)

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
