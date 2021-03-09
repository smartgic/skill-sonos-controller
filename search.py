from random import choice
from soco import exceptions
from soco.discovery import by_name
from .utils import get_category, check_speaker


def search(self, service, speaker, category, playlist=None, album=None,
           artist=None, track=None):
    """Search an item to play, it could be a playlist, an album or a track.

    This function will build a dict with all the required information
    collected and will pass it to the others functions.

    :param service: Music service to search in
    :type service: string
    :param speaker: Speaker where to play
    :type speaker: string
    :param category: Which category to look into
    :type category: string
    :param playlist: Playlist name
    :type playlist: string, optional
    :param album: Album name
    :type album: string, optional
    :param artist: Artist name
    :type artist: string, optional
    :param track: Track name
    :type track: string, optional
    :return:
    :raises SoCoException: Raise SoCoException
    """
    if service in map(str.lower, set(self.services)):
        device_name = check_speaker(self, speaker)
        if device_name:
            provider = get_category(self, service.title(), category)
            if provider:
                # Build data dictionnary to pass to search_type()
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
    """This is a meta function that will act as proxy to redirect the
    query to the right function.

    :param data: Dict with all the required data
    :type dict: string
    """
    if data['category'] == 'playlists':
        search_playlist(self, data)
    # elif data['category'] == 'albums':
    # elif data['category'] == 'tracks'
    # else:


def search_playlist(self, data):
    """Search for playlist into Music Library and Music Services.

    :param data: Dict with all the required data
    :type dict: string
    :return:
    :raises SoCoException: Raise SoCoException
    """
    try:
        picked = None
        title = None

        # Clear the current content playing
        device = by_name(data['speaker'])
        device.clear_queue()

        if data['service'] == 'music library':
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

        # Play the picked playlist
        device.play_from_queue(0)

        self.speak_dialog('sonos.playlist', data={
            'playlist': title, 'service': data['service'],
            'speaker': data['speaker']})
    except exceptions.SoCoException as err:
        self.log.error(err)


def search_album(self, data):
    """Search for album into Music Library and Music Services.

    :param data: Dict with all the required data
    :type dict: string
    :return:
    :raises SoCoException: Raise SoCoException
    """
    try:
        picked = None
        title = None

        # Clear the current content playing
        device = by_name(data['speaker'])
        device.clear_queue()

        if data['service'] == 'music library':
            albums = {}
            for album in data['provider'].get_albums(
                    search_term=data['album'],
                    complete_result=True):
                albums[album.to_dict()['title']] = album.to_dict()[
                    'resources'][0]['uri']
            if albums:
                picked = choice(list(albums.keys()))
                device.add_uri_to_queue(albums[picked])
                title = picked
            else:
                self.speak_dialog('error.album', data={
                    'album': album})
                return
        else:
            albums = data['provider'].search('albums', data['album'])
            picked = choice(albums)
            device.add_to_queue(picked)
            title = picked.title

        # Play the picked album
        device.play_from_queue(0)

        self.speak_dialog('sonos.album', data={
            'album': title, 'service': data['service'],
            'speaker': data['speaker']})
    except exceptions.SoCoException as err:
        self.log.error(err)
