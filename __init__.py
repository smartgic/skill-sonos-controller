from mycroft import MycroftSkill, intent_handler
from soco.discovery import by_name
from soco import exceptions
from random import choice
from urllib.parse import unquote
from .utils import authentication, discovery, get_state, \
    get_category, subscribed_services, check_speaker, check_service, \
    run_command, get_track
from .search import search


class SonosController(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

        # Initialize variables with empty or None values
        self.speakers = []
        self.services = []
        self.service = None
        self.nato_dict = None

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
        else:
            self.log.warning('no subscription found for any music service')
            self.speak_dialog('error.service')

    @intent_handler('sonos.playlist.intent')
    def handle_playlist(self, message):
        service = self.service
        playlist = message.data.get('playlist')
        speaker = message.data.get('speaker')
        if message.data.get('service'):
            service = check_service(self, message.data.get('service'))

        self.log.debug(">>>>>>>>>>>> {}".format(speaker))
        search(self, service, speaker, 'playlists', playlist=playlist)

    @ intent_handler('sonos.album.intent')
    def handle_album(self, message):
        service = self.service
        if message.data.get('service'):
            service = check_service(self, message.data.get('service'))
        album = message.data.get('album')
        speaker = message.data.get('speaker')
        if (
            self.services and service in self.services or
            service == 'Music Library'
        ):
            device_name = check_speaker(self, speaker)
            if device_name:
                check_category = get_category(self, service, 'albums')
                if check_category:
                    try:
                        picked = None
                        title = None
                        device = by_name(device_name)
                        device.clear_queue()
                        if service == 'Music Library':
                            albs = {}
                            for alb in check_category.get_albums(
                                    search_term=album,
                                    complete_result=True):
                                albs[alb.to_dict()['title']] = alb.to_dict()[
                                    'resources'][0]['uri']
                            if albs:
                                picked = choice(list(albs.keys()))
                                device.add_uri_to_queue(albs[picked])
                                title = picked
                            else:
                                self.log.warning('album not found')
                                self.speak_dialog('error.album', data={
                                                  'album': album})
                                return
                        else:
                            albs = check_category.search(
                                'albums', album)
                            picked = choice(albs)
                            device.add_to_queue(picked)
                            title = picked.title

                        device.play_from_queue(0)

                        self.log.debug(
                            '{} album from {} on {} started'.format(
                                picked, service, speaker))
                        self.speak_dialog('sonos.album', data={
                            'album': title, 'service': service,
                            'speaker': speaker})
                    except exceptions.SoCoException as e:
                        self.log.error(e)
                else:
                    self.log.warning(
                        'there is no album category for this service')
                    self.speak_dialog('error.category', data={
                        'category': album})

    @ intent_handler('sonos.track.intent')
    def handle_track(self, message):
        service = self.service
        artist = None
        if message.data.get('service'):
            service = check_service(self, message.data.get('service'))
        if message.data.get('artist'):
            artist = message.data.get('artist')
        track = message.data.get('track')
        speaker = message.data.get('speaker')
        if (
            self.services and service in self.services or
            service == 'Music Library'
        ):
            device_name = check_speaker(self, speaker)
            if device_name:
                check_category = get_category(self, service, 'tracks')
                if check_category:
                    try:
                        picked = None
                        title = None
                        device = by_name(device_name)
                        device.clear_queue()
                        if service == 'Music Library':
                            if artist:
                                trks = {}
                                for trk in check_category.search_track(
                                        artist=artist,
                                        track=track):
                                    trks[
                                        trk.to_dict()['title']
                                    ] = trk.to_dict()[
                                        'resources'][0]['uri']
                                if trks:
                                    picked = choice(list(trks.keys()))
                                    device.add_uri_to_queue(trks[picked])
                                    title = picked
                                else:
                                    self.log.warning('track not found')
                                    self.speak_dialog('error.track', data={
                                        'track': track, 'artist': artist})
                                    return
                            else:
                                trks = {}
                                for trk in check_category.get_tracks(
                                        search_term=track,
                                        complete_result=True):
                                    trks[
                                        trk.to_dict()['title']
                                    ] = trk.to_dict()[
                                        'resources'][0]['uri']
                                if trks:
                                    picked = choice(list(trks.keys()))
                                    device.add_uri_to_queue(trks[picked])
                                    title = picked
                                else:
                                    self.log.warning('track not found')
                                    self.speak_dialog('error.track', data={
                                        'track': track})
                                    return
                        else:
                            trks = check_category.search(
                                'tracks', track)
                            picked = choice(trks)
                            device.add_to_queue(picked)
                            title = picked.title

                        device.play_from_queue(0)

                        self.log.debug(
                            '{} from {} on {} started'.format(
                                picked, service, speaker))
                        self.speak_dialog('sonos.track', data={
                            'track': title, 'service': service,
                            'speaker': speaker})
                    except exceptions.SoCoException as e:
                        self.log.error(e)
                else:
                    self.log.warning(
                        'there is no tracks category for this service')
                    self.speak_dialog('error.category', data={
                        'category': 'tracks'})

    @ intent_handler('sonos.command.intent')
    def handle_command(self, message):
        """Handle the commands to pass to Sonos devices triggered by intents

        The list of the available commands is registered withing the
        command.entity file.

        Command could be run with or without speaker mention.
        """
        command = message.data.get('command')
        speaker = message.data.get('speaker', False)
        device_name = None
        if speaker:
            # Check if the speaker exists before running the command
            device_name = check_speaker(self, speaker)

        if command == 'pause':
            run_command(self, 'pause', device_name)
        elif command == 'stop music':
            run_command(self, 'stop', device_name)
        elif command == 'restart music' or command == 'resume music':
            run_command(self, 'stop', device_name, 'stopped')
        elif (
            command == 'louder' or command == 'volume up' or
            command == 'turn up volume' or command == 'much louder'
        ):
            value = 10
            if command == 'much louder':
                value = 30
            run_command(self, 'vol-up', device_name, extras=value)
        elif (
            command == 'volume down' or command == 'quieter' or
            command == 'turn down volume' or command == 'much quieter'
        ):
            value = 10
            if command == 'much quieter':
                value = 30
            run_command(self, 'vol-down', device_name, extras=value)
        elif command == 'what is playing':
            get_track(self, device_name)
        elif command == 'next music' or command == 'previous music':
            cmd = 'next'
            if command == 'previous music':
                cmd = 'previous'
            run_command(self, cmd, device_name)

    def _entity(self):
        """Register the Padatious entities
        """
        self.register_entity_file('service.entity')
        self.register_entity_file('command.entity')

    def initialize(self):
        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()

    def on_settings_changed(self):
        self._setup()
        authentication(self)
        self._entity()
        discovery(self)
        subscribed_services(self)


def create_skill():
    return SonosController()
