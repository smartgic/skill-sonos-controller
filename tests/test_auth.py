"""Tests for the temporary Sonos authentication-link broker client."""

from unittest.mock import Mock

import pytest

from skill_sonos_controller.auth import AuthenticationBroker


def response(payload):
    result = Mock()
    result.json.return_value = payload
    return result


def test_create_extracts_code_from_full_short_url():
    session = Mock()
    session.post.return_value = response({"link": "https://sonos.example/AB12"})
    broker = AuthenticationBroker("https://sonos.example/", session=session)

    code = broker.create("https://spotify.example/auth", "xyz", "device", "Spotify")

    assert code == "AB12"
    session.post.assert_called_once_with(
        "https://sonos.example",
        json={
            "target": "https://spotify.example/auth",
            "extras": {"code": "xyz", "device": "device", "service": "Spotify"},
        },
        timeout=10,
    )
    session.post.return_value.raise_for_status.assert_called_once_with()


def test_resolve_and_delete_link_metadata():
    session = Mock()
    session.get.return_value = response(
        {"extras": {"code": "xyz", "device": "device", "service": "Spotify"}}
    )
    session.delete.return_value = response({})
    broker = AuthenticationBroker("https://sonos.example", session=session)

    link = broker.resolve("AB12")
    broker.delete("AB12")

    assert (link.code, link.device_id, link.service) == ("xyz", "device", "Spotify")
    session.get.assert_called_once_with("https://sonos.example/AB12/info", timeout=10)
    session.delete.assert_called_once_with("https://sonos.example/AB12", timeout=10)


def test_resolve_rejects_missing_metadata():
    session = Mock()
    session.get.return_value = response({"hello": "world"})

    with pytest.raises(ValueError):
        AuthenticationBroker("https://sonos.example", session=session).resolve("bad")
