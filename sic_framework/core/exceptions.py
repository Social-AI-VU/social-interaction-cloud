"""
exceptions.py

This module defines the exception hierarchy for the Social Interaction Cloud (SIC) framework.
Centralizing exceptions allows for consistent error handling and better documentation.
"""

class SICError(Exception):
    """Base class for all SIC framework exceptions."""
    pass


# -----------------------------------------------------------------------------
# Component & Connector Errors
# -----------------------------------------------------------------------------

class ComponentError(SICError):
    """Base class for component-related errors."""
    pass

class ComponentNotStartedError(ComponentError):
    """Raised when an operation requires a running component that hasn't started."""
    pass

class ComponentConfigurationError(ComponentError):
    """Raised when a component has an invalid configuration."""
    pass

class ComponentRequestError(ComponentError):
    """Raised when a component receives an invalid or unknown request."""
    pass


# -----------------------------------------------------------------------------
# Service & Message Errors
# -----------------------------------------------------------------------------

class ServiceError(SICError):
    """Base class for service-related errors."""
    pass

class MessageError(ServiceError):
    """Base class for messaging errors."""
    pass

class MessageAlignmentError(MessageError):
    """Raised when service inputs cannot be synchronized (formerly PopMessageException/AlignmentError)."""
    pass

class UnknownMessageTypeError(MessageError):
    """Raised when a handler receives a message type it doesn't know how to process."""
    pass

class AlignmentError(Exception):
    """Raised when input messages cannot be time-aligned."""
    pass

# -----------------------------------------------------------------------------
# Device Errors
# -----------------------------------------------------------------------------

class DeviceError(SICError):
    """Base class for device-related errors."""
    pass

class DeviceConnectionError(DeviceError):
    """Raised when a device cannot be reached or connected to."""
    pass

class DeviceAuthError(DeviceConnectionError):
    """Raised when authentication with a device fails (e.g. SSH)."""
    pass

class DeviceReservationError(DeviceError):
    """Raised when a device is already reserved or reservation fails."""
    pass

class DeviceInstallationError(DeviceError):
    """Raised when installing software on a device fails."""
    pass

class DeviceExecutionError(DeviceError):
    """Raised when a command fails to execute on the device."""
    pass


# -----------------------------------------------------------------------------
# Other Errors
# -----------------------------------------------------------------------------

class SICRemoteError(SICError):
    """Raised when a remote exception occurs (forwarded from another component)."""
    pass

class SICRedisError(SICError):
    """Raised when there is an issue communicating with Redis."""
    pass


class SICModelFileNotFoundError(SICError, FileNotFoundError):
    """
    Raised when a required model/checkpoint file cannot be found locally.

    Subclasses FileNotFoundError so it can be handled as a standard filesystem error.
    """

    def __init__(self, message: str, *, missing_path: str | None = None):
        super().__init__(message)
        self.missing_path = missing_path
