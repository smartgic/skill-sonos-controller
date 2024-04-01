"""This file contains constants mostly called by utils.py
"""

# List of current supported service by SoCo
SUPPORTED_SERVICES = [
    "Amazon Music",
    "Apple Music",
    "Deezer",
    "Google Play Music",
    "Music Library",
    "Napster",
    "Plex",
    "SoundCloud",
    "Spotify",
    "Tidal",
    "TuneIn",
    "Wolfgangs Music",
    "YouTube Music",
]

# Service that requires authentication
REQUIRED_AUTHENTICATION = [
    "Spotify",
    "Apple Music",
    "Amazon Music",
    "Deezer",
    "Plex",
    "Tidal",
]

# List of supported categories for music library
SUPPORTED_MUSIC_LIBRARY_CATEGORIES = [
    "artists",
    "album_artists",
    "albums",
    "genres",
    "composers",
    "tracks",
    "share",
    "sonos_playlists",
    "playlists",
]

# Token file used by SoCo Python library
TOKEN_FILE = "/.config/SoCo/token_store.json"

# Token collection name
TOKEN_COLLECTION = "default"

# Volume values
DEFAULT_VOL_INCREMENT = 10
LOUDER_QUIETER = 30

# Link to the URL shortener
# This constant is only used by utils.authentication() method to
# provide support for the music services authentication.
# These services generate URL that are too long to be spoken by Mycroft
# which is why an URL shortener service is used.
URL_SHORTENER = "https://sonos.smartgic.io"

# Timeouts
HTTP_REQUEST_TIMEOUT = 5
