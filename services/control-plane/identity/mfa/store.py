"""Factor records and the repository contract. A real store implements every
method below as one atomic conditional write (the in-memory fake locks)."""

import threading
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional, Protocol


class FactorStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"


@dataclass(frozen=True)
class TotpFactor:
    factor_id: str
    realm: str
    subject_id: str
    sealed_secret: bytes = field(repr=False)  # sealed by the injected SecretBox, never plain
    created_at: int
    status: FactorStatus = FactorStatus.PENDING
    last_counter: int = -1
    bootstrap: bool = False  # pending factor started by an admin ticket (staff first factor)


@dataclass(frozen=True)
class RecoveryRecord:
    code_id: str
    realm: str
    subject_id: str
    salt: bytes = field(repr=False)
    digest: bytes = field(repr=False)
    used: bool = False


@dataclass(frozen=True)
class Attempts:
    allowed: bool
    locked_until: int = 0


class FactorRepository(Protocol):
    def put_factor(self, factor: TotpFactor) -> None: ...
    def get_factor(self, factor_id: str) -> Optional[TotpFactor]: ...
    def factors_for(self, realm: str, subject_id: str) -> tuple: ...
    def delete_factor(self, factor_id: str) -> bool: ...

    def advance_counter(self, factor_id: str, expected_last: int, new_counter: int) -> bool:
        """Compare-and-set: set last_counter to new_counter only if it is still
        expected_last and new_counter is greater. False means another request won
        (replay or race): the caller must treat the code as invalid."""

    def activate_factor(self, factor_id: str, counter: int) -> bool:
        """Atomically PENDING -> ACTIVE with last_counter=counter; False if not pending."""

    def replace_recovery(self, realm: str, subject_id: str, records: tuple) -> None:
        """Replace the whole set atomically (old codes die with the new batch)."""

    def recovery_for(self, realm: str, subject_id: str) -> tuple: ...

    def consume_recovery(self, code_id: str) -> bool:
        """Atomically used False -> True; False if already used or unknown."""

    def begin_attempt(self, key: str, now: int, window: int, max_attempts: int,
                      lockout: int) -> Attempts:
        """Atomically count one attempt before it is evaluated. Over max_attempts
        inside the window locks the key for `lockout` seconds; a locked key stays
        refused until then and attempts made while locked do not extend it."""

    def clear_attempts(self, key: str) -> None: ...


class InMemoryFactorRepository:
    def __init__(self):
        self._lock = threading.RLock()
        self._factors: dict = {}
        self._recovery: dict = {}  # (realm, subject) -> tuple of RecoveryRecord
        self._attempts: dict = {}  # key -> (count, window_start, locked_until)

    def put_factor(self, factor):
        with self._lock:
            self._factors[factor.factor_id] = factor

    def get_factor(self, factor_id):
        with self._lock:
            return self._factors.get(factor_id)

    def factors_for(self, realm, subject_id):
        with self._lock:
            return tuple(f for f in self._factors.values()
                         if f.realm == realm and f.subject_id == subject_id)

    def delete_factor(self, factor_id):
        with self._lock:
            return self._factors.pop(factor_id, None) is not None

    def advance_counter(self, factor_id, expected_last, new_counter):
        with self._lock:
            f = self._factors.get(factor_id)
            if f is None or f.last_counter != expected_last or new_counter <= f.last_counter:
                return False
            self._factors[factor_id] = replace(f, last_counter=new_counter)
            return True

    def activate_factor(self, factor_id, counter):
        with self._lock:
            f = self._factors.get(factor_id)
            if f is None or f.status is not FactorStatus.PENDING:
                return False
            self._factors[factor_id] = replace(f, status=FactorStatus.ACTIVE, last_counter=counter)
            return True

    def replace_recovery(self, realm, subject_id, records):
        with self._lock:
            self._recovery[(realm, subject_id)] = tuple(records)

    def recovery_for(self, realm, subject_id):
        with self._lock:
            return self._recovery.get((realm, subject_id), ())

    def consume_recovery(self, code_id):
        with self._lock:
            for key, records in self._recovery.items():
                for i, r in enumerate(records):
                    if r.code_id == code_id:
                        if r.used:
                            return False
                        self._recovery[key] = records[:i] + (replace(r, used=True),) + records[i + 1:]
                        return True
            return False

    def begin_attempt(self, key, now, window, max_attempts, lockout):
        with self._lock:
            count, start, locked = self._attempts.get(key, (0, now, 0))
            if locked > now:
                return Attempts(False, locked)
            if locked or now - start >= window:  # lockout over, or window rolled
                count, start, locked = 0, now, 0
            count += 1
            if count > max_attempts:
                locked = now + lockout
                self._attempts[key] = (count, start, locked)
                return Attempts(False, locked)
            self._attempts[key] = (count, start, 0)
            return Attempts(True, 0)

    def clear_attempts(self, key):
        with self._lock:
            self._attempts.pop(key, None)
