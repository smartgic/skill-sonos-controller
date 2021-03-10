"""This file contains constants mostly called by utils.py
"""
# List of current supported service by SoCo
SUPPORTED_SERVICES = ["Amazon Music", "Apple Music", "Deezer",
                      "Google Play Music", "Music Library", "Napster", "Plex",
                      "SoundCloud", "Spotify", "TuneIn", "Wolfgangs Music",
                      "YouTube Music"]

# Service that requires authentication
REQUIRED_AUTHENTICATION = ['Spotify', 'Amazon Music']

# List a supported categories for MusicLibrary
SUPPORTED_LIBRARY_CATEGORIES = ['artists', 'album_artists', 'albums',
                                'genres', 'composers', 'tracks', 'share',
                                'sonos_playlists', 'playlists']

TOKEN_FILE = '/.config/SoCo/token_store.json'
