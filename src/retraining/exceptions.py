"""Domain exceptions for the retraining pipeline."""

from __future__ import annotations


class RetrainingError(Exception):
    """Base retraining failure."""


class DataValidationFailed(RetrainingError):
    """Input data failed schema / business checks."""


class TriggerSkip(RetrainingError):
    """No retraining trigger fired — workflow should skip (not fail)."""


class TriggerUnavailable(RetrainingError):
    """Trigger mode lacks required inputs/results — must not silent-succeed."""


class ChampionUnavailable(RetrainingError):
    """Champion artifacts missing; comparison limited."""


class RegistryError(RetrainingError):
    """Atomic registry update failed."""


class GateRejected(RetrainingError):
    """Candidate failed quality gates."""
