Feature: discovery
  Scenario: Discover the Sonos devices
    Given an english speaking user
      And a 1 minute timeout
     When the user says "discover sonos devices"
     Then "mycroft-sonos-controller-skill" should reply with dialog from "sonos.discovery.dialog"