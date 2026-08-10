"""Domain exceptions raised by the Sonos integration layer."""


class SonosControllerError(Exception):
    """Base exception for expected controller failures."""


class NoSpeakersError(SonosControllerError):
    """No Sonos players were discovered."""


class SpeakerNotFoundError(SonosControllerError):
    """A requested Sonos room could not be resolved."""


class AmbiguousSpeakerError(SonosControllerError):
    """A partial room name matched more than one player."""


class ServiceNotFoundError(SonosControllerError):
    """A requested music service is not advertised by the household."""


class CategoryNotSupportedError(SonosControllerError):
    """The music service cannot search the requested media category."""


class NoResultsError(SonosControllerError):
    """A music search completed without a usable result."""


class AuthenticationRequiredError(SonosControllerError):
    """The selected service requires authentication."""


class AuthenticationNotSupportedError(SonosControllerError):
    """SoCo cannot authenticate the selected service's auth scheme."""
