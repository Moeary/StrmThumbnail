from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .scraper import (
    ProcessResult,
    QPSLimiter,
    ScrapeOptions,
    get_artifact_state,
    infer_media_extension,
    plan_for_incremental,
    process_single_strm,
)
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

    @staticmethod
    def _collect_profile_files(root: Path, profile: Profile, allowed_extensions: set[str]) -> list[Path]:
        files: list[Path] = []

        for strm in root.glob("**/*.strm"):
            media_ext = infer_media_extension(strm)
            if media_ext and media_ext in allowed_extensions:
                files.append(strm)

        if profile.include_local_media:
            for ext in allowed_extensions:
                files.extend(root.glob(f"**/*{ext}"))
                files.extend(root.glob(f"**/*{ext.upper()}"))
        # Keep deterministic order for stable logs and progress behavior.
        return sorted(set(files))

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
        files_by_profile: list[tuple[Profile, list[Path]]] = []
        planned_by_profile: list[tuple[Profile, list[tuple[Path, ScrapeOptions]]]] = []
        allowed_extensions = set(self.storage.get_allowed_media_extensions())

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
            files = self._collect_profile_files(root, profile, allowed_extensions)
            log(f"[profile] {profile.name} files={len(files)} mode={mode}")
            files_by_profile.append((profile, files))

        stats = RunStats(total=sum(len(files) for _, files in files_by_profile))
        if not files_by_profile:
            stats.elapsed = time.time() - started
            if on_progress:
                on_progress(stats.to_dict())
            return stats

        precheck_skip_count = 0
        precheck_queued_count = 0
        partial_missing_count = 0
        for profile, files in files_by_profile:
            profile_jobs: list[tuple[Path, ScrapeOptions]] = []
            for strm in files:
                base_options = ScrapeOptions(
                    full=full_mode,
                    generate_poster=profile.generate_poster,
                    generate_fanart=profile.generate_fanart,
                    generate_nfo=profile.generate_nfo,
                    overwrite=profile.overwrite_existing,
                    poster_pct=profile.poster_pct,
                    fanart_pct=profile.fanart_pct,
                )

                if full_mode or profile.overwrite_existing:
                    profile_jobs.append((strm, base_options))
                    precheck_queued_count += 1
                    continue

                plan = plan_for_incremental(strm, base_options)
                if plan.should_run:
                    missing_parts = int(plan.options.generate_poster) + int(plan.options.generate_fanart) + int(plan.options.generate_nfo)
                    if missing_parts < (
                        int(base_options.generate_poster)
                        + int(base_options.generate_fanart)
                        + int(base_options.generate_nfo)
                    ):
                        partial_missing_count += 1
                    profile_jobs.append((strm, plan.options))
                    precheck_queued_count += 1
                    self.storage.upsert_file_state(
                        profile_id=profile.id,
                        strm_path=str(strm),
                        poster_exists=plan.artifact_state.poster_exists,
                        fanart_exists=plan.artifact_state.fanart_exists,
                        nfo_exists=plan.artifact_state.nfo_exists,
                        last_status="queued",
                    )
                else:
                    precheck_skip_count += 1
                    stats.skipped += 1
                    self.storage.upsert_file_state(
                        profile_id=profile.id,
                        strm_path=str(strm),
                        poster_exists=plan.artifact_state.poster_exists,
                        fanart_exists=plan.artifact_state.fanart_exists,
                        nfo_exists=plan.artifact_state.nfo_exists,
                        last_status="skipped",
                    )
            planned_by_profile.append((profile, profile_jobs))

        if not full_mode:
            log(
                f"[precheck] total={stats.total} queued={precheck_queued_count} "
                f"skipped={precheck_skip_count} partial={partial_missing_count}"
            )

        run_id = self.storage.log_run_start(None, mode)
        done = stats.skipped
        configured_qps = float(os.getenv("STRM_QPS", "0.5"))
        limiter = QPSLimiter(qps=max(0.1, configured_qps))
        log(f"[throttle] qps={max(0.1, configured_qps):.2f}")

        if on_progress:
            on_progress(stats.to_dict() | {"done": done})

        if precheck_queued_count == 0:
            stats.elapsed = time.time() - started
            self.storage.log_run_finish(
                run_id,
                success_count=stats.success,
                fail_count=stats.failed,
                skipped_count=stats.skipped,
                output_bytes=stats.output_bytes,
                download_bytes=stats.download_bytes,
            )
            return stats

        for profile, jobs in planned_by_profile:
            if not jobs:
                continue

            log(f"[run-profile] {profile.name} queued={len(jobs)}")
            with ThreadPoolExecutor(max_workers=max(1, profile.threads)) as pool:
                futures = []
                future_to_ctx = {}
                for strm, options in jobs:
                    futures.append(pool.submit(process_single_strm, strm, options, limiter))
                    future_to_ctx[futures[-1]] = strm

                for future in as_completed(futures):
                    result: ProcessResult = future.result()
                    strm = future_to_ctx[future]
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

                    artifact_state = get_artifact_state(strm)
                    self.storage.upsert_file_state(
                        profile_id=profile.id,
                        strm_path=str(strm),
                        poster_exists=artifact_state.poster_exists,
                        fanart_exists=artifact_state.fanart_exists,
                        nfo_exists=artifact_state.nfo_exists,
                        last_status=result.status,
                        last_error=result.message,
                    )

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
