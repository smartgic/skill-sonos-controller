"""Testable Sonos household, playback, and music-service integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, ClassVar
from unicodedata import normalize
from urllib.parse import urljoin, urlsplit

import requests
from soco import discover
from soco.exceptions import MusicServiceAuthException, SoCoException, SoCoUPnPException
from soco.music_library import MusicLibrary
from soco.music_services import Account, MusicService
from soco.xml import XML

from .constants import (
    CATEGORY_ALIASES,
    DEFAULT_DISCOVERY_TIMEOUT,
    MUSIC_LIBRARY,
    MUSIC_LIBRARY_CATEGORIES,
)
from .exceptions import (
    AmbiguousSpeakerError,
    AuthenticationNotSupportedError,
    AuthenticationRequiredError,
    CategoryNotSupportedError,
    NoResultsError,
    NoSpeakersError,
    ServiceNotFoundError,
    SpeakerNotFoundError,
)

_PLAYLIST_CONTENT_TYPES = frozenset(
    {
        "application/mpegurl",
        "application/vnd.apple.mpegurl",
        "application/x-mpegurl",
        "audio/mpegurl",
        "audio/x-mpegurl",
    }
)
_MAX_PLAYLIST_BYTES = 64 * 1024
_MEDIA_URI_TIMEOUT = 10
# Current Sonos firmware reports 800 for live SMAPI streams and 804 for some
# on-demand SMAPI items when they cannot be inserted into a queue. Both remain
# directly playable through the provider's getMediaURI endpoint.
_DIRECT_PLAY_FALLBACK_CODES = frozenset({"800", "804"})


def normalize_name(value: str | None) -> str:
    """Normalize a spoken name while retaining letters from every script."""
    decomposed = normalize("NFKD", (value or "").casefold())
    return "".join(character for character in decomposed if character.isalnum())


@dataclass(frozen=True)
class ServiceInfo:
    """A Sonos music-service descriptor relevant to this household."""

    name: str
    service_type: str | None = None
    auth_type: str = "Anonymous"
    subscribed: bool = False


@dataclass(frozen=True)
class PlaybackResult:
    """Description of media successfully started on a Sonos speaker."""

    title: str
    service: str
    speaker: str
    category: str
    artist: str | None = None


class ServiceRegistry:
    """Resolve service names from descriptors advertised by Sonos."""

    _ALIASES: ClassVar[dict[str, str]] = {
        normalize_name(alias): MUSIC_LIBRARY
        for alias in (
            "library",
            "local",
            "local library",
            "local music",
            "music library",
            "biblioteca de música",
            "biblioteca musical",
            "biblioteca de musica",
            "biblioteca musical local",
            "lokal musik",
            "musikbibliotek",
            "lokale muziek",
            "muziekbibliotheek",
            "musika liburutegia",
            "tokiko musika",
            "biblioteka muzyczna",
            "muzyka lokalna",
            "کتابخانه موسیقی",
            "موسیقی محلی",
            "музична бібліотека",
            "локальна музика",
        )
    }

    def __init__(
        self,
        music_service_cls: type[MusicService] = MusicService,
        account_cls: type[Account] = Account,
    ) -> None:
        self._music_service_cls = music_service_cls
        self._account_cls = account_cls
        self._services: dict[str, ServiceInfo] = {
            normalize_name(MUSIC_LIBRARY): ServiceInfo(MUSIC_LIBRARY, subscribed=True)
        }
        self._account_discovery_succeeded = False

    @property
    def services(self) -> tuple[ServiceInfo, ...]:
        """Return every service currently advertised by Sonos."""
        return tuple(
            sorted(self._services.values(), key=lambda item: item.name.casefold())
        )

    @property
    def household_services(self) -> tuple[ServiceInfo, ...]:
        """Return subscribed and anonymous services available to the household."""
        if not self._account_discovery_succeeded:
            return self.services
        return tuple(service for service in self.services if service.subscribed)

    def refresh(self, device: Any) -> tuple[ServiceInfo, ...]:
        """Load service descriptors and match them to household accounts."""
        account_types: set[str] = set()
        self._account_discovery_succeeded = False
        try:
            account_types = {
                str(account.service_type)
                for account in self._account_cls.get_accounts(device).values()
                if not getattr(account, "deleted", False)
            }
            self._account_discovery_succeeded = True
        except (
            OSError,
            ValueError,
            requests.RequestException,
            SoCoException,
            XML.ParseError,
        ):
            # Some current Sonos firmware does not expose /status/accounts.
            # All advertised services remain resolvable in that case.
            account_types = set()

        services = {
            normalize_name(MUSIC_LIBRARY): ServiceInfo(MUSIC_LIBRARY, subscribed=True)
        }
        for name in self._music_service_cls.get_all_music_services_names():
            data = self._music_service_cls.get_data_for_name(name)
            service_type = str(data.get("ServiceType", "")) or None
            auth_type = str(data.get("Auth", "Anonymous"))
            subscribed = auth_type == "Anonymous" or service_type in account_types
            services[normalize_name(name)] = ServiceInfo(
                name=name,
                service_type=service_type,
                auth_type=auth_type,
                subscribed=subscribed,
            )
        self._services = services
        return self.household_services

    def resolve(self, spoken_name: str | None) -> ServiceInfo:
        """Resolve a case-insensitive service name or safe common alias."""
        key = normalize_name(spoken_name)
        if not key:
            raise ServiceNotFoundError("No music service was provided")
        if key in self._services:
            return self._services[key]

        alias = self._ALIASES.get(key)
        if alias and normalize_name(alias) in self._services:
            return self._services[normalize_name(alias)]

        # Voice recognizers often omit a trailing "Music" from brand names.
        matches = [
            service
            for service in self._services.values()
            if normalize_name(service.name).removesuffix("music") == key
        ]
        if len(matches) == 1:
            return matches[0]
        raise ServiceNotFoundError(spoken_name or "")


class SonosController:
    """Coordinate Sonos discovery, transport commands, and SMAPI searches."""

    def __init__(
        self,
        discovery_timeout: int = DEFAULT_DISCOVERY_TIMEOUT,
        discoverer: Callable[..., Iterable[Any] | None] = discover,
        music_service_cls: type[MusicService] = MusicService,
        music_library_cls: type[MusicLibrary] = MusicLibrary,
        account_cls: type[Account] = Account,
    ) -> None:
        self.discovery_timeout = discovery_timeout
        self._discoverer = discoverer
        self._music_service_cls = music_service_cls
        self._music_library_cls = music_library_cls
        self.registry = ServiceRegistry(music_service_cls, account_cls)
        self.speakers: tuple[Any, ...] = ()
        self._volume_snapshot: dict[str, int] = {}

    def refresh(self) -> tuple[Any, ...]:
        """Discover speakers and refresh household music services."""
        discovered = self._discoverer(timeout=self.discovery_timeout) or set()
        self.speakers = tuple(
            sorted(discovered, key=lambda item: item.player_name.casefold())
        )
        if self.speakers:
            self.registry.refresh(self.speakers[0])
        return self.speakers

    def _require_speakers(self) -> None:
        if not self.speakers:
            self.refresh()
        if not self.speakers:
            raise NoSpeakersError("No Sonos speakers were discovered")

    def resolve_speaker(self, spoken_name: str | None, coordinator: bool = True) -> Any:
        """Resolve a room exactly, or by an unambiguous partial name."""
        self._require_speakers()
        if not spoken_name:
            raise SpeakerNotFoundError("No speaker was provided")
        key = normalize_name(spoken_name)
        exact = [
            device
            for device in self.speakers
            if normalize_name(device.player_name) == key
        ]
        matches = exact or [
            device
            for device in self.speakers
            if key and key in normalize_name(device.player_name)
        ]
        if not matches:
            raise SpeakerNotFoundError(spoken_name)
        if len(matches) > 1:
            raise AmbiguousSpeakerError(spoken_name)
        device = matches[0]
        if coordinator and len(device.group.members) > 1:
            return device.group.coordinator
        return device

    def coordinators(self, state: str | None = None) -> tuple[Any, ...]:
        """Return each group coordinator once, optionally filtered by state."""
        self._require_speakers()
        coordinators: dict[str, Any] = {}
        for speaker in self.speakers:
            coordinator = (
                speaker.group.coordinator if len(speaker.group.members) > 1 else speaker
            )
            uid = str(getattr(coordinator, "uid", coordinator.player_name))
            if state and self.transport_state(coordinator) != state:
                continue
            coordinators[uid] = coordinator
        return tuple(coordinators.values())

    @staticmethod
    def transport_state(device: Any) -> str:
        """Return a player's normalized AV transport state."""
        return str(
            device.get_current_transport_info().get("current_transport_state", "")
        ).upper()

    def run_command(
        self,
        command: str,
        speaker: str | None = None,
        required_state: str | None = "PLAYING",
        mode: str | None = None,
    ) -> int:
        """Run a validated transport command and return the target count."""
        allowed = {"next", "pause", "play", "previous", "stop"}
        if command != "mode" and command not in allowed:
            raise ValueError(f"Unsupported Sonos command: {command}")

        if speaker:
            targets = (self.resolve_speaker(speaker),)
        else:
            targets = self.coordinators(required_state)

        count = 0
        for device in targets:
            if (
                required_state
                and self.transport_state(device) != required_state.upper()
            ):
                continue
            if command == "mode":
                if not mode:
                    raise ValueError("A play mode is required")
                device.play_mode = mode.upper()
            elif command in {"pause", "stop"} and not self._valid_music_source(device):
                continue
            else:
                getattr(device, command)()
            count += 1
        return count

    def set_playback_option(
        self, option: str, enabled: bool, speaker: str | None = None
    ) -> int:
        """Toggle shuffle or repeat without changing the other option."""
        if option not in {"repeat", "shuffle"}:
            raise ValueError(f"Unsupported Sonos playback option: {option}")
        targets = (
            (self.resolve_speaker(speaker),)
            if speaker
            else self.coordinators("PLAYING")
        )
        count = 0
        for device in targets:
            if self.transport_state(device) != "PLAYING":
                continue
            setattr(device, option, bool(enabled))
            count += 1
        return count

    @staticmethod
    def _valid_music_source(device: Any) -> bool:
        return not (device.is_playing_tv or device.is_playing_line_in)

    def change_volume(
        self, delta: int, speaker: str | None = None, active_only: bool = True
    ) -> int:
        """Change volume using SoCo's single-request relative adjustment."""
        if speaker:
            targets = (self.resolve_speaker(speaker, coordinator=False),)
        elif active_only:
            targets = self.active_speakers()
        else:
            self._require_speakers()
            targets = self.speakers
        for device in targets:
            device.set_relative_volume(int(delta))
        return len(targets)

    def set_volume(
        self, level: int, speaker: str | None = None, active_only: bool = True
    ) -> int:
        """Set an exact, validated volume on a room or active household."""
        level = int(level)
        if not 0 <= level <= 100:
            raise ValueError("Sonos volume must be between 0 and 100")
        targets = self._individual_targets(speaker, active_only)
        for device in targets:
            device.volume = level
        return len(targets)

    def set_mute(
        self, muted: bool, speaker: str | None = None, active_only: bool = True
    ) -> int:
        """Set mute on a room or every member of an active group."""
        targets = self._individual_targets(speaker, active_only)
        for device in targets:
            device.mute = bool(muted)
        return len(targets)

    def _individual_targets(
        self, speaker: str | None, active_only: bool
    ) -> tuple[Any, ...]:
        """Resolve individual speakers for volume-like controls."""
        if speaker:
            return (self.resolve_speaker(speaker, coordinator=False),)
        if active_only:
            return self.active_speakers()
        self._require_speakers()
        return self.speakers

    def group_speakers(self, coordinator_name: str, member_names: Iterable[str]) -> int:
        """Join resolved rooms to a coordinator after validating every name."""
        coordinator = self.resolve_speaker(coordinator_name, coordinator=False)
        members = tuple(
            self.resolve_speaker(name, coordinator=False) for name in member_names
        )
        coordinator_uid = str(getattr(coordinator, "uid", coordinator.player_name))
        changed = 0
        for member in members:
            member_uid = str(getattr(member, "uid", member.player_name))
            if member_uid == coordinator_uid:
                continue
            if (
                len(member.group.members) > 1
                and member.group.coordinator.uid == coordinator.uid
            ):
                continue
            member.join(coordinator)
            changed += 1
        return changed

    def group_all(self, coordinator_name: str) -> int:
        """Group the complete discovered household around one room."""
        self._require_speakers()
        return self.group_speakers(
            coordinator_name,
            (speaker.player_name for speaker in self.speakers),
        )

    def ungroup_speaker(self, speaker_name: str) -> int:
        """Isolate a room predictably, including when it is the coordinator."""
        device = self.resolve_speaker(speaker_name, coordinator=False)
        members = tuple(device.group.members)
        if len(members) <= 1:
            return 0
        if device.group.coordinator.uid != device.uid:
            device.unjoin()
            return 1

        changed = 0
        for member in members:
            if member.uid == device.uid:
                continue
            member.unjoin()
            changed += 1
        return changed

    def switch_to_tv(self, speaker_name: str) -> int:
        """Select the HDMI/optical TV input on a home-theater room."""
        device = self.resolve_speaker(speaker_name, coordinator=False)
        device.switch_to_tv()
        return 1

    def set_home_theater_option(
        self, option: str, enabled: bool, speaker_name: str
    ) -> int:
        """Toggle a current SoCo home-theater enhancement."""
        properties = {"night": "night_mode", "speech": "dialog_mode"}
        try:
            property_name = properties[option]
        except KeyError as error:
            raise ValueError(f"Unsupported home-theater option: {option}") from error
        device = self.resolve_speaker(speaker_name, coordinator=False)
        setattr(device, property_name, bool(enabled))
        return 1

    def active_speakers(self) -> tuple[Any, ...]:
        """Return every individual speaker in a currently playing group."""
        self._require_speakers()
        return tuple(
            speaker
            for speaker in self.speakers
            if self.transport_state(
                speaker.group.coordinator if len(speaker.group.members) > 1 else speaker
            )
            == "PLAYING"
        )

    def duck(self, amount: int) -> int:
        """Snapshot and reduce the volume of currently playing speakers."""
        targets = self.active_speakers()
        self._volume_snapshot = {
            str(getattr(device, "uid", device.player_name)): int(device.volume)
            for device in targets
        }
        for device in targets:
            device.set_relative_volume(-int(amount))
        return len(targets)

    def unduck(self) -> int:
        """Restore only speakers captured by the most recent duck operation."""
        restored = 0
        self._require_speakers()
        for device in self.speakers:
            uid = str(getattr(device, "uid", device.player_name))
            if uid in self._volume_snapshot:
                device.volume = self._volume_snapshot[uid]
                restored += 1
        self._volume_snapshot.clear()
        return restored

    def provider(self, service: ServiceInfo, device: Any) -> Any:
        """Create a provider bound to the target household device."""
        if service.name == MUSIC_LIBRARY:
            return self._music_library_cls(device)
        return self._music_service_cls(service.name, device=device)

    @staticmethod
    def is_authenticated(provider: Any, device: Any) -> bool:
        """Check SoCo's token store for this service and household."""
        if provider.auth_type == "Anonymous":
            return True
        if provider.auth_type not in {"DeviceLink", "AppLink"}:
            return False
        return provider.token_store.has_token(provider.service_id, device.household_id)

    def begin_authentication(self, service_name: str) -> tuple[Any, str]:
        """Start authentication and return the provider and registration URL."""
        self._require_speakers()
        service = self.registry.resolve(service_name)
        if service.name == MUSIC_LIBRARY:
            raise AuthenticationNotSupportedError(service.name)
        provider = self.provider(service, self.speakers[0])
        if provider.auth_type == "Anonymous" or self.is_authenticated(
            provider, self.speakers[0]
        ):
            return provider, ""
        if provider.auth_type not in {"DeviceLink", "AppLink"}:
            raise AuthenticationNotSupportedError(service.name)
        return provider, provider.begin_authentication()

    def complete_authentication(
        self, service_name: str, link_code: str, device_id: str | None
    ) -> None:
        """Finish authentication using brokered SMAPI link metadata."""
        self._require_speakers()
        service = self.registry.resolve(service_name)
        provider = self.provider(service, self.speakers[0])
        provider.complete_authentication(link_code, device_id)

    def search_and_play(
        self,
        service_name: str,
        speaker_name: str,
        category: str,
        query: str,
        artist: str | None = None,
    ) -> PlaybackResult:
        """Search a service, queue the best match, and start playback."""
        if not query or not query.strip():
            raise NoResultsError(query)
        device = self.resolve_speaker(speaker_name)
        service = self.registry.resolve(service_name)
        provider = self.provider(service, device)

        if service.name != MUSIC_LIBRARY and provider.auth_type not in {
            "Anonymous",
            "DeviceLink",
            "AppLink",
        }:
            raise AuthenticationNotSupportedError(service.name)

        search_category = self._resolve_category(provider, service, category)

        try:
            results = self._search(provider, service, search_category, query, artist)
        except MusicServiceAuthException as error:
            raise AuthenticationRequiredError(service.name) from error
        picked = self._pick_best(results, query, artist)
        if picked is None:
            raise NoResultsError(query)

        self._start_playback(device, provider, service, picked)
        return PlaybackResult(
            title=str(getattr(picked, "title", query)),
            service=service.name,
            speaker=device.player_name,
            category=category,
            artist=artist,
        )

    @classmethod
    def _start_playback(
        cls,
        device: Any,
        provider: Any,
        service: ServiceInfo,
        item: Any,
    ) -> None:
        """Queue an item, with a direct-stream fallback for SMAPI streams.

        Current Sonos firmware can reject stream-style SMAPI items (including
        TuneIn live stations and on-demand episodes) when they are inserted
        into the queue. In that case the provider's playable URI is resolved
        and sent directly to AVTransport. Other UPnP failures are preserved
        instead of being masked.
        """
        title = str(getattr(item, "title", ""))
        device.clear_queue()
        try:
            device.add_to_queue(item)
        except SoCoUPnPException as error:
            item_id = getattr(item, "id", None)
            can_fallback = (
                str(error.error_code) in _DIRECT_PLAY_FALLBACK_CODES
                and service.name != MUSIC_LIBRARY
                and item_id
                and callable(getattr(provider, "get_media_uri", None))
            )
            if not can_fallback:
                raise
            media_uri = str(provider.get_media_uri(item_id) or "")
            if not media_uri:
                raise
            device.play_uri(cls._resolve_media_uri(media_uri), title=title)
        else:
            device.play_from_queue(0)

    @staticmethod
    def _resolve_media_uri(media_uri: str) -> str:
        """Resolve a small single-entry HTTP M3U without flattening HLS.

        TuneIn's ``getMediaURI`` can return an M3U redirect document. Sonos may
        reject the document itself as an illegal MIME type, while the single
        HTTPS media URL inside it is directly playable. Responses are streamed
        and size-limited so an audio resource is never downloaded by OVOS.
        """
        parsed = urlsplit(media_uri)
        if parsed.scheme not in {"http", "https"}:
            return media_uri

        with requests.get(
            media_uri, timeout=_MEDIA_URI_TIMEOUT, stream=True
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            mime_type = content_type.partition(";")[0].strip().casefold()
            playlist_path = parsed.path.casefold().endswith((".m3u", ".m3u8"))
            if mime_type not in _PLAYLIST_CONTENT_TYPES and not playlist_path:
                return media_uri

            payload = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                payload.extend(chunk)
                if len(payload) > _MAX_PLAYLIST_BYTES:
                    return media_uri

        lines = payload.decode(
            response.encoding or "utf-8", errors="replace"
        ).splitlines()
        if any(line.lstrip().upper().startswith("#EXT-X-") for line in lines):
            return media_uri
        entries = [
            line.strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(entries) != 1:
            return media_uri
        resolved = urljoin(media_uri, entries[0])
        if urlsplit(resolved).scheme not in {"http", "https"}:
            return media_uri
        return resolved

    @staticmethod
    def _resolve_category(provider: Any, service: ServiceInfo, category: str) -> str:
        candidates = CATEGORY_ALIASES.get(category, (category,))
        if service.name == MUSIC_LIBRARY:
            available = MUSIC_LIBRARY_CATEGORIES
        else:
            available = set(provider.available_search_categories)
        normalized = {normalize_name(value): value for value in available}
        for candidate in candidates:
            resolved = normalized.get(normalize_name(candidate))
            if resolved is not None:
                return resolved
        raise CategoryNotSupportedError(f"{service.name}:{category}")

    @classmethod
    def _search(
        cls,
        provider: Any,
        service: ServiceInfo,
        category: str,
        query: str,
        artist: str | None,
    ) -> list[Any]:
        if service.name != MUSIC_LIBRARY:
            results = list(provider.search(category, query) or [])
            artist_categories = {
                normalize_name(value) for value in CATEGORY_ALIASES["artists"]
            }
            if normalize_name(category) in artist_categories:
                return cls._expand_artist_results(provider, results, query)
            return cls._expand_provider_results(provider, results, query)
        if category == "tracks" and artist:
            return list(provider.search_track(artist=artist, track=query) or [])
        if category == "albums" and artist:
            return list(
                provider.get_album_artists(
                    search_term=query,
                    subcategories=[artist],
                    complete_result=True,
                )
                or []
            )
        method = getattr(provider, f"get_{category}")
        return list(method(search_term=query, complete_result=True) or [])

    @classmethod
    def _expand_artist_results(
        cls, provider: Any, results: list[Any], query: str
    ) -> list[Any]:
        """Prefer an artist's own top tracks over a related-artist radio seed."""
        if any(cls._is_queueable(item) for item in results):
            return results

        containers = [item for item in results if cls._item_flag(item, "can_enumerate")]
        containers.sort(key=lambda item: cls._match_score(item, query), reverse=True)
        fallback: list[Any] = []
        for container in containers:
            try:
                children = list(provider.get_metadata(container, count=100) or [])
            except (OSError, ValueError, requests.RequestException, SoCoException):
                continue

            queueable = [item for item in children if cls._is_queueable(item)]
            track_lists = [
                item
                for item in queueable
                if normalize_name(str(getattr(item, "item_type", ""))) == "tracklist"
            ]
            if track_lists:
                return track_lists

            exact_artist_items = [
                item
                for item in queueable
                if normalize_name(cls._item_artist(item)) == normalize_name(query)
            ]
            if exact_artist_items:
                return exact_artist_items

            if not fallback:
                fallback = cls._expand_provider_results(provider, children, query)
        return fallback or results

    @classmethod
    def _expand_provider_results(
        cls,
        provider: Any,
        results: list[Any],
        query: str,
        remaining_depth: int = 3,
    ) -> list[Any]:
        """Browse SMAPI containers until a genuinely playable item is found.

        Providers such as TuneIn return search-result buckets, then show
        containers, and only expose playable episodes below the original
        search. A container marked ``canEnumerate`` must not be passed to the
        Sonos queue when ``canPlay`` is false.
        """
        if any(cls._is_queueable(item) for item in results):
            return results
        if remaining_depth <= 0:
            return results

        containers = [
            item
            for item in results
            if cls._item_flag(item, "can_enumerate") is True
            or (
                cls._item_flag(item, "can_enumerate") is None
                and cls._is_container(item)
            )
        ]
        containers.sort(key=lambda item: cls._match_score(item, query), reverse=True)
        for container in containers:
            try:
                children = list(provider.get_metadata(container, count=100) or [])
            except (OSError, ValueError, requests.RequestException, SoCoException):
                continue
            expanded = cls._expand_provider_results(
                provider,
                children,
                query,
                remaining_depth=remaining_depth - 1,
            )
            if any(cls._is_queueable(item) for item in expanded):
                return expanded
        return results

    @classmethod
    def _pick_best(
        cls, results: Iterable[Any], query: str, artist: str | None
    ) -> Any | None:
        usable = [item for item in results if cls._is_queueable(item)]
        if artist:
            artist_scores = [
                (cls._artist_match_score(item, artist), item) for item in usable
            ]
            best_artist_score = max(
                (score for score, _item in artist_scores), default=0
            )
            if best_artist_score:
                usable = [
                    item for score, item in artist_scores if score == best_artist_score
                ]
            elif any(cls._item_artist(item) for item in usable):
                return None
        if not usable:
            return None
        return max(usable, key=lambda item: cls._match_score(item, query))

    @staticmethod
    def _match_score(item: Any, query: str) -> tuple[int, float]:
        title = str(getattr(item, "title", ""))
        title_key = normalize_name(title)
        query_key = normalize_name(query)
        exact = title_key == query_key
        contains_query = bool(query_key and query_key in title_key)
        similarity = SequenceMatcher(None, query_key, title_key).ratio()
        # ``max`` and Python's sort are stable. Leaving equal scores equal keeps
        # the provider's relevance ordering instead of inventing a lexical tie
        # breaker. Suffixes such as remaster years and take numbers also remain
        # tied, so Spotify's ranking chooses the canonical recording.
        if exact:
            return 2, 1.0
        if contains_query:
            return 1, 1.0
        return 0, similarity

    @staticmethod
    def _item_flag(item: Any, name: str) -> bool | None:
        try:
            return getattr(item, name)
        except AttributeError:
            return None

    @staticmethod
    def _is_queueable(item: Any) -> bool:
        resources = getattr(item, "resources", None)
        can_play = SonosController._item_flag(item, "can_play")
        return (
            bool(resources)
            and can_play is not False
            and not SonosController._is_container(item)
        )

    @staticmethod
    def _is_container(item: Any) -> bool:
        """Identify SMAPI browse containers even when flags are omitted."""
        item_type = normalize_name(str(getattr(item, "item_type", "")))
        return item_type in {"collection", "container"}

    @classmethod
    def _artist_matches(cls, item: Any, requested_artist: str) -> bool:
        return cls._artist_match_score(item, requested_artist) > 0

    @classmethod
    def _artist_match_score(cls, item: Any, requested_artist: str) -> int:
        """Prefer exact artist names while retaining useful partial matches."""
        actual = normalize_name(cls._item_artist(item))
        requested = normalize_name(requested_artist)
        if not actual or not requested:
            return 0
        if actual == requested:
            return 2
        return int(actual in requested or requested in actual)

    @staticmethod
    def _item_artist(item: Any) -> str | None:
        direct = getattr(item, "artist", None)
        if direct:
            return str(direct)
        track_metadata = getattr(item, "track_metadata", None)
        artist = getattr(track_metadata, "artist", None) if track_metadata else None
        if artist:
            return str(artist)
        metadata = getattr(item, "metadata", {})
        if isinstance(metadata, dict):
            for key in ("artist", "album_artist"):
                if metadata.get(key):
                    return str(metadata[key])
        return None
