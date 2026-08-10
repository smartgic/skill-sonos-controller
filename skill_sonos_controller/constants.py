"""Constants shared by the Sonos controller skill."""

DEFAULT_DISCOVERY_TIMEOUT = 5
DEFAULT_SOURCE = "Music Library"
DEFAULT_VOLUME_STEP = 10
LARGE_VOLUME_STEP = 30
MUSIC_LIBRARY = "Music Library"

# Canonical regional locales currently shipped by ovos-core. Locale resource
# directories use lowercase BCP-47 tags, as expected by ovos-workshop.
SUPPORTED_LOCALES = (
    "ca-es",
    "da-dk",
    "de-de",
    "en-us",
    "es-es",
    "eu-es",
    "fa-ir",
    "fr-fr",
    "gl-es",
    "it-it",
    "nl-be",
    "nl-nl",
    "pl-pl",
    "pt-br",
    "pt-pt",
    "uk-ua",
)

# SoCo exposes these categories for the local Sonos music index.
MUSIC_LIBRARY_CATEGORIES = frozenset(
    {
        "album_artists",
        "albums",
        "artists",
        "composers",
        "genres",
        "playlists",
        "share",
        "sonos_playlists",
        "tracks",
    }
)

# Different SMAPI providers use different names for podcast-like content.
CATEGORY_ALIASES = {
    "albums": ("albums", "books"),
    "artists": ("artists", "authors", "narrators", "users", "people", "hosts"),
    "playlists": ("playlists", "mix stations"),
    "podcasts": ("podcasts", "shows", "radio shows", "radio episodes", "episodes"),
    "stations": ("stations", "radio stations", "radios"),
    "tracks": ("tracks", "books"),
}

# This service only stores the temporary registration URL and link metadata.
DEFAULT_URL_SHORTENER = "https://sonos.smartgic.io"
HTTP_REQUEST_TIMEOUT = 10
