from mycroft import MycroftSkill, intent_handler
from soco import discover


class SonosController(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
        self.speakers = []

    def _discovery(self):
        self.speakers = discover()
        if not self.speakers:
            self.log.error(
                'I could not find any Sonos devices on your network')
            self.speak_dialog('error.disovery')
        else:
            self.log.info(
                '{} Sonos device(s) found'.format(len(self.speakers)))

    def _intents(self):
        self.register_intent_file(
            'sonos.discovery.intent', self.handle_speaker_discovery)

    def handle_speaker_discovery(self, message):
        self._discovery()
        if self.speakers:
            self.speak_dialog('sonos.discovery', data={
                              "total": len(self.speakers)})
            list_devices = self.ask_yesno('sonos.list')
            if list_devices == 'yes':
                for speaker in self.speakers:
                    self.speak(speaker.player_name)

    def initialize(self):
        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()
        self._intents()

    def on_settings_changed(self):
        return


def create_skill():
    return SonosController()
