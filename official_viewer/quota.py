"""Small, local, fail-closed daily request budget ledger."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date
from pathlib import Path
from typing import Callable, Literal

QuotaKind = Literal["place", "panorama"]

_STALE_LOCK_RECOVERY_ATTEMPTS = 3
_STALE_LOCK_RECOVERY_DELAY_SECONDS = 0.1


class QuotaError(RuntimeError):
    """Base class for local quota ledger failures."""


class DailyQuotaExceeded(QuotaError):
    """Raised before this viewer would exceed its configured daily request budget."""

    def __init__(self, kind: QuotaKind, limit: int) -> None:
        self.kind = kind
        self.limit = limit
        label = "地点检索" if kind == "place" else "全景展示"
        super().__init__(f"本地{label}日预算已达到 {limit} 次，未发送新的官方请求。")


class UsageLedgerError(QuotaError):
    """Raised when the local counter cannot be safely read or persisted."""


class RuntimeLockError(QuotaError):
    """Raised when another viewer process already owns the local usage directory."""


class RuntimeLock:
    """A small cross-process lock for one local viewer usage directory.

    The lock prevents two viewer processes from racing the counter-only budget
    ledger. A lock left by a crashed process is reclaimed only after its recorded
    PID is no longer alive. Malformed or still-owned locks fail closed.
    """

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._descriptor: int | None = None

    def acquire(self) -> None:
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeLockError("无法安全创建本地用量锁，未启动新进程。") from exc

        try:
            descriptor = self._create_lock_file()
        except FileExistsError as exc:
            if not self._remove_stale_lock_with_retry():
                raise RuntimeLockError(
                    "同一用量目录已有本地查看器在运行；为避免并发绕过日预算，未启动新进程。"
                ) from exc
            try:
                descriptor = self._create_lock_file()
            except FileExistsError as retry_exc:
                raise RuntimeLockError(
                    "同一用量目录已有本地查看器在运行；为避免并发绕过日预算，未启动新进程。"
                ) from retry_exc
        except OSError as exc:
            raise RuntimeLockError("无法安全创建本地用量锁，未启动新进程。") from exc

        try:
            os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
            os.fsync(descriptor)
        except OSError as exc:
            os.close(descriptor)
            try:
                self._lock_path.unlink()
            except OSError:
                pass
            raise RuntimeLockError("无法安全写入本地用量锁，未启动新进程。") from exc
        self._descriptor = descriptor

    def _create_lock_file(self) -> int:
        return os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)

    def _remove_stale_lock_with_retry(self) -> bool:
        # Windows may briefly retain a forcibly terminated process in its table.
        # Keep failing closed unless a later probe confirms the recorded PID exited.
        for attempt in range(_STALE_LOCK_RECOVERY_ATTEMPTS):
            if self._remove_stale_lock():
                return True
            if attempt + 1 < _STALE_LOCK_RECOVERY_ATTEMPTS:
                time.sleep(_STALE_LOCK_RECOVERY_DELAY_SECONDS)
        return False

    def _remove_stale_lock(self) -> bool:
        try:
            recorded_pid = int(self._lock_path.read_text(encoding="ascii").strip())
        except FileNotFoundError:
            return True
        except (OSError, UnicodeDecodeError, ValueError):
            return False
        if recorded_pid <= 0 or _process_is_running(recorded_pid):
            return False
        try:
            self._lock_path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def release(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            return
        try:
            os.close(descriptor)
        finally:
            try:
                self._lock_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _process_is_running(process_id: int) -> bool:
    """Check a PID without sending a signal to a Windows process."""

    if os.name != "nt":
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return True
        return True

    import ctypes

    process_query_limited_information = 0x1000
    access_denied = 5
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.GetExitCodeProcess.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    handle = kernel32.OpenProcess(process_query_limited_information, False, process_id)
    if handle:
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    return ctypes.get_last_error() == access_denied


class DailyUsageLedger:
    """Persist only date and counters, never POIs, panorama IDs, or API responses."""

    def __init__(
        self,
        state_path: Path,
        *,
        place_limit: int,
        panorama_limit: int,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._state_path = state_path
        self._limits = {"place": place_limit, "panorama": panorama_limit}
        self._today = today
        self._lock = threading.Lock()

    def snapshot(self) -> dict[str, int | str]:
        """Return the current local budget status without writing POI data."""

        with self._lock:
            state = self._load_current_state()
            return self._public_snapshot(state)

    def reserve(self, kind: QuotaKind) -> dict[str, int | str]:
        """Atomically reserve one viewer request before an official API call."""

        with self._lock:
            state = self._load_current_state()
            key = f"{kind}_requests"
            limit = self._limits[kind]
            if state[key] >= limit:
                raise DailyQuotaExceeded(kind, limit)
            state[key] += 1
            self._write_state(state)
            return self._public_snapshot(state)

    def _load_current_state(self) -> dict[str, int | str]:
        current_day = self._today().isoformat()
        if not self._state_path.exists():
            return self._empty_state(current_day)
        try:
            raw = self._state_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UsageLedgerError(
                "本地用量账本无法安全读取；为避免错误绕过日预算，未发送请求。"
            ) from exc

        try:
            stored_day = data["day"]
            place_requests = data["place_requests"]
            panorama_requests = data["panorama_requests"]
        except (KeyError, TypeError) as exc:
            raise UsageLedgerError(
                "本地用量账本格式无效；为避免错误绕过日预算，未发送请求。"
            ) from exc
        if (
            not isinstance(stored_day, str)
            or isinstance(place_requests, bool)
            or isinstance(panorama_requests, bool)
            or not isinstance(place_requests, int)
            or not isinstance(panorama_requests, int)
            or place_requests < 0
            or panorama_requests < 0
        ):
            raise UsageLedgerError(
                "本地用量账本内容无效；为避免错误绕过日预算，未发送请求。"
            )
        if stored_day != current_day:
            return self._empty_state(current_day)
        return {
            "day": stored_day,
            "place_requests": place_requests,
            "panorama_requests": panorama_requests,
        }

    @staticmethod
    def _empty_state(day: str) -> dict[str, int | str]:
        return {"day": day, "place_requests": 0, "panorama_requests": 0}

    def _public_snapshot(self, state: dict[str, int | str]) -> dict[str, int | str]:
        place_requests = int(state["place_requests"])
        panorama_requests = int(state["panorama_requests"])
        return {
            "day": state["day"],
            "place_requests": place_requests,
            "place_limit": self._limits["place"],
            "place_remaining": max(0, self._limits["place"] - place_requests),
            "panorama_requests": panorama_requests,
            "panorama_limit": self._limits["panorama"],
            "panorama_remaining": max(0, self._limits["panorama"] - panorama_requests),
        }

    def _write_state(self, state: dict[str, int | str]) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self._state_path.with_suffix(
                f"{self._state_path.suffix}.tmp"
            )
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._state_path)
        except OSError as exc:
            raise UsageLedgerError(
                "本地用量账本无法安全写入；为避免错误绕过日预算，未发送请求。"
            ) from exc
