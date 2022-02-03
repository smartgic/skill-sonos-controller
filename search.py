"""This file contains functions related to the searching items
"""
import re
from random import choice
from urllib.parse import unquote
from soco import exceptions
from soco.discovery import by_name
from .utils import get_category, check_speaker


def search(self, service, speaker, category, playlist=None, album=None,
           artist=None, track=None, podcast=None):
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
    :param podcast: Podcast name
    :type podcast: string, optional
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
                data['podcast'] = podcast
                search_type(self, data)
            else:
                self.speak_dialog('error.category', data={
                    'category': category})


def search_type(self, data):
    """This is a meta function that will act as proxy to redirect the
    query to the right function.

    :param data: Dict with all the required data
    :type data: dict
    """
    if data['category'] == 'playlists':
        search_playlist(self, data)
    elif data['category'] == 'albums':
        search_album(self, data)
    elif data['category'] == 'tracks':
        search_track(self, data)
    elif data['podcast'] == 'podcasts':
        search_podcast(self, data)


def search_playlist(self, data):
    """Search for playlist into Music Library and Music Services.

    :param data: Dict with all the required data
    :type data: dict
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

        if self.confirmation:
            self.speak_dialog('sonos.playlist', data={
                'playlist': title, 'service': data['service'],
                'speaker': data['speaker']})
    except exceptions.SoCoException as err:
        self.log.error(err)


def search_album(self, data):
    """Search for album into Music Library and Music Services.

    :param data: Dict with all the required data
    :type data: dict
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
            # If artist has been specify then we are using the
            # get_album_artists() method with subcategories argument.
            if data['artist']:
                for album in data['provider'].get_album_artists(
                        search_term=data['album'],
                        subcategories=[data['artist']],
                        complete_result=True):
                    albums[album.to_dict()['title']] = album.to_dict()[
                        'resources'][0]['uri']
                if albums:
                    picked = choice(list(albums.keys()))
                    device.add_uri_to_queue(albums[picked])
                    title = picked
                else:
                    self.speak_dialog('error.album.artist', data={
                        'album': data['album'], 'artist': data['artists']})
                    return
            else:
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
                        'album': data['album']})
                    return
        else:
            albums = data['provider'].search('albums', data['album'])
            if data['artist']:
                found = False
                for album in albums:
                    item_id = unquote(
                        unquote(re.sub('^0fffffff', '', album.item_id)))
                    meta = data['provider'].get_extended_metadata(item_id)
                    for key, value in meta.items():
                        if key == 'mediaCollection':
                            for info in value.items():
                                if info[1] == data['artist'].title():
                                    device.add_to_queue(album)
                                    title = album.title
                                    found = True
                                    break
                        if found:
                            break
                    if found:
                        break
                else:
                    self.speak_dialog('error.album.artist', data={
                        'album': data['album'],
                        'artist': data['artist']})
            else:
                if albums:
                    picked = choice(albums)
                    device.add_to_queue(picked)
                    title = picked.title
                else:
                    self.speak_dialog('error.album', data={
                        'album': data['album']})
                    return

        # Play the picked album
        device.play_from_queue(0)

        if self.confirmation:
            if data['artist']:
                self.speak_dialog('sonos.album.artist', data={
                    'album': title, 'service': data['service'],
                    'speaker': data['speaker'], 'artist': data['artist']})
            else:
                self.speak_dialog('sonos.album', data={
                    'album': title, 'service': data['service'],
                    'speaker': data['speaker']})
    except exceptions.SoCoException as err:
        self.log.error(err)


def search_track(self, data):
    """Search for track into Music Library and Music Services.

    :param data: Dict with all the required data
    :type data: dict
    :return:
    :raises SoCoException: Raise SoCoException
    """
    try:
        picked = None
        title = None
        tracks = {}

        # Clear the current content playing
        device = by_name(data['speaker'])
        device.clear_queue()

        if data['service'] == 'music library':
            # If artist has been specify then we are using the
            # search_track() method.
            if data['artist']:
                for track in data['provider'].search_track(
                        artist=data['artist'],
                        track=data['track']):
                    tracks[
                        track.to_dict()['title']] = track.to_dict()[
                        'resources'][0]['uri']
                if tracks:
                    picked = choice(list(tracks.keys()))
                    device.add_uri_to_queue(tracks[picked])
                    title = picked
                else:
                    self.speak_dialog('error.track.artist', data={
                        'track': data['track'], 'artist': data['artist']})
                    return
            else:
                for track in data['provider'].get_tracks(
                        search_term=data['track'],
                        complete_result=True):
                    tracks[
                        track.to_dict()['title']
                    ] = track.to_dict()[
                        'resources'][0]['uri']
                if tracks:
                    picked = choice(list(tracks.keys()))
                    device.add_uri_to_queue(tracks[picked])
                    title = picked
                else:
                    self.speak_dialog('error.track', data={
                        'track': data['track']})
        else:
            tracks = data['provider'].search('tracks', data['track'])
            if data['artist']:
                found = False
                for track in tracks:
                    item_id = unquote(
                        unquote(re.sub('^0fffffff', '', track.item_id)))
                    meta = data['provider'].get_media_metadata(item_id)
                    for key, value in meta.items():
                        if key == 'trackMetadata':
                            for info in value.items():
                                if info[1] == data['artist'].title():
                                    device.add_to_queue(track)
                                    title = track.title
                                    found = True
                                    break
                        if found:
                            break
                    if found:
                        break
                else:
                    self.speak_dialog('error.track.artist', data={
                        'track': data['track'],
                        'artist': data['artist']})
            else:
                if tracks:
                    picked = choice(tracks)
                    device.add_to_queue(picked)
                    title = picked.title
                else:
                    self.speak_dialog('error.track', data={
                        'track': data['track']})
                    return

        # Play the picked track
        device.play_from_queue(0)

        if self.confirmation:
            if data['artist']:
                self.speak_dialog('sonos.track.artist', data={
                    'track': title, 'service': data['service'],
                    'speaker': data['speaker'], 'artist': data['artist']})
            else:
                self.speak_dialog('sonos.track', data={
                    'track': title, 'service': data['service'],
                    'speaker': data['speaker']})
    except exceptions.SoCoException as err:
        self.log.error(err)


def search_podcast(self, data):
    """Search for podcast into Music Services only.

    :param data: Dict with all the required data
    :type data: dict
    :return:
    :raises SoCoException: Raise SoCoException
    """
    try:
        picked = None
        title = None

        # Clear the current content playing
        device = by_name(data['speaker'])
        device.clear_queue()

        podcasts = data['provider'].search('podcasts', data['podcast'])
        picked = choice(podcasts)
        device.add_to_queue(picked)
        title = picked.title

        # Play the picked podcast
        device.play_from_queue(0)

        if self.confirmation:
            self.speak_dialog('sonos.podcast', data={
                'podcast': title, 'service': data['service'],
                'speaker': data['speaker']})
    except exceptions.SoCoException as err:
        self.log.error(err)
