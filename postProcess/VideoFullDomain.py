"""Render whole-domain facet snapshots into deterministic movie frames."""

from __future__ import annotations

import argparse
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
    parser.add_argument("--ldomain", type=float, required=True, help="Domain size used for plotting.")
    parser.add_argument("--tsnap", type=float, default=0.01, help="Snapshot cadence for plot titles.")
    parser.add_argument("--fps", type=int, default=25, help="Video frame rate.")
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

    cmd = ["qcc", "-O2", "-Wall", "-disable-dimensions", str(source), "-o", str(binary), "-lm"]
    sp.run(cmd, check=True, cwd=PROJECT_ROOT)
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


def getting_facets(helper_bin: Path, snapshot: Path) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    proc = sp.run([str(helper_bin), str(snapshot)], check=True, capture_output=True, text=True)
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
    return sorted(rendered)


def assemble_video(output_dir: Path, fps: int) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required unless --skip-video is used")
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(output_dir / "frame_%06d.png"),
        "-pix_fmt",
        "yuv420p",
        str(output_dir / "movie.mp4"),
    ]
    sp.run(cmd, check=True)


def main() -> None:
    args = parse_args()
    if args.cpus <= 0:
        raise SystemExit("--cpus must be > 0")

    case_dir = Path(args.case_dir).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = case_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshots = list_snapshots(case_dir, args.max_frames)
    helper_bin = precompile_get_helpers(snapshots)
    rendered = render_snapshots(snapshots, args.cpus, helper_bin, output_dir, args.ldomain, args.tsnap)
    print(f"Rendered {len(rendered)} frame(s) into {output_dir}")
    if rendered and not args.skip_video:
        assemble_video(output_dir, args.fps)


if __name__ == "__main__":
    main()
