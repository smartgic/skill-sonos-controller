from mycroft import MycroftSkill, intent_handler
from soco import discover
from soco.music_services import MusicService
from soco.discovery import by_name
from soco import exceptions
from random import choice

SUPPORTED_SERVICES = ["Amazon Music", "Apple Music", "Deezer",
                      "Google Play Music", "Napster", "Plex", "Sonos Radio",
                      "SoundCloud", "Spotify", "TuneIn", "Wolfgangs Music",
                      "YouTube Music"]


class SonosController(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
        self.speakers = []
        self.services = []
        self.service = 'Spotify'

    def _discovery(self):
        try:
            self.speakers = discover()
        except exceptions.SoCoException as e:
            self.log.error(e)

        if not self.speakers:
            self.log.warning(
                'I could not find any devices on your network')
            self.speak_dialog('error.disovery')
        else:
            self.log.info(
                '{} device(s) found'.format(len(self.speakers)))
            self.log.debug(self.speakers)

    def _get_state(self, speaker):
        device = self._check_speaker(speaker)
        return device.get_current_transport_info()['current_transport_state']

    def _subscribed_services(self):
        try:
            # Commented until SoCo integrates this method back
            # self.services = MusicService.get_subscribed_services_names()
            self.services = ['Spotify', 'Amazon Music', 'Wolfgangs Music']
            return self.services
        except exceptions.SoCoException as e:
            self.log.error(e)

    def _check_category(self, service, category):
        try:
            provider = MusicService(service)
            for categories in provider.available_search_categories:
                if category in categories:
                    return provider
        except exceptions.SoCoException as e:
            self.log.error(e)

        self.log.warning('no {} category for this service'.format(category))
        self.speak_dialog('error.category', data={'category': category})

    def _check_speaker(self, speaker):
        for device in self.speakers:
            if speaker in device.player_name.lower():
                self.log.debug('{} speaker has been found'.format(device))
                return device.player_name

        self.log.warning('{} speaker not found'.format(speaker))
        self.speak_dialog('error.speaker', data={'speaker': speaker})

    def _check_service(self, service):
        for svc in SUPPORTED_SERVICES:
            if service in svc.lower():
                for subscription in self.services:
                    if service in subscription.lower():
                        self.log.debug('{} subscription found'.format(service))
                        return svc

        self.speak_dialog('error.support', data={'service': service})
        self.log.error('{} service not supported'.format(service))

    @intent_handler('sonos.discovery.intent')
    def handle_speaker_discovery(self, message):
        self._discovery()
        if self.speakers:
            self.speak_dialog('sonos.discovery', data={
                              'total': len(self.speakers)})
            list_device = self.ask_yesno('sonos.list')
            if list_device == 'yes':
                for speaker in self.speakers:
                    self.speak(speaker.player_name.lower())

    @intent_handler('sonos.service.intent')
    def handle_subscribed_services(self, message):
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
        if message.data.get('service'):
            service = self._check_service(message.data.get('service'))
        playlist = message.data.get('playlist')
        speaker = message.data.get('speaker')

        if self.services and service in self.services:
            device_name = self._check_speaker(speaker)
            if device_name:
                check_category = self._check_category(service, 'playlists')
                if check_category:
                    try:
                        playlists = check_category.search(
                            'playlists', playlist)
                        picked = choice(playlists)
                        device = by_name(device_name)
                        device.clear_queue()
                        device.add_to_queue(picked)
                        device.play_from_queue(0)

                        self.log.debug(
                            '{} playlist from {} on {} started'.format(
                                picked, service, speaker))
                        self.speak_dialog('sonos.playlist', data={
                            'playlist': picked.title, 'service': service,
                            'speaker': speaker})
                    except exceptions.SoCoException as e:
                        self.log.error(e)
                else:
                    self.log.warning(
                        'there is no playlist category for this service')
                    self.speak_dialog('error.category', data={
                        'category': playlist})

    @intent_handler('sonos.command.intent')
    def handle_command(self, message):
        command = message.data.get('command')
        speaker = message.data.get('speaker', False)
        if speaker:
            self.log.info(speaker)
            device_name = self._check_speaker(speaker)
            self.log.info(device_name)

        if command == "pause":
            try:
                if speaker:
                    device = by_name(device_name)
                    if self._get_state(device) == 'PLAYING':
                        device.pause()
                else:
                    for device in self.speakers:
                        if self._get_state(device) == 'PLAYING':
                            device.pause()
            except exceptions.SoCoException as e:
                self.log.error(e)

    def _entity(self):
        self.register_entity_file('service.entity')
        # self.register_entity_file('command.entity')

    def initialize(self):
        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()
        self._discovery()
        self._subscribed_services()
        self._entity()

    def on_settings_changed(self):
        return


def create_skill():
    return SonosController()
