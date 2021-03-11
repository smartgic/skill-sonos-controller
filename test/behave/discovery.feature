Feature: discovery
  Scenario: Discover the Sonos devices
    Given an english speaking user
     When the user says "discover sonos devices"
     Then "mycroft-sonos-controller-skill" should reply with dialog from "sonos.discovery.dialog"