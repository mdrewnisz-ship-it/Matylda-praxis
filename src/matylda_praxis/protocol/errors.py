"""Failures that stop a protocol run without mutating its record."""


class ProtocolViolation(ValueError):
    """An operation would violate an epistemic invariant."""


class ConcurrencyConflict(RuntimeError):
    """A repository revision changed before a write could commit."""


class ApprovalDenied(ProtocolViolation):
    """No explicit human authority was supplied for a decision."""
