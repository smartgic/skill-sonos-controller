from mycroft import MycroftSkill, intent_handler
from soco import discover
from soco.music_services import MusicService


class SonosController(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
        self.speakers = []

    def _discovery(self):
        self.speakers = discover()
        if not self.speakers:
            self.log.error(
                'I could not find any devices on your network')
            self.speak_dialog('error.disovery')
        else:
            self.log.info(
                '{} device(s) found'.format(len(self.speakers)))

    @intent_handler('sonos.discovery.intent')
    def handle_speaker_discovery(self, message):
        self._discovery()
        if self.speakers:
            self.speak_dialog('sonos.discovery', data={
                              "total": len(self.speakers)})
            list_device = self.ask_yesno('sonos.list')
            if list_device == 'yes':
                for speaker in self.speakers:
                    self.speak(speaker.player_name)

    @intent_handler('sonos.service.intent')
    def handle_subscribed_services(self, message):
        # Commented until SoCo integrates this method back
        # services = MusicService.get_subscribed_services_names()
        services = ['spotify', 'amazon music']
        if services:
            self.speak_dialog('sonos.service', data={
                              "total": len(services)})
            list_service = self.ask_yesno('sonos.list')
            if list_service == 'yes':
                for service in services:
                    self.speak(service)
        else:
            self.log.warning('no subscription found to any music service')
            self.speak_dialog('error.list')

    def initialize(self):
        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()
        self._discovery()

    def on_settings_changed(self):
        return


def create_skill():
    return SonosController()
