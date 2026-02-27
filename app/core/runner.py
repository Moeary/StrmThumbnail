from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .scraper import ProcessResult, QPSLimiter, ScrapeOptions, process_single_strm
from .storage import Profile, Storage

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[dict], None]


@dataclass(slots=True)
class RunStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    output_bytes: int = 0
    download_bytes: int = 0
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "output_bytes": self.output_bytes,
            "download_bytes": self.download_bytes,
            "elapsed": self.elapsed,
        }


class Runner:
    def __init__(self, storage: Storage):
        self.storage = storage

    def run_profiles(
        self,
        profiles: list[Profile],
        *,
        mode: str,
        on_log: LogCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> RunStats:
        started = time.time()
        full_mode = mode == "full"
        all_files: list[tuple[Profile, Path]] = []

        def log(message: str) -> None:
            if on_log:
                on_log(message)

        for profile in profiles:
            if not profile.enabled:
                log(f"[skip-profile] {profile.name}: disabled")
                continue
            root = Path(profile.directory)
            if not root.exists():
                log(f"[invalid-path] {profile.name}: {root}")
                continue
            files = list(root.glob("**/*.strm"))
            log(f"[profile] {profile.name} files={len(files)} mode={mode}")
            all_files.extend((profile, f) for f in files)

        stats = RunStats(total=len(all_files))
        if not all_files:
            stats.elapsed = time.time() - started
            if on_progress:
                on_progress(stats.to_dict())
            return stats

        run_id = self.storage.log_run_start(None, mode)
        done = 0
        limiter = QPSLimiter(qps=2)

        with ThreadPoolExecutor(max_workers=max((p.threads for p, _ in all_files), default=4)) as pool:
            futures = []
            for profile, strm in all_files:
                options = ScrapeOptions(
                    full=full_mode,
                    generate_poster=profile.generate_poster,
                    generate_fanart=profile.generate_fanart,
                    generate_nfo=profile.generate_nfo,
                    overwrite=profile.overwrite_existing,
                    poster_pct=profile.poster_pct,
                    fanart_pct=profile.fanart_pct,
                )
                futures.append(pool.submit(process_single_strm, strm, options, limiter))

            for future in as_completed(futures):
                result: ProcessResult = future.result()
                done += 1
                if result.status == "success":
                    stats.success += 1
                elif result.status == "failed":
                    stats.failed += 1
                else:
                    stats.skipped += 1

                stats.output_bytes += result.output_size
                stats.download_bytes += result.downloaded_bytes
                stats.elapsed = time.time() - started

                if result.message:
                    log(f"[{result.status}] {result.path.name}: {result.message}")
                else:
                    log(f"[{result.status}] {result.path.name}")

                if on_progress:
                    payload = stats.to_dict() | {"done": done}
                    on_progress(payload)

        self.storage.log_run_finish(
            run_id,
            success_count=stats.success,
            fail_count=stats.failed,
            skipped_count=stats.skipped,
            output_bytes=stats.output_bytes,
            download_bytes=stats.download_bytes,
        )
        return stats
