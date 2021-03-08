"""This file contains functions related to extra operations
and are called by the handle_* methods from __init__.py
"""

import os
from soco import exceptions
from soco import discover
from soco.discovery import by_name
from soco.music_library import MusicLibrary
from soco.music_services import MusicService
from .constants import SUPPORTED_LIBRARY_CATEGORIES, \
    SUPPORTED_SERVICES, REQUIRED_AUTHENTICATION, TOKEN_FILE


def authentication(self):
    """Some music services require an authentication.
    SoCo is currently looking to bring back the music service which will make
    this function disappears in the future.
    https://github.com/SoCo/SoCo/pull/763s
    """
    # This path is required by SoCo Python library and can't be changed
    token_file = os.getenv('HOME') + TOKEN_FILE

    if self.service in REQUIRED_AUTHENTICATION:
        provider = MusicService(self.service)

        # self.code is an option from available fomr home.mycroft.ai
        if not os.path.isfile(token_file) and self.code != '':
            try:
                provider.device_or_app_link_auth_part2(self.code)
                self.speak_dialog('sonos.authenticated')
            except exceptions.SoCoException as err:
                self.log.error(err)
        elif not os.path.isfile(token_file):
            try:
                _, link_code = provider.device_or_app_link_auth_part1()
                # Map the code with NATO
                data = {"slash": '. '.join(
                    map(self.nato_dict.get, link_code)) + '.'}
                self.log.info('sonos link code: {}'.format(link_code))
                self.speak_dialog('sonos.link_code', data={
                    'link_code': data})
            except exceptions.SoCoException as err:
                self.log.error(err)


def discovery(self):
    """Discover Sonos devices registered on the local network and
    add the speakers to a list.
    https://tinyurl.com/kahwd11y
    """
    try:
        self.speakers = discover(timeout=10, allow_network_scan=True)
    except exceptions.SoCoException as err:
        self.log.error(err)

    if not self.speakers:
        self.log.warning('unable to find sonos devices')
        self.speak_dialog('error.disovery')
    else:
        self.log.info(
            '{} device(s) found'.format(len(self.speakers)))


def get_state(self, speaker):
    """Get the current playback state.
    https://tinyurl.com/5az3lcb5

    :param speaker: Speaker to check the playback state
    :return: The current transport state
    :rtype: str
    """
    try:
        device = by_name(speaker)
        if device:
            key = 'current_transport_state'
            return device.get_current_transport_info()[key]
    except exceptions.SoCoException as err:
        self.log.error(err)
    return None


def check_category(self, service, category):
    """Check if a category is available for a specific service or library.
    https://tinyurl.com/1plj5lzv

    :param service: Music service to check the categories
    :param category: Which category to check
    :return: A music provider depending the service
    :rtype:
    """
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
    except exceptions.SoCoException as err:
        self.log.error(err)

    self.log.warning('{} category not found for {} service'.format(
        category, service))
    self.speak_dialog('error.category', data={
                      'category': category, 'service': service})
    return None


def subscribed_services(self):
    """Get a list of all subscribed music services.
    https://tinyurl.com/zu3ymsd9

    :return: A list of subscribed services
    :rtype: list
    """
    try:
        # Commented until SoCo integrates this method back
        # self.services = MusicService.get_subscribed_services_names()
        self.services = ['Spotify', 'Amazon Music',
                         'Wolfgangs Music', 'Music Library']
        return self.services
    except exceptions.SoCoException as err:
        self.log.error(err)


def check_speaker(self, speaker):
    """Check if the speaker is part of the discovered speakers and checks
    if it's part of a group/zone.
    If the speaker is part of a group/zone then it retrieves the group
    coordinator.
    https://tinyurl.com/4chwrb6u

    :param speaker: Which speaker to looking for
    :return: Speaker name
    :rtype: str
    """
    try:
        for device in self.speakers:
            if speaker in device.player_name.lower():
                if len(device.group.members) > 1:
                    coordinator = device.group.coordinator
                    return coordinator.player_name
                return device.player_name
    except exceptions.SoCoException as err:
        self.log.error(err)

    self.log.warning('{} speaker not found'.format(speaker))
    self.speak_dialog('error.speaker', data={'speaker': speaker})

    return None


def check_service(self, service):
    """Check if the spoken service is part of the supported services, if found
    then we are looking for it into the subscribed service. Once the service
    has been found into the both list then we are looking it requires an
    authentication.

    :param service: Music service to check
    :return: Speaker name
    :rtype: str
    """
    if service in map(str.lower, set(SUPPORTED_SERVICES)):
        for subscription in self.services:
            if service in subscription.lower():
                auth = map(str.lower, set(REQUIRED_AUTHENTICATION))
                if service in auth:
                    if not os.path.isfile(os.getenv('HOME') + TOKEN_FILE):
                        self.log.warning(
                            '{} requires authentication'.format(service))
                        self.speak_dialog('error.auth', data={
                            'service': service})
                        return service
                return service

    self.log.error('{} service not supported'.format(service))
    self.speak_dialog('error.support', data={'service': service})

    return None