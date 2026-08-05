"""Typed error hierarchy for PARKER."""


class PARKERError(Exception):
    """Base error for PARKER."""

    code: str = "parker_error"
    message: str = "An unexpected PARKER error occurred."
    recoverable: bool = True

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        recoverable: bool | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if recoverable is not None:
            self.recoverable = recoverable
        super().__init__(self.message)


class DeviceNotFoundError(PARKERError):
    code = "device_not_found"
    message = "The requested device could not be found."


class AmbiguousDeviceError(PARKERError):
    code = "ambiguous_device"
    message = "Multiple devices match the request. Please specify."


class ConfirmationRequiredError(PARKERError):
    code = "confirmation_required"
    message = "This action requires explicit confirmation."
    recoverable = True


class ActionExecutionError(PARKERError):
    code = "action_failed"
    message = "The action failed to execute."


class TranscriptionError(PARKERError):
    code = "transcription_failed"
    message = "Speech transcription failed."


class ContextExpiredError(PARKERError):
    code = "context_expired"
    message = "The conversation context has expired."
