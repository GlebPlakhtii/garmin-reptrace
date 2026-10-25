"""One reentrant process lock for strength mutations across web and collector."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import threading
import time

_guard = threading.RLock()
_local = threading.local()


class StrengthBusy(TimeoutError):
    """A coherent snapshot could not be taken while a mutation was in progress."""

    def __init__(self):
        super().__init__(
            "Training records are being updated. Please try again shortly."
        )


@contextmanager
def strength_lock(timeout=None):
    """Serialize writers and snapshots, with optional bounded reader waiting."""
    deadline = None if timeout is None else time.monotonic() + timeout
    if not _guard.acquire(timeout=-1 if timeout is None else timeout):
        raise StrengthBusy()
    try:
        if getattr(_local, "depth", 0):
            _local.depth += 1
            try:
                yield
            finally:
                _local.depth -= 1
            return
        path = Path(
            os.getenv(
                "STRENGTH_MUTATION_LOCK_PATH",
                f"/tmp/garmin-reptrace-strength-{os.getuid()}.lock",
            )
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            if deadline is None:
                fcntl.flock(handle, fcntl.LOCK_EX)
            else:
                while True:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise StrengthBusy()
                        time.sleep(min(0.01, remaining))
            _local.depth = 1
            try:
                yield
            finally:
                _local.depth = 0
                fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        _guard.release()


def protected_activity(activity_id, *, local_body=None):
    """Protect pending recovery, allowing its exact confirmed local step only."""
    from reptrace.garmin.operations import OperationJournal

    path = Path(
        os.getenv(
            "GARMIN_OPERATION_STATE_PATH", "/var/lib/form/garmin-operations.sqlite"
        )
    )
    if not path.exists():
        return False
    return any(
        not (
            local_body is not None
            and operation.get("localBody") == local_body
            and (
                operation.get("destination") == "local"
                or operation.get("remoteStatus") == "saved"
            )
        )
        for operation in OperationJournal(path).unresolved(str(activity_id))
    )


@contextmanager
def collector_batch(points, client, version):
    """Recheck stale fetched batches under the same lock held through the write."""
    from reptrace.training.strength import has_manual_strength_details

    ids = {
        str(p.get("tags", {}).get("ActivityID"))
        for p in points
        if p.get("measurement") in ("StrengthSet", "StrengthExercise")
        or (
            p.get("measurement") == "ActivitySummary"
            and str(p.get("fields", {}).get("activityType", "")).startswith(
                "strength_training"
            )
        )
    }
    if not ids:
        yield points
        return
    with strength_lock():
        blocked = {
            key
            for key in ids
            if protected_activity(key)
            or has_manual_strength_details(client, version, key)
        }
        yield [
            p for p in points if str(p.get("tags", {}).get("ActivityID")) not in blocked
        ]


def strength_writer(function):
    from functools import wraps

    @wraps(function)
    def wrapped(*args, **kwargs):
        with strength_lock():
            return function(*args, **kwargs)

    return wrapped
