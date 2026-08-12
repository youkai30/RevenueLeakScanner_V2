"""
src/exceptions.py — Revenue Leak Scanner V2 Exception Taxonomy
"""

class RevenueLeakScannerError(Exception):
    """Base exception for all Revenue Leak Scanner V2 errors."""
    pass


class DomainValidationError(RevenueLeakScannerError):
    """Raised when store domain or base URL fails validation checks."""
    pass


class InvalidBoundingBoxError(RevenueLeakScannerError):
    """Raised when spatial coordinates fail non-negative dimension checks."""
    pass


class InvalidCommercialMetricsError(RevenueLeakScannerError):
    """Raised when commercial metrics fall outside defined bounds."""
    pass


class SessionExistsException(RevenueLeakScannerError):
    """Raised when an attempt is made to overwrite an existing immutable session ID."""
    pass


class SessionNotFoundException(RevenueLeakScannerError):
    """Raised when a requested session bundle directory or file is missing."""
    pass


class EvidenceTamperedException(RevenueLeakScannerError):
    """Raised when SHA-256 checksum or file validation checks fail at read time."""
    pass


class InvalidBundleException(RevenueLeakScannerError):
    """Raised when a SessionBundle fails JSON schema or structure verification."""
    pass


class ChecksumMismatchException(EvidenceTamperedException):
    """Raised specifically when calculated checksum does not match stored signature."""
    pass
