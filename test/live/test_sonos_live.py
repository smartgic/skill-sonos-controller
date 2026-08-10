"""Opt-in, state-restoring integration test for a real Sonos household."""

from __future__ import annotations

import json
import os
from time import monotonic, sleep

import pytest

from skill_sonos_controller.controller import SonosController

pytestmark = pytest.mark.live_sonos


def _required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"{name} is required for live Sonos testing")
    return value


def _playback_cases() -> list[dict[str, str]]:
    raw = os.environ.get("SONOS_LIVE_CASES", "").strip()
    if raw:
        cases = json.loads(raw)
        if not isinstance(cases, list) or not all(
            isinstance(case, dict) for case in cases
        ):
            raise ValueError("SONOS_LIVE_CASES must be a JSON list of objects")
        return cases
    return [
        {
            "service": os.environ.get("SONOS_LIVE_SERVICE", "TuneIn").strip(),
            "category": os.environ.get("SONOS_LIVE_CATEGORY", "podcasts").strip(),
            "query": os.environ.get("SONOS_LIVE_QUERY", "The Daily").strip(),
        }
    ]


def _wait_for_isolated_rooms(
    controller: SonosController, room_names: tuple[str, ...], timeout: float = 10
) -> tuple[object, ...]:
    """Poll fresh topology until asynchronous ungrouping has propagated."""
    deadline = monotonic() + timeout
    devices: tuple[object, ...] = ()
    while monotonic() < deadline:
        controller.refresh()
        devices = tuple(
            controller.resolve_speaker(name, coordinator=False) for name in room_names
        )
        if all(
            device.group.coordinator.uid == device.uid
            and len(device.group.members) == 1
            for device in devices
        ):
            return devices
        sleep(0.25)
    raise AssertionError(f"rooms did not become isolated: {room_names}")


def _exercise_playback_case(
    controller: SonosController,
    speaker_name: str,
    case: dict[str, str],
    test_volume: int,
) -> None:
    """Play one case briefly and restore transport, URI, queue, and volume."""
    service = str(case["service"]).strip()
    category = str(case["category"]).strip()
    query = str(case["query"]).strip()
    artist = str(case.get("artist") or "").strip() or None
    device = controller.resolve_speaker(speaker_name, coordinator=False)

    media = device.avTransport.GetMediaInfo([("InstanceID", 0)])
    original = {
        "volume": int(device.volume),
        "mute": bool(device.mute),
        "state": controller.transport_state(device),
        "queue_length": len(list(device.get_queue())),
        "media_uri": media.get("CurrentURI", ""),
        "media_metadata": media.get("CurrentURIMetaData", ""),
    }
    if original["state"] != "STOPPED" or original["queue_length"] != 0:
        pytest.skip("live tests require a stopped speaker with an empty queue")

    state = ""
    observed_volume = None
    try:
        # Some models apply a source-specific autoplay volume during the
        # transition. Keep the speaker muted until the cap is re-applied after
        # PLAYING is reached.
        device.mute = True
        device.volume = test_volume
        result = controller.search_and_play(
            service_name=service,
            speaker_name=speaker_name,
            category=category,
            query=query,
            artist=artist,
        )
        deadline = monotonic() + 15
        while monotonic() < deadline:
            state = controller.transport_state(device)
            if state == "PLAYING":
                break
            sleep(0.25)
        device.mute = True
        device.volume = test_volume
        observed_volume = int(device.volume)
        if state == "PLAYING" and not original["mute"]:
            device.mute = False
            sleep(0.5)
    finally:
        device.stop()
        device.clear_queue()
        device.avTransport.SetAVTransportURI(
            [
                ("InstanceID", 0),
                ("CurrentURI", original["media_uri"]),
                ("CurrentURIMetaData", original["media_metadata"]),
            ]
        )
        device.stop()
        device.mute = original["mute"]
        device.volume = original["volume"]

    assert result.service == service
    assert result.speaker == speaker_name
    assert state == "PLAYING"
    assert observed_volume == test_volume
    assert int(device.volume) == original["volume"]
    assert bool(device.mute) is original["mute"]
    assert controller.transport_state(device) == original["state"]
    assert len(list(device.get_queue())) == original["queue_length"]
    restored_media = device.avTransport.GetMediaInfo([("InstanceID", 0)])
    assert restored_media.get("CurrentURI", "") == original["media_uri"]


def test_search_and_play_on_an_idle_isolated_speaker() -> None:
    """Play a configurable matrix at low volume and restore every case."""
    if os.environ.get("SONOS_LIVE_TEST") != "1":
        pytest.skip("set SONOS_LIVE_TEST=1 to authorize real speaker control")

    speaker_name = _required_setting("SONOS_LIVE_SPEAKER")
    requested_volume = int(os.environ.get("SONOS_LIVE_VOLUME", "2"))
    test_volume = max(1, min(5, requested_volume))
    controller = SonosController()
    controller.refresh()
    device = controller.resolve_speaker(speaker_name, coordinator=False)
    if device.player_name.casefold() != speaker_name.casefold():
        pytest.skip("live tests require an exact speaker name")
    if device.group.coordinator.uid != device.uid or len(device.group.members) != 1:
        pytest.skip("live tests require an ungrouped speaker")

    for case in _playback_cases():
        _exercise_playback_case(controller, speaker_name, case, test_volume)


def test_pairwise_grouping_and_restoration() -> None:
    """Join two stopped rooms while muted, then restore both rooms exactly."""
    if os.environ.get("SONOS_LIVE_TEST") != "1":
        pytest.skip("set SONOS_LIVE_TEST=1 to authorize real speaker control")

    coordinator_name = _required_setting("SONOS_LIVE_SPEAKER")
    member_name = _required_setting("SONOS_LIVE_GROUP_MEMBER")
    controller = SonosController()
    controller.refresh()
    coordinator = controller.resolve_speaker(coordinator_name, coordinator=False)
    member = controller.resolve_speaker(member_name, coordinator=False)
    if coordinator.uid == member.uid:
        pytest.skip("grouping requires two different rooms")
    for device in (coordinator, member):
        isolated = len(device.group.members) == 1
        stopped = controller.transport_state(device) == "STOPPED"
        if not isolated or not stopped:
            pytest.skip("grouping requires two stopped, isolated rooms")

    original = {
        device.uid: {"volume": int(device.volume), "mute": bool(device.mute)}
        for device in (coordinator, member)
    }
    try:
        for device in (coordinator, member):
            device.mute = True
            device.volume = 1
        assert controller.group_speakers(coordinator_name, (member_name,)) == 1
        assert member.group.coordinator.uid == coordinator.uid
        assert {device.uid for device in member.group.members} == {
            coordinator.uid,
            member.uid,
        }
    finally:
        if len(member.group.members) > 1:
            member.unjoin()
        coordinator, member = _wait_for_isolated_rooms(
            controller, (coordinator_name, member_name)
        )
        for device in (coordinator, member):
            device.mute = original[device.uid]["mute"]
            device.volume = original[device.uid]["volume"]

    assert len(coordinator.group.members) == 1
    assert len(member.group.members) == 1
    for device in (coordinator, member):
        assert int(device.volume) == original[device.uid]["volume"]
        assert bool(device.mute) is original[device.uid]["mute"]
