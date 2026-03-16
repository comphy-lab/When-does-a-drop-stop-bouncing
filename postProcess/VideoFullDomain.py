"""Render whole-domain facet snapshots into deterministic movie frames."""

from __future__ import annotations

import argparse
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import shutil
import subprocess as sp

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTPROCESS_DIR = PROJECT_ROOT / "postProcess"
CACHE_ROOT = POSTPROCESS_DIR / ".video-cache"
TARGET_VIDEO_SECONDS = 10.0
MIN_VIDEO_FPS = 30

matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["text.usetex"] = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-dir",
        default=str(PROJECT_ROOT / "simulationCases" / "0"),
        help="Case directory containing intermediate/snapshot-* files.",
    )
    parser.add_argument(
        "--output-dir",
        default="VideoFullDomain",
        help="Frame output directory relative to the case directory unless absolute.",
    )
    parser.add_argument("--ldomain", type=float, default=8.0, help="Domain size used for plotting.")
    parser.add_argument("--tsnap", type=float, default=0.01, help="Snapshot cadence for plot titles.")
    parser.add_argument("--fps", type=int, default=None, help="Override automatic video frame rate (minimum 30).")
    parser.add_argument("--max-frames", type=int, default=None, help="Limit rendered frames for testing.")
    parser.add_argument("--skip-video", action="store_true", help="Only render frames; do not call ffmpeg.")
    parser.add_argument("--cpus", "--CPUs", dest="cpus", type=int, default=4, help="Worker processes to use.")
    return parser.parse_args()


def list_snapshots(case_dir: Path, max_frames: int | None) -> list[Path]:
    snapshot_dir = case_dir / "intermediate"
    snapshots = sorted(snapshot_dir.glob("snapshot-*"))
    if max_frames is not None:
        snapshots = snapshots[:max_frames]
    return snapshots


def precompile_get_helpers(snapshots: list[Path]) -> Path | None:
    if not snapshots:
        return None

    source = POSTPROCESS_DIR / "getFacet.c"
    binary = POSTPROCESS_DIR / "getFacet"
    if binary.exists() and binary.stat().st_mtime >= source.stat().st_mtime:
        return binary

    # Basilisk's qcc can fail to emit its generated `*-cpp.c` file when the
    # source is passed as an absolute path on this toolchain, even though the
    # same helper compiles correctly from the source directory.
    cmd = ["qcc", "-O2", "-Wall", "-disable-dimensions", source.name, "-o", binary.name, "-lm"]
    sp.run(cmd, check=True, cwd=POSTPROCESS_DIR)
    return binary


def configure_worker_environment(cache_root: Path) -> None:
    worker_root = cache_root / f"worker-{os.getpid()}"
    mpl_dir = worker_root / "mpl"
    texmfvar = worker_root / "texmf-var"
    texmfconfig = worker_root / "texmf-config"
    mpl_dir.mkdir(parents=True, exist_ok=True)
    texmfvar.mkdir(parents=True, exist_ok=True)
    texmfconfig.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(mpl_dir)
    os.environ["TEXMFVAR"] = str(texmfvar)
    os.environ["TEXMFCONFIG"] = str(texmfconfig)
    os.environ["OMP_NUM_THREADS"] = "1"


def project_relative(path: Path) -> str:
    return os.path.relpath(path, PROJECT_ROOT)


def getting_facets(helper_bin: Path, snapshot: Path) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    proc = sp.run(
        [str(helper_bin), project_relative(snapshot)],
        check=True,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    lines = proc.stderr.splitlines()
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    skip = False
    for index, line in enumerate(lines):
        parts = line.split()
        if not parts:
            skip = False
            continue
        if skip or index + 1 >= len(lines):
            continue
        next_parts = lines[index + 1].split()
        if len(parts) < 2 or len(next_parts) < 2:
            continue
        r1, z1 = float(parts[1]), float(parts[0])
        r2, z2 = float(next_parts[1]), float(next_parts[0])
        segs.extend(
            [
                ((r1, z1), (r2, z2)),
                ((r1, -z1), (r2, -z2)),
                ((-r1, z1), (-r2, z2)),
                ((-r1, -z1), (-r2, -z2)),
            ]
        )
        skip = True
    return segs


def movie_output_path(case_dir: Path) -> Path:
    return case_dir / f"{case_dir.name}.mp4"


def choose_video_fps(frame_count: int, fps_override: int | None) -> int:
    if frame_count <= 0:
        raise ValueError("frame_count must be > 0")
    if fps_override is not None:
        if fps_override < MIN_VIDEO_FPS:
            raise ValueError(f"--fps must be >= {MIN_VIDEO_FPS}")
        return fps_override
    return max(MIN_VIDEO_FPS, math.ceil(frame_count / TARGET_VIDEO_SECONDS))


def render_single_snapshot(
    frame_index: int,
    snapshot: Path,
    helper_bin: Path,
    output_dir: Path,
    ldomain: float,
    tsnap: float,
    cache_root: Path,
) -> Path:
    configure_worker_environment(cache_root)
    segs = getting_facets(helper_bin, snapshot)
    if not segs:
        raise RuntimeError(f"No facets extracted from {snapshot}")

    rmin, rmax, zmin, zmax = -ldomain / 2.0, ldomain / 2.0, 0.0, ldomain
    output_path = output_dir / f"frame_{frame_index:06d}.png"

    fig, ax = plt.subplots()
    fig.set_size_inches(19.20, 10.80)
    ax.plot([0, 0], [zmin, zmax], "-.", color="grey", linewidth=2)
    ax.plot([rmin, rmin], [zmin, zmax], "-", color="black", linewidth=2)
    ax.plot([rmin, rmax], [zmin, zmin], "-", color="black", linewidth=2)
    ax.plot([rmin, rmax], [zmax, zmax], "-", color="black", linewidth=2)
    ax.plot([rmax, rmax], [zmin, zmax], "-", color="black", linewidth=2)
    ax.add_collection(LineCollection(segs, linewidths=4, colors="green", linestyle="solid"))
    ax.set_aspect("equal")
    ax.set_xlim(rmin, rmax)
    ax.set_ylim(zmin, zmax)
    ax.set_title(rf"$V_0t/R_0$ = {frame_index * tsnap:4.3f}", fontsize=20)
    ax.axis("off")
    plt.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_snapshots(
    snapshots: list[Path],
    cpus: int,
    helper_bin: Path | None,
    output_dir: Path,
    ldomain: float,
    tsnap: float,
) -> list[Path]:
    if not snapshots:
        return []
    if cpus <= 0:
        raise ValueError("--cpus must be > 0")
    if helper_bin is None:
        raise RuntimeError("Helper binary is required when snapshots are present")

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    tasks = list(enumerate(snapshots))
    total_frames = len(tasks)
    progress_interval = max(cpus, total_frames // 20 or 1)
    last_reported = 0
    rendered: list[Path] = []
    for start in range(0, len(tasks), cpus):
        batch = tasks[start : start + cpus]
        with ProcessPoolExecutor(max_workers=cpus) as pool:
            futures = [
                pool.submit(
                    render_single_snapshot,
                    frame_index,
                    snapshot,
                    helper_bin,
                    output_dir,
                    ldomain,
                    tsnap,
                    CACHE_ROOT,
                )
                for frame_index, snapshot in batch
            ]
            rendered.extend(future.result() for future in futures)
        rendered_count = len(rendered)
        if rendered_count == total_frames or rendered_count - last_reported >= progress_interval:
            print(f"Rendered {rendered_count}/{total_frames} frame(s)...", flush=True)
            last_reported = rendered_count
    return sorted(rendered)


def count_rendered_frames(output_dir: Path) -> int:
    return sum(1 for _ in output_dir.glob("frame_*.png"))


def assemble_video(output_dir: Path, output_path: Path, fps: int) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required unless --skip-video is used")
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-pattern_type",
        "glob",
        "-i",
        str(output_dir / "*.png"),
        "-vf",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v",
        "libx264",
        "-r",
        str(fps),
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    sp.run(cmd, check=True)


def main() -> None:
    args = parse_args()
    if args.cpus <= 0:
        raise SystemExit("--cpus must be > 0")
    if args.fps is not None and args.fps < MIN_VIDEO_FPS:
        raise SystemExit(f"--fps must be >= {MIN_VIDEO_FPS}")

    case_dir = Path(args.case_dir).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = case_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshots = list_snapshots(case_dir, args.max_frames)
    helper_bin = precompile_get_helpers(snapshots)
    rendered = render_snapshots(
        snapshots,
        args.cpus,
        helper_bin,
        output_dir,
        args.ldomain,
        args.tsnap,
    )
    print(f"Rendered {len(rendered)} frame(s) into {output_dir}")
    if rendered and not args.skip_video:
        frame_count = count_rendered_frames(output_dir)
        fps = choose_video_fps(frame_count, args.fps)
        final_movie = movie_output_path(case_dir)
        print(f"Encoding {frame_count} frame(s) into {final_movie} at {fps} fps...", flush=True)
        assemble_video(output_dir, final_movie, fps)
        print(f"Wrote {final_movie} from {frame_count} frame(s) at {fps} fps")


if __name__ == "__main__":
    main()
