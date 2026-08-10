# Sonos Controller for OpenVoiceOS

Control Sonos rooms and search the music services configured for your Sonos
household.

> This community skill is not commissioned or supported by Sonos, Inc. Sonos
> is a registered trademark of Sonos, Inc.

## Features

- Discovers Sonos rooms on the local network and respects group coordinators.
- Plays tracks, albums, artists, playlists, podcasts, and radio stations.
- Controls play, pause, stop, next, previous, shuffle, repeat, exact or relative
  volume, and mute.
- Groups two rooms, groups the whole household, and isolates a room again.
- Selects the TV source and controls Night Mode and Speech Enhancement on
  compatible Sonos home-theater products.
- Reports the current track, artist, and speaker information.
- Optionally ducks active Sonos playback while OVOS is listening.
- Discovers music-service names, subscription state, authentication type, and
  search categories from the Sonos household at runtime.

## Music services

The skill does not maintain a hard-coded provider allow-list. It supports the
local Music Library and every SMAPI music service advertised by the Sonos
system, including common providers such as Amazon Music, Apple Music, Deezer,
Napster, Plex, Qobuz, SoundCloud, Spotify, TIDAL, TuneIn, and YouTube Music.

A provider can only handle a request when it exposes the corresponding Sonos
search category. For example, a service that exposes tracks but not playlists
can play track requests but cannot search for an arbitrary playlist. Podcast
requests also recognize the `shows` category used by services such as TuneIn.
Provider-specific names such as `Books`, `Authors`, `Users`, `MixStations`, and
`Radios` are normalized to their closest generic voice category.

If current Sonos firmware rejects a live or on-demand SMAPI stream from the
queue, the skill resolves the provider's playable URI and follows a bounded,
single-entry M3U redirect instead; unrelated UPnP failures are not masked.

Link paid services to the same Sonos household in the Sonos app before using
them. The skill first attempts the household service, because providers such as
Deezer can work through Sonos without a separate local token, and only asks for
DeviceLink or AppLink authentication after a real SMAPI authentication failure.
For AppLink providers such as Spotify, being connected in the Sonos app does
not give a local SoCo client access to the app's private credential. Complete
the skill's one-time authentication flow as well; this adds a separate token for
the same Sonos household and does not disconnect or replace the account in the
Sonos app.
Anonymous services need no additional login. Legacy UserId authentication
cannot be completed by SoCo and the skill reports that limitation instead of
failing playback silently.

## Examples

- “Play song I Gotta Feeling on living room”
- “Play song I Gotta Feeling by Black Eyed Peas from Spotify on living room”
- “Play soundtrack playlist from Apple Music in dining room”
- “Play Back to Front album by Lionel Richie from TIDAL in dining room”
- “Play The Daily podcast from TuneIn in office”
- “Play music by Michael Jackson from Spotify in office”
- “Play station CBC Radio One from TuneIn in office”
- “Discover Sonos devices”
- “What are my music services?”
- “What is playing on living room?”
- “Volume up on living room”
- “Set the volume to 12 percent on office”
- “Mute office”
- “Group office with kitchen”
- “Play everywhere from living room”
- “Pause music”
- “Enable shuffle mode on living room”
- “Enable Night Mode on living room”
- “Turn on Speech Enhancement on living room”
- “Authenticate Spotify with Sonos”

## Alexa and Sonos Voice Control parity

The official Alexa integration documents music requests, room targeting, basic
transport, volume, TV-source control, Night Mode, and Speech Enhancement. This
skill covers that Sonos-control surface except HDMI-CEC television power, which
is not exposed by SoCo's local UPnP API.

It also goes beyond Alexa-on-Sonos with indexed Music Library/NAS playback,
artist and station searches, exact volume, mute, shuffle/repeat, current-track
details, and voice grouping/ungrouping. Sonos explicitly lists Music Library
playback as unavailable in Alexa, while grouping is documented as a Sonos Voice
Control feature.

- [Alexa control documented by Sonos](https://support.sonos.com/en-us/article/control-sonos-with-amazon-alexa)
- [Sonos Voice Control grouping](https://www.sonos.com/en-us/guides/sonosvoicecontrol)

## Installation

Install the skill in the same Python environment as OVOS:

```bash
pip install git+https://github.com/smartgic/skill-sonos-controller
```

Sonos discovery uses local multicast traffic. The OVOS host and Sonos players
must be reachable on the same LAN, and client isolation must be disabled. The
provided container uses host networking for this reason:

```bash
cd docker
docker compose up -d
```

## Configuration

OVOS stores settings under the skill ID
`skill-sonos-controller.smartgic`. Available options are:

| Option | Default | Description |
| --- | --- | --- |
| `default_source` | `Music Library` | Service used when an utterance does not name one. The name is case-insensitive. |
| `link_code` | empty | Temporary code used to finish DeviceLink or AppLink authentication. |
| `duck` | `false` | Reduce active Sonos volume while OVOS listens. |
| `playing_confirmation` | `false` | Speak a confirmation after playback starts. |
| `searching_confirmation` | `true` | Announce before searching a service. |
| `url_shortener` | `https://sonos.smartgic.io` | Broker used to make a long provider registration URL speakable. |

### Authenticate a service

1. Say “Authenticate Spotify with Sonos,” replacing Spotify with the service
   you want to use.
2. Visit the spoken `sonos.smartgic.io/CODE` URL and complete the provider's
   login flow.
3. Put `CODE` in the skill's `link_code` setting.
4. Say “Finish Sonos authentication.” The temporary broker record is deleted
   after the token is stored successfully.

SoCo stores tokens in its user configuration directory, normally
`~/.config/SoCo/token_store.json`. Persist that directory when the skill runs
in a container.

## Development

The supported runtime matrix is Python 3.11, 3.12, 3.13, and 3.14. The SoCo
constraint currently resolves to 0.31.2, the latest published release, while
allowing compatible 0.31 patch updates. CI also runs against the current OVOS
alpha constraint set so newer workshop and bus APIs cannot regress silently.

The integration is separated from the OVOS voice layer and can be tested
without Sonos hardware:

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest
.venv/bin/python -m build
```

Intent routing is also tested end to end with OVOScope. This boots the real
MiniCroft skill loader and tests all 36 intents in all 16 locales with
Padacioso, the complete English surface with Padatious and trainable model2vec,
model2vec free-form entity hydration, and a runtime-advertised provider name
(650 cases total). The frozen model2vec classifier cannot learn newly registered
skill labels, so the suite deliberately uses its prototype pipeline. The test
replaces the Sonos controller before skill construction, so it never discovers
or changes speakers on the local network:

```bash
.venv/bin/pip install --pre -e '.[test,end2end]'
.venv/bin/pytest test/end2end -v
```

Pull requests also run the official reusable OVOScope workflow with bus-message
coverage enabled and the official `ovos-localize` validation workflow. Locale
resources can be regenerated and schema-checked with:

```bash
python scripts/generate_locales.py
ovos-localize-cli --repo . --report-format text
```

There is also an opt-in hardware test. It refuses to run unless the selected
speaker is stopped, ungrouped, and has an empty queue. Playback is capped at
volume 5 and the original volume, mute state, transport state, media URI,
metadata, and empty queue are restored. `SONOS_LIVE_CASES` can provide a JSON
matrix of services, categories, queries, and optional artists. Supplying a
second stopped room also exercises reversible grouping:

```bash
SONOS_LIVE_TEST=1 \
SONOS_LIVE_SPEAKER=Office \
SONOS_LIVE_GROUP_MEMBER=Library \
SONOS_LIVE_VOLUME=2 \
SONOS_LIVE_CASES='[{"service":"Music Library","category":"tracks","query":"Imagine"}]' \
.venv/bin/pytest -q test/live
```

Live validation of each paid provider still requires an account for that
provider. Unit tests cover the shared SMAPI search and authentication contract,
including dynamically advertised names and provider-specific categories.
Direct search and authentication also inherit
[SoCo's upstream provider limitations](https://pypi.org/project/soco/0.31.2/);
its current release still describes music-service support as unstable.

## Languages

- Basque (`eu-ES`)
- Catalan (`ca-ES`)
- Danish (`da-DK`)
- Dutch, Belgium (`nl-BE`)
- Dutch, Netherlands (`nl-NL`)
- English (`en-US`)
- French (`fr-FR`)
- Galician (`gl-ES`)
- German (`de-DE`)
- Italian (`it-IT`)
- Persian (`fa-IR`)
- Polish (`pl-PL`)
- Portuguese, Brazil (`pt-BR`)
- Portuguese, Portugal (`pt-PT`)
- Spanish (`es-ES`)
- Ukrainian (`uk-UA`)

## Credits

- [Smart'Gic](https://smartgic.io/)
- [SoCo](https://github.com/SoCo/SoCo)
- [@rbcolom](https://github.com/rbcolom) — Italian translation
