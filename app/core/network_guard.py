from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from enum import Enum


class FailureKind(str, Enum):
    TIMEOUT = "timeout"
    NETWORK = "network"
    PROCESS = "process"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class GuardResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    failure_kind: FailureKind | None = None
    attempts: int = 1


def classify_failure(stderr: str, timed_out: bool) -> FailureKind:
    if timed_out:
        return FailureKind.TIMEOUT

    text = (stderr or "").lower()
    network_markers = [
        "connection",
        "timed out",
        "network",
        "unreachable",
        "host",
        "http",
        "tls",
    ]
    if any(m in text for m in network_markers):
        return FailureKind.NETWORK
    if text.strip():
        return FailureKind.PROCESS
    return FailureKind.UNKNOWN


def run_with_retry(
    cmd: list[str],
    *,
    timeout: int,
    retries: int = 2,
    retry_backoff: float = 0.7,
) -> GuardResult:
    attempts = max(1, retries + 1)
    last_result: GuardResult | None = None

    for index in range(attempts):
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if proc.returncode == 0:
                return GuardResult(ok=True, stdout=proc.stdout, stderr=proc.stderr, returncode=0, attempts=index + 1)

            failure_kind = classify_failure(proc.stderr, False)
            last_result = GuardResult(
                ok=False,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                failure_kind=failure_kind,
                attempts=index + 1,
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            last_result = GuardResult(
                ok=False,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                returncode=124,
                failure_kind=classify_failure(exc.stderr or "", timed_out),
                attempts=index + 1,
            )

        if index < attempts - 1:
            time.sleep(retry_backoff * (index + 1))

    if last_result is None:
        return GuardResult(ok=False, failure_kind=FailureKind.UNKNOWN)
    return last_result
