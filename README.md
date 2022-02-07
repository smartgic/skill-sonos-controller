[![Build Status](https://travis-ci.com/smartgic/mycroft-sonos-controller-skill.svg?branch=20.8.1)](https://travis-ci.com/github/smartgic/mycroft-sonos-controller-skill) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![contributions welcome](https://img.shields.io/badge/contributions-welcome-pink.svg?style=flat)](https://github.com/smartgic/mycroft-sonos-controller-skill/pulls) [![Skill: MIT](https://img.shields.io/badge/mycroft.ai-skill-blue)](https://mycroft.ai) [![Discord](https://img.shields.io/discord/809074036733902888)](https://discord.gg/sHM3Duz5d3)

<p align="center">
  <img alt="Mycrof Sonos Controller Skill" src="docs/mycroft-sonos-logo.png" width="500px">
</p>

# Sonos Controller

Control Sonos speakers with music services support such as Spotify, Deezer, Amazon Music, etc...

## Disclaimer

*This plugin is not officially commissioned/supported by Sonos. The trademark "Sonos" is registered by "Sonos, Inc."*

## About

[Sonos](https://www.sonos.com) is the ultimate wireless home sound system: a whole-house WiFi network that fills your home with brilliant sound, room by room.

This skill interacts with your Sonos devices and allows you to play music from different music sources such as:

* Local library
* Amazon Music *(account required)*
* Deezer *(account required)*
* Plex *(account required)*
* Spotify *(account required)*
* Tidal *(account required)*

Before using a music service, **make sure that you linked** your service account to your Sonos devices by using the Sonos application:

<img src='docs/sonos-app.png' width='450'/>

## Examples

* "play i got a feeling on living room"
* "play i got a feeling by black eyed peas on living room"
* "play i got a feeling from spotify on living room"
* "play i got a feeling by black eyed peas from spotify on living room"
* "play soundtrack playlist on dining room"
* "play soundtrack playlist from spotify on dining room"
* "play soundtrack album on dining room"
* "play back to front album by lionel richie on dining room"
* "play back to front album by lionel richie from spotify on dining room"
* "play soundtrack album from spotify on dining room"
* "play the mysterious universe podcast from plex on office"
* "discover sonos devices"
* "what is playing"
* "which artist is playing"
* "what are my music services"
* "volume louder"
* "volume quieter"
* "volume down on living room"
* "volume up"
* "quieter"
* "louder"
* "pause music"
* "stop music"
* "resume music"
* "shuffle off"
* "shuffle on"
* "disable repeat mode"
* "enable repeat mode"
* "next music"
* "previous music"
* "give me information on dining room device"
* "give me detailed information about library speaker"

## Installation

Make sure to be within the Mycroft `virtualenv` before running the `msm` command.

```shell
. mycroft-core/venv-activate.sh
msm install https://github.com/smartgic/mycroft-sonos-controller-skill.git
```

## Configuration

This skill utilizes the `settings.json` file which allows you to configure this skill via `home.mycroft.ai` after a few seconds of having the skill installed you should see something like below in the <https://home.mycroft.ai/#/skill> location:

<img src='docs/sonos-controller-config.png' width='450'/>

Fill this out with your appropriate information and hit the `save` button.

When Spotify music service is selected Mycroft will speak to you with a URL and code to follow. This URL is <https://sonos.smartgic.io/CODE> where `CODE` will be automatically and randomly generated by Mycroft and spoken to you *(e.g. Visit sonos.smartgic.io/FRK7Y)*.

<https://sonos.smartgic.io> is a URL shortener system which will temporary store the music service authentication URL. Once the authentication is done, the URL will be deleted from the URL shortener system.

This link will redirect you to the music service authentication login page using `https` protocol.

<img src='docs/spotify-auth.png' width='450'/>

<img src='docs/sonos-spotify-agreement.png' width='450'/>

Once you successfully logged to Spotify, enter the same code as provided before into the `Link Code` field. Mycroft will confirm the configuration and gives you some example of what you could say.

## Supported languages

* English
* French
* Italian

## Credits

* [Smart'Gic](https://smartgic.io/)
* [SoCo](https://github.com/SoCo/SoCo)
* [@rbcolom](https://github.com/rbcolom) - Italian translation

## Category

**Music & Audio**

## Tags

#music
#audio
#sonos
#sound
#smarthome
#spotify
#deezer
#amazonmusic
#plex
#tidal
