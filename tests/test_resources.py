"""Checks that package metadata and OVOS resources cannot drift."""

import ast
import json
import tomllib
from pathlib import Path
from string import Formatter

from skill_sonos_controller import CLASSIFIER_INTENT_HANDLERS, DEFAULT_SETTINGS
from skill_sonos_controller.constants import SUPPORTED_LOCALES

PROJECT_ROOT = Path(__file__).parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "skill_sonos_controller"


def test_every_packaged_intent_has_a_classifier_handler():
    intents = {
        path.name
        for path in (PACKAGE_ROOT / "locale" / "en-us" / "intents").glob("*.intent")
    }
    assert set(CLASSIFIER_INTENT_HANDLERS) == intents


def test_packaged_and_marketplace_settings_metadata_match():
    assert (PROJECT_ROOT / "settingsmeta.json").read_bytes() == (
        PACKAGE_ROOT / "settingsmeta.json"
    ).read_bytes()


def test_settings_metadata_matches_runtime_defaults():
    metadata = json.loads((PROJECT_ROOT / "settingsmeta.json").read_text())
    fields = metadata["skillMetadata"]["sections"][0]["fields"]
    values = {field["name"]: field["value"] for field in fields}
    normalized = {
        name: value.casefold() == "true" if value in {"true", "false"} else value
        for name, value in values.items()
    }
    assert normalized == DEFAULT_SETTINGS


def test_compatibility_requirements_match_project_dependencies():
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    requirements = {
        line.strip()
        for line in (PROJECT_ROOT / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert requirements == set(project["project"]["dependencies"])


def test_all_locales_have_the_same_intent_and_dialog_resources():
    locales = PACKAGE_ROOT / "locale"
    assert {path.name for path in locales.iterdir() if path.is_dir()} == set(
        SUPPORTED_LOCALES
    )
    expected = {
        path.relative_to(locales / "en-us")
        for path in (locales / "en-us").rglob("*")
        if path.is_file()
    }
    assert expected
    for locale in SUPPORTED_LOCALES:
        actual = {
            path.relative_to(locales / locale)
            for path in (locales / locale).rglob("*")
            if path.is_file()
        }
        assert actual == expected


def _fields(path):
    return {
        field
        for _, field, _, _ in Formatter().parse(path.read_text(encoding="utf-8"))
        if field is not None
    }


def test_localized_dialogs_preserve_the_english_interpolation_fields():
    locales = PACKAGE_ROOT / "locale"
    for english in (locales / "en-us" / "dialog").glob("*.dialog"):
        expected = _fields(english)
        for locale in SUPPORTED_LOCALES:
            assert _fields(locales / locale / "dialog" / english.name) == expected


def test_every_intent_and_entity_has_localized_content():
    locales = PACKAGE_ROOT / "locale"
    for locale in SUPPORTED_LOCALES:
        for path in (locales / locale).rglob("*"):
            if path.is_file():
                assert path.read_text(encoding="utf-8").strip(), path


def test_all_localized_resources_have_canonical_text_formatting():
    """Keep generated and hand-maintained resources byte-stable."""
    locales = PACKAGE_ROOT / "locale"
    for path in locales.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        assert content.endswith("\n"), path
        assert all(line == line.rstrip() for line in content.splitlines()), path
        nonempty = [line for line in content.splitlines() if line]
        assert len(nonempty) == len(set(nonempty)), path


def test_dialog_catalog_has_no_missing_or_obsolete_files():
    source = ast.parse((PACKAGE_ROOT / "__init__.py").read_text(encoding="utf-8"))
    referenced = {
        call.args[0].value
        for call in ast.walk(source)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in {"ask_yesno", "speak_dialog"}
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    }
    referenced.update(
        {
            "error.album",
            "error.album.artist",
            "error.artist",
            "error.playlist",
            "error.podcast",
            "error.station",
            "error.track",
            "error.track.artist",
            "sonos.album.artist",
            "sonos.album.result",
            "sonos.artist.result",
            "sonos.playlist.result",
            "sonos.podcast.result",
            "sonos.station.result",
            "sonos.track.artist",
            "sonos.track.result",
        }
    )
    dialogs = {
        path.name.removesuffix(".dialog")
        for path in (PACKAGE_ROOT / "locale" / "en-us" / "dialog").glob("*.dialog")
    }
    assert dialogs == referenced


def test_every_locale_recognizes_all_canonical_music_service_names():
    locales = PACKAGE_ROOT / "locale"
    canonical = {
        line.strip()
        for line in (locales / "en-us" / "intents" / "service.entity")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    for locale in SUPPORTED_LOCALES:
        localized = {
            line.strip()
            for line in (locales / locale / "intents" / "service.entity")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        }
        assert canonical <= localized


def test_code_values_keep_stable_system_characters_in_every_locale():
    locales = PACKAGE_ROOT / "locale"
    expected = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    for locale in SUPPORTED_LOCALES:
        systems = {
            line.rsplit(",", maxsplit=1)[1].strip()
            for line in (locales / locale / "dialog" / "codes.value")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        }
        assert systems == expected
