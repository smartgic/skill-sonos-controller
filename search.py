from random import choice
from soco import exceptions
from soco.discovery import by_name
from .utils import get_category, check_speaker


def search(self, service, speaker, category, playlist=None, album=None,
           artist=None, track=None):
    if service in self.services:
        device_name = check_speaker(self, speaker)
        self.log.debug("++++++++++++++++{}".format(device_name))

        if device_name:
            provider = get_category(self, service, category)
            self.log.debug("==================== {}".format(provider))
            if provider:
                # Build data dictionnary
                data = {}
                data['service'] = service
                data['speaker'] = device_name
                data['category'] = category
                data['provider'] = provider
                data['playlist'] = playlist
                data['album'] = album
                data['artist'] = artist
                data['track'] = track
                search_type(self, data)
            else:
                self.speak_dialog('error.category', data={
                    'category': category})


def search_type(self, data):
    self.log.debug("=====search_type")
    if data['category'] == 'playlists':
        search_playlist(self, data)
    # elif data['category'] == 'albums':
    # elif data['category'] == 'tracks'
    # else:


def search_playlist(self, data):
    # try:
    picked = None
    title = None

    self.log.debug('===== {}'.format(data))

    device = by_name(data['speaker'])
    device.clear_queue()

    if data['service'] == 'Music Library':
        playlists = {}
        for playlist in data['provider'].get_playlists(
                search_term=data['playlist'],
                complete_result=True):
            playlists[playlist.to_dict()['title']] = playlist.to_dict()[
                'resources'][0]['uri']
        if playlists:
            picked = choice(list(playlists.keys()))
            device.add_uri_to_queue(playlists[picked])
            title = picked
        else:
            self.speak_dialog('error.playlist', data={
                'playlist': data['playlist']})
            return
    else:
        playlists = data['provider'].search('playlists', data['playlist'])
        picked = choice(playlists)
        device.add_to_queue(picked)
        title = picked.title

    device.play_from_queue(0)

    self.log.debug(
        '{} playlist from {} on {} started'.format(
            picked, data['service'], data['speaker']))
    self.speak_dialog('sonos.playlist', data={
        'playlist': title, 'service': data['service'],
        'speaker': data['speaker']})
    # except exceptions.SoCoException as e:
    #     self.log.error(e)
