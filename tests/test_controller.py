"""Unit tests for the hardware-independent Sonos integration layer."""

from types import SimpleNamespace
from typing import ClassVar

import pytest
from soco.exceptions import MusicServiceAuthException, SoCoUPnPException

from skill_sonos_controller.constants import MUSIC_LIBRARY
from skill_sonos_controller.controller import (
    ServiceRegistry,
    SonosController,
    normalize_name,
)
from skill_sonos_controller.exceptions import (
    AmbiguousSpeakerError,
    AuthenticationNotSupportedError,
    CategoryNotSupportedError,
    NoResultsError,
    ServiceNotFoundError,
)

SERVICES = {
    "Amazon Music": {"ServiceType": "1", "Auth": "DeviceLink"},
    "Apple Music": {"ServiceType": "2", "Auth": "AppLink"},
    "Deezer": {"ServiceType": "3", "Auth": "DeviceLink"},
    "Napster": {"ServiceType": "4", "Auth": "DeviceLink"},
    "Plex": {"ServiceType": "5", "Auth": "DeviceLink"},
    "Qobuz": {"ServiceType": "6", "Auth": "DeviceLink"},
    "SoundCloud": {"ServiceType": "7", "Auth": "DeviceLink"},
    "Spotify": {"ServiceType": "8", "Auth": "DeviceLink"},
    "TIDAL": {"ServiceType": "9", "Auth": "DeviceLink"},
    "TuneIn": {"ServiceType": "65031", "Auth": "Anonymous"},
    "YouTube Music": {"ServiceType": "10", "Auth": "DeviceLink"},
}


class FakeTokenStore:
    def __init__(self, authenticated=True):
        self.authenticated = authenticated

    def has_token(self, service_id, household_id):
        return self.authenticated and bool(service_id and household_id)


class FakeMusicService:
    results: ClassVar[dict] = {}
    metadata: ClassVar[dict] = {}
    media_uris: ClassVar[dict] = {}
    categories: ClassVar[dict] = {}
    errors: ClassVar[dict] = {}
    instances: ClassVar[list] = []

    @classmethod
    def get_all_music_services_names(cls):
        return list(SERVICES)

    @classmethod
    def get_data_for_name(cls, name):
        return {"Name": name, "Id": SERVICES[name]["ServiceType"], **SERVICES[name]}

    def __init__(self, name, device=None):
        descriptor = self.get_data_for_name(name)
        self.service_name = name
        self.service_id = descriptor["Id"]
        self.service_type = descriptor["ServiceType"]
        self.auth_type = descriptor["Auth"]
        self.device = device
        self.token_store = FakeTokenStore()
        self.available_search_categories = self.categories.get(
            name, ["albums", "playlists", "podcasts", "tracks"]
        )
        self.link_code = "provider-code"
        self.link_device_id = "provider-device"
        self.completed = None
        self.instances.append(self)

    def search(self, category, query):
        error = self.errors.get((self.service_name, category, query))
        if error:
            raise error
        return self.results.get((self.service_name, category, query), [])

    def get_metadata(self, value, count=100):
        return self.metadata.get((self.service_name, value.id), [])[:count]

    def get_media_uri(self, value):
        return self.media_uris.get((self.service_name, value), "x-sonos:test")

    def begin_authentication(self):
        return "https://service.example/auth"

    def complete_authentication(self, code, device_id):
        self.completed = (code, device_id)


class FakeAccount:
    fail = False

    @classmethod
    def get_accounts(cls, _device):
        if cls.fail:
            raise OSError("account endpoint unavailable")
        return {
            str(index): SimpleNamespace(service_type=data["ServiceType"], deleted=False)
            for index, data in enumerate(SERVICES.values())
            if data["Auth"] != "Anonymous"
        }


class FakeLibrary:
    result: ClassVar[list] = []

    def __init__(self, device):
        self.device = device

    def get_tracks(self, **_kwargs):
        return self.result

    def get_albums(self, **_kwargs):
        return self.result

    def get_playlists(self, **_kwargs):
        return self.result

    def get_album_artists(self, **_kwargs):
        return self.result

    def search_track(self, **_kwargs):
        return self.result


class FakeDevice:
    def __init__(self, name="Living Room", state="PLAYING", volume=40, uid=None):
        self.player_name = name
        self.uid = uid or name
        self.household_id = "household"
        self.volume = volume
        self.mute = False
        self.play_mode = "NORMAL"
        self.repeat = False
        self.shuffle = False
        self.is_playing_tv = False
        self.is_playing_line_in = False
        self.dialog_mode = False
        self.night_mode = False
        self.calls = []
        self.queued = []
        self.queue_error = None
        self.state = state
        self.group = SimpleNamespace(members=[self], coordinator=self)

    def get_current_transport_info(self):
        return {"current_transport_state": self.state}

    def clear_queue(self):
        self.calls.append("clear_queue")
        self.queued.clear()

    def add_to_queue(self, item):
        self.calls.append("add_to_queue")
        if self.queue_error:
            raise self.queue_error
        self.queued.append(item)

    def play_from_queue(self, index):
        self.calls.append(("play_from_queue", index))

    def play_uri(self, uri, title=""):
        self.calls.append(("play_uri", uri, title))

    def pause(self):
        self.calls.append("pause")

    def stop(self):
        self.calls.append("stop")

    def play(self):
        self.calls.append("play")

    def next(self):
        self.calls.append("next")

    def previous(self):
        self.calls.append("previous")

    def switch_to_tv(self):
        self.calls.append("switch_to_tv")
        self.is_playing_tv = True

    def set_relative_volume(self, delta):
        self.volume = max(0, min(100, self.volume + delta))
        return self.volume

    def join(self, coordinator):
        self.calls.append(("join", coordinator.player_name))
        self.group = coordinator.group
        if self not in coordinator.group.members:
            coordinator.group.members.append(self)

    def unjoin(self):
        self.calls.append("unjoin")
        old_group = self.group
        old_group.members.remove(self)
        self.group = SimpleNamespace(members=[self], coordinator=self)


def item(
    title,
    artist=None,
    can_play=True,
    can_enumerate=True,
    item_type="track",
):
    return SimpleNamespace(
        id=title,
        title=title,
        artist=artist,
        resources=[SimpleNamespace(uri="x-sonos:test")],
        can_play=can_play,
        can_enumerate=can_enumerate,
        item_type=item_type,
        metadata={},
    )


@pytest.fixture(autouse=True)
def reset_fakes():
    FakeAccount.fail = False
    FakeMusicService.instances = []
    FakeMusicService.results = {}
    FakeMusicService.metadata = {}
    FakeMusicService.media_uris = {}
    FakeMusicService.categories = {}
    FakeMusicService.errors = {}
    FakeLibrary.result = []


@pytest.fixture
def device():
    return FakeDevice()


@pytest.fixture
def controller(device):
    instance = SonosController(
        discoverer=lambda **_kwargs: {device},
        music_service_cls=FakeMusicService,
        music_library_cls=FakeLibrary,
        account_cls=FakeAccount,
    )
    instance.refresh()
    return instance


def test_registry_resolves_every_advertised_service_without_case_rewriting(device):
    registry = ServiceRegistry(FakeMusicService, FakeAccount)
    registry.refresh(device)

    for service_name in SERVICES:
        assert registry.resolve(service_name.casefold()).name == service_name
    assert registry.resolve("tidal").name == "TIDAL"
    assert registry.resolve("amazon").name == "Amazon Music"
    assert registry.resolve("local library").name == MUSIC_LIBRARY
    with pytest.raises(ServiceNotFoundError):
        registry.resolve("not a sonos service")


@pytest.mark.parametrize(
    "localized_name",
    (
        "biblioteca de música",
        "musikbibliotek",
        "musika liburutegia",
        "muziekbibliotheek",
        "biblioteka muzyczna",
        "کتابخانه موسیقی",
        "музична бібліотека",
    ),
)
def test_registry_resolves_localized_music_library_aliases(device, localized_name):
    registry = ServiceRegistry(FakeMusicService, FakeAccount)
    registry.refresh(device)

    assert registry.resolve(localized_name).name == MUSIC_LIBRARY


@pytest.mark.parametrize(
    ("spoken", "expected"),
    (
        ("Música Local", "musicalocal"),
        ("کتابخانهٔ موسیقی", "کتابخانهموسیقی"),
        ("Музична бібліотека", "музичнабібліотека"),
    ),
)
def test_name_normalization_preserves_non_latin_scripts(spoken, expected):
    assert normalize_name(spoken) == expected


@pytest.mark.parametrize("room_name", ("دفتر کار", "Дитяча кімната"))
def test_speaker_resolution_supports_non_latin_room_names(room_name):
    device = FakeDevice(name=room_name)
    controller = SonosController(
        discoverer=lambda **_kwargs: {device},
        music_service_cls=FakeMusicService,
        music_library_cls=FakeLibrary,
        account_cls=FakeAccount,
    )
    controller.refresh()

    assert controller.resolve_speaker(room_name, coordinator=False) is device


def test_registry_lists_only_household_and_anonymous_services(device):
    class SpotifyAccount(FakeAccount):
        @classmethod
        def get_accounts(cls, _device):
            return {
                "1": SimpleNamespace(service_type="8", deleted=False),
            }

    registry = ServiceRegistry(FakeMusicService, SpotifyAccount)
    registry.refresh(device)

    assert {service.name for service in registry.household_services} == {
        MUSIC_LIBRARY,
        "Spotify",
        "TuneIn",
    }


def test_registry_keeps_all_services_when_account_endpoint_is_unavailable(device):
    FakeAccount.fail = True
    registry = ServiceRegistry(FakeMusicService, FakeAccount)
    registry.refresh(device)

    assert {service.name for service in registry.household_services} == {
        MUSIC_LIBRARY,
        *SERVICES,
    }


@pytest.mark.parametrize("service_name", list(SERVICES))
def test_search_and_play_works_for_every_advertised_service(
    controller, device, service_name
):
    result_item = item("Exact Song")
    FakeMusicService.results[(service_name, "tracks", "Exact Song")] = [result_item]

    result = controller.search_and_play(
        service_name, "living room", "tracks", "Exact Song"
    )

    assert result.service == service_name
    assert result.title == "Exact Song"
    assert device.queued == [result_item]
    assert FakeMusicService.instances[-1].device is device


def test_household_proxy_search_can_work_without_a_local_soco_token(controller, device):
    result_item = item("Exact Song")
    FakeMusicService.results[("Deezer", "tracks", "Exact Song")] = [result_item]
    FakeMusicService.instances.clear()

    result = controller.search_and_play("Deezer", "Living Room", "tracks", "Exact Song")

    assert result.service == "Deezer"
    assert device.queued == [result_item]


def test_real_smapi_auth_failure_is_translated_without_clearing_queue(
    controller, device
):
    device.queued = ["currently playing"]
    FakeMusicService.errors[("Spotify", "tracks", "Exact Song")] = (
        MusicServiceAuthException("token expired")
    )

    from skill_sonos_controller.exceptions import AuthenticationRequiredError

    with pytest.raises(AuthenticationRequiredError):
        controller.search_and_play("Spotify", "Living Room", "tracks", "Exact Song")

    assert device.queued == ["currently playing"]


def test_podcast_search_uses_provider_show_category(controller, device):
    FakeMusicService.categories["TuneIn"] = ["shows", "stations"]
    show = item("The Daily")
    FakeMusicService.results[("TuneIn", "shows", "The Daily")] = [show]

    result = controller.search_and_play(
        "TuneIn", "Living Room", "podcasts", "The Daily"
    )

    assert result.title == "The Daily"
    assert device.queued == [show]


@pytest.mark.parametrize(
    ("requested", "provider_category"),
    [
        ("albums", "Books"),
        ("artists", "Authors"),
        ("artists", "Users"),
        ("playlists", "MixStations"),
        ("podcasts", "Radio Shows"),
        ("stations", "Radios"),
        ("tracks", "Books"),
    ],
)
def test_provider_category_aliases_are_case_and_spacing_insensitive(
    controller, device, requested, provider_category
):
    FakeMusicService.categories["TuneIn"] = [provider_category]
    station = item("CBC Radio One")
    FakeMusicService.results[("TuneIn", provider_category, "CBC Radio One")] = [station]

    result = controller.search_and_play(
        "TuneIn", "Living Room", requested, "CBC Radio One"
    )

    assert result.category == requested
    assert device.queued == [station]


def test_podcast_search_browses_to_a_playable_episode(controller, device):
    bucket = item("Recent Episodes", can_play=False)
    show = item("The Daily", can_play=False)
    episode = item("A New Episode", can_enumerate=False)
    FakeMusicService.categories["TuneIn"] = ["shows"]
    FakeMusicService.results[("TuneIn", "shows", "The Daily")] = [bucket]
    FakeMusicService.metadata[("TuneIn", bucket.id)] = [show]
    FakeMusicService.metadata[("TuneIn", show.id)] = [episode]

    result = controller.search_and_play(
        "TuneIn", "living room", "podcasts", "The Daily"
    )

    assert result.title == "A New Episode"
    assert device.queued == [episode]


def test_artist_search_prefers_top_tracks_over_related_artist_radio(controller, device):
    artist = item("Alicia Keys", can_play=False, can_enumerate=True, item_type="artist")
    radio = item("Alicia Keys Radio", artist="Alicia Keys", item_type="program")
    top_tracks = item("Top Tracks", item_type="trackList")
    FakeMusicService.categories["Spotify"] = ["artists"]
    FakeMusicService.results[("Spotify", "artists", "Alicia Keys")] = [artist]
    FakeMusicService.metadata[("Spotify", artist.id)] = [radio, top_tracks]

    controller.search_and_play("Spotify", "Living Room", "artists", "Alicia Keys")

    assert device.queued == [top_tracks]


def test_podcast_search_browses_playable_container_with_missing_flags(
    controller, device
):
    show = item(
        "Journal de 9h",
        can_play=True,
        can_enumerate=None,
        item_type="container",
    )
    episode = item("Journal de 09h00", can_enumerate=False)
    FakeMusicService.categories["TuneIn"] = ["podcasts"]
    FakeMusicService.results[("TuneIn", "podcasts", "Journal de 9h")] = [show]
    FakeMusicService.metadata[("TuneIn", show.id)] = [episode]

    result = controller.search_and_play(
        "TuneIn", "living room", "podcasts", "Journal de 9h"
    )

    assert result.title == "Journal de 09h00"
    assert device.queued == [episode]


@pytest.mark.parametrize("error_code", ["800", "804"])
def test_queue_stream_error_resolves_provider_m3u_and_plays_directly(
    error_code, controller, device, monkeypatch
):
    episode = item("A New Episode", can_enumerate=False)
    FakeMusicService.results[("TuneIn", "podcasts", "The Daily")] = [episode]
    FakeMusicService.media_uris[("TuneIn", episode.id)] = (
        "https://provider.example/Tune.ashx?id=episode"
    )
    device.queue_error = SoCoUPnPException("rejected", error_code, "")

    class PlaylistResponse:
        headers: ClassVar[dict[str, str]] = {"Content-Type": "audio/x-mpegurl"}
        encoding = "utf-8"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_content(chunk_size):
            assert chunk_size == 4096
            yield b"#EXTM3U\nhttps://cdn.example/episode.mp3\n"

    monkeypatch.setattr(
        "skill_sonos_controller.controller.requests.get",
        lambda *_args, **_kwargs: PlaylistResponse(),
    )

    result = controller.search_and_play(
        "TuneIn", "living room", "podcasts", "The Daily"
    )

    assert result.title == "A New Episode"
    assert device.queued == []
    assert (
        "play_uri",
        "https://cdn.example/episode.mp3",
        "A New Episode",
    ) in device.calls
    assert ("play_from_queue", 0) not in device.calls


def test_queue_errors_other_than_804_are_not_masked(controller, device):
    track = item("Exact Song")
    FakeMusicService.results[("Spotify", "tracks", "Exact Song")] = [track]
    device.queue_error = SoCoUPnPException("transition unavailable", "701", "")

    with pytest.raises(SoCoUPnPException, match="transition unavailable"):
        controller.search_and_play("Spotify", "living room", "tracks", "Exact Song")

    assert not any(
        call[0] == "play_uri" for call in device.calls if isinstance(call, tuple)
    )


def test_hls_playlist_is_left_for_sonos_to_process(monkeypatch):
    class HlsResponse:
        headers: ClassVar[dict[str, str]] = {
            "Content-Type": "application/vnd.apple.mpegurl"
        }
        encoding = "utf-8"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_content(chunk_size):
            assert chunk_size == 4096
            yield b"#EXTM3U\n#EXT-X-VERSION:3\nsegment.ts\n"

    monkeypatch.setattr(
        "skill_sonos_controller.controller.requests.get",
        lambda *_args, **_kwargs: HlsResponse(),
    )

    uri = "https://cdn.example/live.m3u8"
    assert SonosController._resolve_media_uri(uri) == uri


def test_unsupported_category_does_not_destroy_current_queue(controller, device):
    device.queued = ["currently playing"]
    FakeMusicService.categories["Spotify"] = ["tracks"]

    with pytest.raises(CategoryNotSupportedError):
        controller.search_and_play("Spotify", "Living Room", "playlists", "Focus")

    assert device.queued == ["currently playing"]
    assert "clear_queue" not in device.calls


def test_unsupported_legacy_auth_does_not_search_or_clear_queue(controller, device):
    device.queued = ["currently playing"]
    SERVICES["Legacy Service"] = {"ServiceType": "99", "Auth": "UserId"}
    try:
        controller.registry.refresh(device)
        with pytest.raises(AuthenticationNotSupportedError):
            controller.search_and_play(
                "Legacy Service", "Living Room", "tracks", "Song"
            )
        assert device.queued == ["currently playing"]
    finally:
        SERVICES.pop("Legacy Service")


def test_no_artist_match_does_not_start_an_empty_or_wrong_queue(controller, device):
    device.queued = ["currently playing"]
    FakeMusicService.results[("Spotify", "tracks", "Hello")] = [
        item("Hello", artist="Adele"),
        item("Hello", artist="Lionel Richie"),
    ]

    with pytest.raises(NoResultsError):
        controller.search_and_play(
            "Spotify", "Living Room", "tracks", "Hello", artist="Beyoncé"
        )

    assert device.queued == ["currently playing"]


def test_best_exact_artist_and_title_match_is_selected(controller, device):
    exact = item("Hello", artist="Adele")
    FakeMusicService.results[("Spotify", "tracks", "Hello")] = [
        item("Hello Again", artist="Adele"),
        exact,
        item("Hello", artist="Lionel Richie"),
    ]

    controller.search_and_play(
        "Spotify", "Living Room", "tracks", "Hello", artist="adele"
    )

    assert device.queued == [exact]


def test_exact_artist_beats_a_title_match_from_a_tribute_artist(controller, device):
    exact = item("Imagine - Remastered 2010", artist="John Lennon")
    FakeMusicService.results[("Spotify", "tracks", "Imagine")] = [
        item("Imagine", artist="John Lennon Experience"),
        exact,
    ]

    controller.search_and_play(
        "Spotify", "Living Room", "tracks", "Imagine", artist="John Lennon"
    )

    assert device.queued == [exact]


def test_equal_normalized_titles_preserve_provider_relevance_order(controller, device):
    provider_favorite = item("Thriller", artist="Michael Jackson")
    FakeMusicService.results[("Spotify", "albums", "Thriller")] = [
        provider_favorite,
        item("Thriller!", artist="Cold Blood"),
    ]

    controller.search_and_play("Spotify", "Living Room", "albums", "Thriller")

    assert device.queued == [provider_favorite]


def test_title_suffixes_preserve_provider_relevance_order(controller, device):
    canonical = item("Here Comes The Sun - Remastered 2009", artist="The Beatles")
    FakeMusicService.results[("Spotify", "tracks", "Here Comes the Sun")] = [
        canonical,
        item("Here Comes The Sun - 2019 Mix", artist="The Beatles"),
        item("Here Comes The Sun (Take 9)", artist="The Beatles"),
    ]

    controller.search_and_play(
        "Spotify",
        "Living Room",
        "tracks",
        "Here Comes the Sun",
        artist="The Beatles",
    )

    assert device.queued == [canonical]


def test_music_library_uses_target_device_and_didl_item(controller, device):
    local_track = item("Local Song")
    FakeLibrary.result = [local_track]

    result = controller.search_and_play(
        "music library", "Living Room", "tracks", "Local Song"
    )

    assert result.service == MUSIC_LIBRARY
    assert device.queued == [local_track]


def test_partial_speaker_names_must_be_unambiguous():
    living = FakeDevice("Living Room")
    kitchen = FakeDevice("Living Kitchen")
    controller = SonosController(discoverer=lambda **_kwargs: {living, kitchen})
    controller.speakers = (living, kitchen)

    with pytest.raises(AmbiguousSpeakerError):
        controller.resolve_speaker("living")
    assert controller.resolve_speaker("living room") is living


def test_group_commands_target_the_coordinator_only_once():
    coordinator = FakeDevice("Living Room", uid="coordinator")
    member = FakeDevice("Kitchen", uid="member")
    group = SimpleNamespace(members=[coordinator, member], coordinator=coordinator)
    coordinator.group = group
    member.group = group
    controller = SonosController(discoverer=lambda **_kwargs: {coordinator, member})
    controller.speakers = (coordinator, member)

    assert controller.run_command("next") == 1
    assert coordinator.calls == ["next"]
    assert member.calls == []
    with pytest.raises(ValueError):
        controller.run_command("__class__")


def test_playback_options_preserve_each_other(controller, device):
    device.repeat = True

    controller.set_playback_option("shuffle", True, "Living Room")

    assert device.shuffle is True
    assert device.repeat is True
    with pytest.raises(ValueError):
        controller.set_playback_option("crossfade", True)


def test_group_volume_changes_every_active_member():
    coordinator = FakeDevice("Living Room", volume=20)
    member = FakeDevice("Kitchen", volume=30)
    group = SimpleNamespace(members=[coordinator, member], coordinator=coordinator)
    coordinator.group = group
    member.group = group
    controller = SonosController(discoverer=lambda **_kwargs: {coordinator, member})
    controller.speakers = (coordinator, member)

    assert controller.change_volume(10) == 2
    assert (coordinator.volume, member.volume) == (30, 40)


def test_exact_volume_and_mute_target_individual_group_member():
    coordinator = FakeDevice("Living Room", volume=20)
    member = FakeDevice("Kitchen", volume=30)
    group = SimpleNamespace(members=[coordinator, member], coordinator=coordinator)
    coordinator.group = group
    member.group = group
    controller = SonosController(discoverer=lambda **_kwargs: {coordinator, member})
    controller.speakers = (coordinator, member)

    assert controller.set_volume(12, "Kitchen") == 1
    assert controller.set_mute(True, "Kitchen") == 1
    assert coordinator.volume == 20
    assert coordinator.mute is False
    assert member.volume == 12
    assert member.mute is True
    with pytest.raises(ValueError):
        controller.set_volume(101, "Kitchen")


def test_group_all_and_ungroup_coordinator_are_predictable():
    office = FakeDevice("Office")
    kitchen = FakeDevice("Kitchen")
    library = FakeDevice("Library")
    controller = SonosController(
        discoverer=lambda **_kwargs: {office, kitchen, library}
    )
    controller.speakers = (office, kitchen, library)

    assert controller.group_all("Office") == 2
    assert kitchen.group.coordinator is office
    assert library.group.coordinator is office
    assert controller.ungroup_speaker("Office") == 2
    assert office.group.members == [office]
    assert kitchen.group.members == [kitchen]
    assert library.group.members == [library]


def test_home_theater_source_night_and_speech_controls(controller, device):
    assert controller.switch_to_tv("Living Room") == 1
    assert controller.set_home_theater_option("night", True, "Living Room") == 1
    assert controller.set_home_theater_option("speech", True, "Living Room") == 1

    assert "switch_to_tv" in device.calls
    assert device.night_mode is True
    assert device.dialog_mode is True
    with pytest.raises(ValueError):
        controller.set_home_theater_option("unknown", True, "Living Room")


def test_volume_is_clamped_and_duck_restores_exact_snapshot(device):
    device.volume = 95
    controller = SonosController(discoverer=lambda **_kwargs: {device})
    controller.speakers = (device,)

    controller.change_volume(30, "Living Room")
    assert device.volume == 100
    controller.duck(10)
    assert device.volume == 90
    controller.unduck()
    assert device.volume == 100
