from mycroft import MycroftSkill, intent_handler
from soco import discover
from soco.music_library import MusicLibrary
from soco.music_services import MusicService
from soco.discovery import by_name
from soco import exceptions
from random import choice
from urllib.parse import unquote
from .constants import REQUIRED_AUTHENTICATION, TOKEN_FILE, \
    SUPPORTED_LIBRARY_CATEGORIES, SUPPORTED_SERVICES
import os
import re


class SonosController(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

        self.speakers = []
        self.services = []
        self.service = None
        self.nato_dict = None

    """
    Register some default values to empty initialized variables
    """

    def _setup(self):
        # By default the Music Library service is used
        self.service = self.settings.get('default_source', 'Music Library')
        self.code = self.settings.get('link_code')
        # Initiate NATO dict
        # https://en.wikipedia.org/wiki/NATO_phonetic_alphabet
        self.nato_dict = self.translate_namedvalues('codes')

    def _authentication(self):
        # This path is required by SoCo Python library and can't be changed
        token_file = os.getenv('HOME') + TOKEN_FILE

        if self.service in REQUIRED_AUTHENTICATION:
            provider = MusicService(self.service)

            if not os.path.isfile(token_file) and self.code != '':
                try:
                    provider.device_or_app_link_auth_part2(self.code)
                    self.speak_dialog('sonos.authenticated')
                except exceptions.SoCoException as e:
                    self.log.error(e)
            elif not os.path.isfile(token_file):
                try:
                    _, link_code = provider.device_or_app_link_auth_part1()
                    self.log.info('Sonos link code: {}'.format(link_code))
                    data = {"slash": '. '.join(
                        map(self.nato_dict.get, link_code)) + '.'}
                    self.speak_dialog('sonos.link_code', data={
                                      'link_code': data})
                except exceptions.SoCoException as e:
                    self.log.error(e)

    """
    Discover Sonos devices registered on the local network and
    add the speakers to a list.
    https://tinyurl.com/kahwd11y
    """

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

    """
    Get the current playback state.
    https://tinyurl.com/5az3lcb5
    """

    def _get_state(self, speaker):
        dev = by_name(speaker)
        if dev:
            return dev.get_current_transport_info()['current_transport_state']

    """
    Get a list of the names of all subscribed music services.
    https://tinyurl.com/zu3ymsd9
    """

    def _subscribed_services(self):
        try:
            # Commented until SoCo integrates this method back
            # self.services = MusicService.get_subscribed_services_names()
            self.services = ['Spotify', 'Amazon Music',
                             'Wolfgangs Music', 'Music Library']
            return self.services
        except exceptions.SoCoException as e:
            self.log.error(e)

    """
    Check if a category is available for a specific service or library.
    https://tinyurl.com/1plj5lzv
    """

    def _check_category(self, service, category):
        try:
            provider = None
            available_categories = None
            if service == 'Music Library':
                provider = MusicLibrary()
                available_categories = SUPPORTED_LIBRARY_CATEGORIES
            else:
                provider = MusicService(service)
                available_categories = provider.available_search_categories

            for categories in available_categories:
                if category in categories:
                    return provider
        except exceptions.SoCoException as e:
            self.log.error(e)

        self.log.warning('no {} category for this service'.format(category))
        self.speak_dialog('error.category', data={'category': category})

    """
    Check if the speaker is part of the discovered speakers and checks
    if it's part of a group. If part of a group then retrieve the coordinator
    of this group.
    https://tinyurl.com/4chwrb6u
    """

    def _check_speaker(self, speaker):
        for device in self.speakers:
            if speaker in device.player_name.lower():
                if len(device.group.members) > 1:
                    coordinator = device.group.coordinator
                    self.log.debug(
                        '{} is part of a group, {} is coordinator'.format(
                            device, coordinator.player_name))
                    return coordinator.player_name

                self.log.debug('{} speaker has been found'.format(device))
                return device.player_name

        self.log.warning('{} speaker not found'.format(speaker))
        self.speak_dialog('error.speaker', data={'speaker': speaker})

    """
    Check if the spoken service is part of the supported services and
    if it is check if authentication is required.
    """

    def _check_service(self, service):
        for svc in SUPPORTED_SERVICES:
            if service in svc.lower():
                for subscription in self.services:
                    if service in subscription.lower():
                        r_a = map(str.lower, set(REQUIRED_AUTHENTICATION))
                        if service in r_a:
                            token_file = os.getenv('HOME') + TOKEN_FILE
                            if not os.path.isfile(token_file):
                                self.log.warning(
                                    '{} requires authentication'.format(
                                        service))
                                self.speak_dialog('error.authentication', data={
                                    'service': service})
                                return
                        self.log.debug('{} subscription found'.format(
                            service))
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
        if (
            self.services and service in self.services or
            service == 'Music Library'
        ):
            device_name = self._check_speaker(speaker)
            if device_name:
                check_category = self._check_category(service, 'playlists')
                if check_category:
                    try:
                        picked = None
                        title = None
                        device = by_name(device_name)
                        device.clear_queue()
                        if service == 'Music Library':
                            pls = {}
                            for pl in check_category.get_playlists(
                                    search_term=playlist,
                                    complete_result=True):
                                pls[pl.to_dict()['title']] = pl.to_dict()[
                                    'resources'][0]['uri']
                            if pls:
                                picked = choice(list(pls.keys()))
                                device.add_uri_to_queue(pls[picked])
                                title = picked
                            else:
                                self.log.warning('playlist not found')
                                self.speak_dialog('error.playlist', data={
                                                  'playlist': playlist})
                                return
                        else:
                            pls = check_category.search(
                                'playlists', playlist)
                            picked = choice(pls)
                            device.add_to_queue(picked)
                            title = picked.title

                        device.play_from_queue(0)

                        self.log.debug(
                            '{} playlist from {} on {} started'.format(
                                picked, service, speaker))
                        self.speak_dialog('sonos.playlist', data={
                            'playlist': title, 'service': service,
                            'speaker': speaker})
                    except exceptions.SoCoException as e:
                        self.log.error(e)
                else:
                    self.log.warning(
                        'there is no playlist category for this service')
                    self.speak_dialog('error.category', data={
                        'category': playlist})

    @intent_handler('sonos.album.intent')
    def handle_album(self, message):
        service = self.service
        if message.data.get('service'):
            service = self._check_service(message.data.get('service'))
        album = message.data.get('album')
        speaker = message.data.get('speaker')
        if (
            self.services and service in self.services or
            service == 'Music Library'
        ):
            device_name = self._check_speaker(speaker)
            if device_name:
                check_category = self._check_category(service, 'albums')
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

    @intent_handler('sonos.track.intent')
    def handle_track(self, message):
        service = self.service
        artist = None
        if message.data.get('service'):
            service = self._check_service(message.data.get('service'))
        if message.data.get('artist'):
            artist = message.data.get('artist')
        track = message.data.get('track')
        speaker = message.data.get('speaker')
        if (
            self.services and service in self.services or
            service == 'Music Library'
        ):
            device_name = self._check_speaker(speaker)
            if device_name:
                check_category = self._check_category(service, 'tracks')
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

    @intent_handler('sonos.command.intent')
    def handle_command(self, message):
        command = message.data.get('command')
        speaker = message.data.get('speaker', False)
        device_name = None
        if speaker:
            device_name = self._check_speaker(speaker)

        if command == 'pause':
            try:
                if speaker:
                    device = by_name(device_name)
                    if self._get_state(device.player_name) == 'PLAYING':
                        device.pause()
                else:
                    for device in self.speakers:
                        if self._get_state(device.player_name) == 'PLAYING':
                            device.pause()
            except exceptions.SoCoException as e:
                self.log.error(e)
        elif command == 'stop music':
            try:
                if speaker:
                    device = by_name(device_name)
                    if self._get_state(device.player_name) == 'PLAYING':
                        device.stop()
                else:
                    for device in self.speakers:
                        if self._get_state(device.player_name) == 'PLAYING':
                            device.stop()
            except exceptions.SoCoException as e:
                self.log.error(e)
        elif command == 'restart music' or command == 'resume music':
            try:
                if speaker:
                    device = by_name(device_name)
                    if self._get_state(device.player_name) == 'STOPPED':
                        device.play()
                else:
                    for device in self.speakers:
                        if self._get_state(device.player_name) == 'STOPPED':
                            device.play()
            except exceptions.SoCoException as e:
                self.log.error(e)
        elif (
            command == 'louder' or command == 'volume up' or
            command == 'turn up volume' or command == 'much louder'
        ):
            try:
                if speaker:
                    device = by_name(device_name)
                    if self._get_state(device.player_name) == 'PLAYING':
                        if command == 'much louder':
                            device.volume += 30
                        else:
                            device.volume += 10
                else:
                    for device in self.speakers:
                        if self._get_state(device.player_name) == 'PLAYING':
                            if command == 'much louder':
                                device.volume += 30
                            else:
                                device.volume += 10
            except exceptions.SoCoException as e:
                self.log.error(e)
        elif (
            command == 'volume down' or command == 'quieter' or
            command == 'turn down volume' or command == 'much quieter'
        ):
            try:
                if speaker:
                    device = by_name(device_name)
                    if self._get_state(device.player_name) == 'PLAYING':
                        if command == 'much quieter':
                            device.volume -= 30
                        else:
                            device.volume -= 10
                else:
                    for device in self.speakers:
                        if self._get_state(device.player_name) == 'PLAYING':
                            if command == 'much quieter':
                                device.volume -= 30
                            else:
                                device.volume -= 10
            except exceptions.SoCoException as e:
                self.log.error(e)
        elif command == 'what is playing':
            try:
                if speaker:
                    device = by_name(device_name)
                    if self._get_state(device.player_name) == 'PLAYING':
                        self.speak('{} by {}'.format(
                            device.get_current_track_info()['title'],
                            device.get_current_track_info()['artist']))
                    else:
                        self.speak_dialog('error.playing')
                else:
                    for device in self.speakers:
                        if self._get_state(device.player_name) == 'PLAYING':
                            if device.get_current_track_info()['title']:
                                self.speak('{} by {} on {}'.format(
                                    device.get_current_track_info()['title'],
                                    device.get_current_track_info()['artist'],
                                    device.player_name))
                            else:
                                self.speak_dialog('warning.playing')
                        else:
                            self.speak_dialog('warning.playing')
            except exceptions.SoCoException as e:
                self.log.error(e)
        elif command == 'next music' or command == 'previous music':
            try:
                if speaker:
                    device = by_name(device_name)
                    if self._get_state(device.player_name) == 'PLAYING':
                        if command == 'next music':
                            device.next()
                        elif command == 'previous music':
                            device.previous()
                else:
                    for device in self.speakers:
                        if self._get_state(device.player_name) == 'PLAYING':
                            if command == 'next music':
                                device.next()
                            elif command == 'previous music':
                                device.previous()
            except exceptions.SoCoException as e:
                self.log.error(e)

    def _entity(self):
        self.register_entity_file('service.entity')
        self.register_entity_file('command.entity')

    def initialize(self):
        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()

    def on_settings_changed(self):
        self._setup()
        self._authentication()
        self._entity()
        self._discovery()
        self._subscribed_services()


def create_skill():
    return SonosController()
