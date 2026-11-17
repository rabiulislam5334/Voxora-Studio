# Phase 2.0 — Final Reliability Regression Audit

**Baseline:** `main` at `558ed9408d611e3241fb12737102594e9d321b37` (PR #27 merged)  
**Audit branch:** `audit/phase-2-0-final-reliability`  
**Audit type:** Read-only source and regression-test review  
**Runtime changes:** None

## Executive summary

The current production path has strong protections around FFmpeg child-process cleanup, final MP4 validation, atomic project saves, and cooperating-process save serialization. The user's latest reported full-suite baseline after PR #27 is **606 passed in 63.31s**.

The audit found several remaining reliability gaps worth addressing before treating Phase 2.0 reliability work as complete:

1. **Cancellation is not observed during final FFprobe validation.** The timestamp inspection can decode a long output for up to one hour. If the user cancels during that inspection, the validation call continues, and the production path has no cancellation check immediately before publishing the final `.part` file. A completed output can therefore still be published after a cancellation request.
2. **A non-empty but corrupt cached scene MP4 is treated as a valid cache hit.** Cache lookup checks only file existence and non-zero size. Cache commit also checks only those properties; it does not inspect the segment.
3. **Stale-part cleanup is directory-wide.** Each production run removes every `*.part` file in the shared segment cache directory. If two production jobs/processes share that cache concurrently, one job can delete another job's active segment output.
4. **Final A/V start validation checks relative alignment, not absolute timeline origin.** It compares audio start time with video start time, but does not independently require the first video timestamp / stream start to be at the intended zero origin.
5. **Media cache identity is metadata-based.** A source file replaced with different bytes while preserving its resolved path, size, and nanosecond mtime can retain the same cache identity. This is a documented performance trade-off, not necessarily a defect for ordinary editing workflows.

The first three are the most actionable findings. The persistence save path itself appears internally consistent within its documented advisory-lock boundary.

## Findings

### F-01 — Cancellation is not propagated through final FFprobe validation

**Priority:** High  
**Area:** FFmpeg inspection / production cancellation  
**Evidence:**
- `app/audio/ffmpeg_tool.py`: `probe_structured()` and `probe_frame_timestamps()` use blocking `subprocess.run()` calls and accept no `CancelToken`.
- `probe_frame_timestamps()` has a timeout of up to 3600 seconds because it decodes and inspects all video frames.
- `app/workers/production.py`: final MP4 validation invokes the structured probe and frame-timestamp probe, then calls `os.replace(part_video, video_path)`. There is no cancellation check between the probes and final publication.
- Existing tests cover cancellation of `run_with_progress()` and cleanup of its reader thread, but do not cover cancellation while final FFprobe validation is running.

**Impact:** A user can request cancellation while the final output is being inspected, but the inspection does not stop. If validation eventually succeeds, the output may still be published even though cancellation was requested.

**Recommendation:** Make the final inspection path cancellation-aware (or run it through a cancellable subprocess helper), and call `cancel.raise_if_cancelled()` immediately before publishing the final output. Add a deterministic test that cancels during timestamp inspection and asserts that the final target is not published and the `.part` file is removed.

### F-02 — Corrupt non-empty cached segments are accepted as cache hits

**Priority:** Medium  
**Area:** Video cache integrity  
**Evidence:**
- `app/cache/video_cache.py`: `VideoCache.has_segment()` returns true when the cache path is a file with size greater than zero.
- `VideoCache.commit_segment()` publishes any non-empty `.part` file using `os.replace()`; it does not probe or validate the MP4.
- `app/workers/production.py`: a true `has_segment(key)` result skips rendering and appends the cached path directly to the join list.
- The reviewed production tests cover ordinary cache reuse and source-media changes, but do not inject a deliberately truncated, non-empty cached MP4 and verify recovery.

**Impact:** A truncated or otherwise corrupt cache entry can be repeatedly reused. The subsequent join or mux may fail, requiring the user to manually clear the cache or retry after the invalid entry is removed.

**Recommendation:** Validate a cache entry before reuse using a suitably lightweight media check (at minimum a readable video stream and expected segment frame count/duration). On validation failure, invalidate that entry and render the segment again. Add tests for a non-empty invalid cache file and a structurally readable file with the wrong frame count. Avoid a full expensive decode on every normal cache hit unless benchmarks justify it.

### F-03 — Shared cache stale-part cleanup can race with another active render

**Priority:** Medium, conditional on concurrent jobs sharing a cache root  
**Area:** Cache concurrency  
**Evidence:**
- `app/cache/video_cache.py`: `remove_stale_parts()` unlinks every `*.part` file under `segments_dir`.
- `app/workers/production.py`: every production run calls `remove_stale_parts()` before rendering its scene segments.
- `part_path()` creates unique names, but cleanup does not distinguish stale files from parts owned by another live process/job.

**Impact:** If multiple production jobs or Voxora processes share the same cache directory, a newly starting job can remove a segment file that another job is actively writing. The cross-process project-save lock does not protect the video cache.

**Recommendation:** Do not perform unqualified directory-wide cleanup while jobs may be active. Use per-job ownership/age metadata, an explicit cache lock, or cleanup only parts known to be abandoned. Add a multiprocessing test with one job holding an active part while another starts cleanup. If concurrent production is explicitly unsupported, enforce and document a single-writer boundary rather than relying on assumption.

### F-04 — Final stream-start validation does not assert the absolute timeline origin

**Priority:** Medium / hardening  
**Area:** Final MP4 timestamp validation  
**Evidence:**
- `app/workers/production.py`: `stream_start_aligned` compares the absolute difference between audio and video stream start times.
- `app/audio/probe.py`: structured inspection already exposes format and stream start times, and frame timestamp inspection exposes the first decoded video timestamp.
- The final validator does not require the video stream / first decoded frame to start at the expected timeline origin (normally zero).

**Impact:** The validator proves that audio and video start near each other, but not independently that both begin at the intended absolute origin. A file with both streams shifted by the same amount is not rejected solely by the relative-offset condition.

**Recommendation:** First characterize the actual FFmpeg mux output across supported codecs and containers. If the intended contract is a zero-based MP4 timeline, add an explicit origin tolerance check and a synthetic fixture where both streams share the same non-zero start offset.

### F-05 — Source-media cache identity is not a content hash

**Priority:** Low / known limitation  
**Area:** Cache invalidation  
**Evidence:**
- `app/cache/video_cache.py`: `media_identity()` uses resolved path, file size, and `st_mtime_ns`; those values feed the segment cache key.

**Impact:** Replacing a source file with different bytes while preserving the same path, size, and mtime can cause the old rendered segment to be reused.

**Recommendation:** Keep the current inexpensive identity if its performance trade-off is intentional, but document it. Consider a content hash or a hybrid fingerprint only if users encounter stale-cache reports; benchmark the cost before changing the key because it can require reading large media files.

## Areas that passed source-level review

### FFmpeg process lifecycle

- `run_with_progress()` starts FFmpeg without a shell, drains its progress pipe on a dedicated reader thread, checks cancellation and timeout, kills a still-running child on exceptional exit, waits for the child, and joins the reader thread.
- The production test suite includes a regression test asserting that the progress reader is joined after cancellation.
- The simpler `_run()` helper uses `communicate(timeout=...)`, kills on cancellation/timeout, and collects the child output.
- Production output paths use `.part` files and clean them up on exceptions. The final MP4 is replaced into its target only after validation.

**Conclusion:** No new process-lifecycle defect was confirmed in the reviewed paths. The uncovered cancellation gap is specifically in the separate blocking FFprobe validation calls, not the FFmpeg progress runner.

### Final MP4 validation

The current production validator checks:
- video output classification and audio stream presence;
- container duration against frame-derived expected duration;
- decoded video frame count against expected total frames;
- missing and non-monotonic decoded-frame timestamps;
- constant-frame-rate interval continuity against configured FPS;
- individual video and audio stream durations with codec-aware tolerances;
- relative audio/video stream start alignment.

This is a substantial validation foundation. The remaining concerns are cancellation during the inspection itself and the absolute timeline-origin assertion described above.

### Project persistence and cross-process save safety

Reviewed paths:
- `app/persistence/repository.py`
- `app/persistence/file_lock.py`
- `app/persistence/atomic.py`
- `tests/test_project_file_lock.py`

Verified design properties:
- Project serialization happens before filesystem mutation.
- A per-project advisory lock covers the staged write, disk-stamp checks, backup work, and final replacement.
- The lock has a bounded acquisition timeout and is released by the operating system if the process exits.
- The staged file is created beside the target, flushed and fsynced, and then atomically replaced.
- Failed staged writes are discarded on ordinary exception paths.
- Existing disk-stamp checks remain in place to detect non-cooperating writers.
- Multiprocessing tests cover mutual exclusion, lock reuse, and reacquisition after release.

**Boundary:** The lock coordinates cooperating Voxora processes running under the same OS user on the same machine. It does not protect against unrelated programs, other OS users, or remote machines. The repository documentation correctly retains this limitation. This audit does not claim that the save operation is universally race-free.

### Snapshot / recovery scope

This audit does not enable autosave, snapshots, automatic project recovery, or any new persistence workflow. Existing opt-in/disabled-by-default behavior remains unchanged.

## Recommended follow-up order

1. Fix F-01: cancellation-aware final inspection and a cancellation check before publishing the MP4.
2. Fix F-02: detect and regenerate corrupt cached scene segments.
3. Resolve F-03: define/enforce cache cleanup ownership if concurrent jobs can share a cache root.
4. Add the F-04 zero-origin characterization test, then decide whether a runtime check is required.
5. Keep F-05 documented unless real-world evidence justifies a more expensive source fingerprint.

Keep each runtime fix in a separate, focused PR. Do not combine this audit with parallel rendering, scheduler work, retries, UI changes, or schema changes.

## Verification status

- User-reported full-suite baseline after PR #27: **606 passed in 63.31s**.
- This document is a source-level audit. No tests were executed as part of authoring this report.
- Before merging any runtime follow-up, run focused regression tests and `python -m pytest -q tests` on the user's Windows environment.
