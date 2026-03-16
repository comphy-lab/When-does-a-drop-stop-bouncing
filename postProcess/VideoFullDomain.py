"""
# Whole-Domain Video Renderer

Render mirrored full-domain movies from axisymmetric Basilisk snapshots.

## Workflow

1. Discover `snapshot-*` dumps under a case directory.
2. Compile the Basilisk helpers `getFacet.c` and `getData.c` on demand.
3. Sample the positive-r half-domain fields and mirror them across the axis.
4. Draw `D2` on the left half and `|u|` on the right half.
5. Optionally encode the rendered frames into an MP4 with `ffmpeg`.

## Dependencies

- `numpy`: grid reshaping and masking
- `matplotlib`: frame rendering
- `qcc`: helper compilation
- `ffmpeg`: optional MP4 assembly
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import subprocess as sp

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.ticker import StrMethodFormatter
import numpy as np

"""
## Paths and Rendering Defaults

Centralize repository-relative paths and rendering constants so the CLI and the
worker processes agree on helper locations and video pacing.
"""

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTPROCESS_DIR = PROJECT_ROOT / "postProcess"
CACHE_ROOT = POSTPROCESS_DIR / ".video-cache"
TARGET_VIDEO_SECONDS = 10.0
MIN_VIDEO_FPS = 30

matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["mathtext.fontset"] = "cm"


@dataclass(frozen=True)
class FieldData:
    """
    Sampled half-domain fields parsed from `getData`.

    #### Attributes

    - `z`: Unique axial coordinates.
    - `r`: Unique positive-r coordinates.
    - `d2`: Masked `D2` field on the half-domain sampling grid.
    - `vel`: Masked velocity-magnitude field on the same grid.
    """

    z: np.ndarray
    r: np.ndarray
    d2: np.ma.MaskedArray
    vel: np.ma.MaskedArray


def parse_args() -> argparse.Namespace:
    """
    Parse command-line options for frame rendering and video assembly.

    #### Returns

    - `argparse.Namespace`: Parsed CLI arguments.
    """
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
    parser.add_argument("--ldomain", type=float, default=8.0, help="Vertical domain size used for plotting.")
    parser.add_argument("--ny", type=int, default=400, help="Number of sampling cells along the positive-r half.")
    parser.add_argument("--tsnap", type=float, default=0.01, help="Fallback snapshot cadence for plot titles.")
    parser.add_argument("--fps", type=int, default=None, help="Override automatic video frame rate (minimum 30).")
    parser.add_argument("--max-frames", type=int, default=None, help="Limit rendered frames for testing.")
    parser.add_argument("--skip-video", action="store_true", help="Only render frames; do not call ffmpeg.")
    parser.add_argument("--cpus", "--CPUs", dest="cpus", type=int, default=4, help="Worker processes to use.")
    parser.add_argument("--d2-cmap", default="hot_r", help="Colormap for D2 on the left half.")
    parser.add_argument("--vel-cmap", default="Blues", help="Colormap for velocity on the right half.")
    parser.add_argument("--d2-vmin", type=float, default=-1.0, help="Minimum color limit for D2.")
    parser.add_argument("--d2-vmax", type=float, default=2.0, help="Maximum color limit for D2.")
    parser.add_argument("--vel-vmin", type=float, default=0.0, help="Minimum color limit for velocity.")
    parser.add_argument("--vel-vmax", type=float, default=None, help="Maximum color limit for velocity.")
    return parser.parse_args()


def list_snapshots(case_dir: Path, max_frames: int | None) -> list[Path]:
    """Return sorted snapshot files, optionally truncated to `max_frames`."""
    snapshots = sorted((case_dir / "intermediate").glob("snapshot-*"))
    if max_frames is not None:
        snapshots = snapshots[:max_frames]
    return snapshots


def snapshot_time(snapshot: Path, tsnap_fallback: float, frame_index: int) -> float:
    """Recover physical time from the snapshot filename or fall back to `tsnap`."""
    suffix = snapshot.name.split("snapshot-", 1)[-1]
    try:
        return float(suffix)
    except ValueError:
        return frame_index * tsnap_fallback


def clean_existing_frames(output_dir: Path) -> None:
    """Delete stale `frame_*.png` files before a fresh render pass."""
    for old_png in output_dir.glob("frame_*.png"):
        old_png.unlink()


def compile_helper(source_name: str, binary_name: str) -> Path:
    """
    Compile a Basilisk helper if the binary is missing or older than the source.

    #### Returns

    - `Path`: Path to the ready-to-run helper binary.
    """
    source = POSTPROCESS_DIR / source_name
    binary = POSTPROCESS_DIR / binary_name
    if binary.exists() and binary.stat().st_mtime >= source.stat().st_mtime:
        return binary

    cmd = ["qcc", "-O2", "-Wall", "-disable-dimensions", source.name, "-o", binary.name, "-lm"]
    sp.run(cmd, check=True, cwd=POSTPROCESS_DIR)
    return binary


def precompile_get_helpers(snapshots: list[Path]) -> tuple[Path | None, Path | None]:
    """Compile `getFacet` and `getData` only when snapshots are present."""
    if not snapshots:
        return None, None
    return compile_helper("getFacet.c", "getFacet"), compile_helper("getData.c", "getData")


def configure_worker_environment(cache_root: Path) -> None:
    """Create per-process Matplotlib and TeX cache directories for worker safety."""
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
    """Express `path` relative to `PROJECT_ROOT` for subprocess calls."""
    return os.path.relpath(path, PROJECT_ROOT)


def run_helper(command: list[str]) -> str:
    """Execute a helper binary from the project root and return merged text output."""
    proc = sp.run(command, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
    return f"{proc.stdout}{proc.stderr}"


def parse_facet_segments(raw: str) -> np.ndarray:
    """Convert raw facet-point text into `LineCollection`-ready segment pairs."""
    points: list[list[float]] = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            points.append([float(parts[0]), float(parts[1])])
        except ValueError:
            continue

    if len(points) < 2:
        return np.empty((0, 2, 2), dtype=float)

    usable = len(points) - (len(points) % 2)
    return np.asarray(points[:usable], dtype=float).reshape(-1, 2, 2)


def map_segments_to_rz(segments: np.ndarray) -> np.ndarray:
    """Swap Basilisk's `(z, r)` output ordering into plotting `(r, z)` ordering."""
    if len(segments) == 0:
        return segments
    return segments[..., [1, 0]].copy()


def mirror_segments_about_axis(segments_rz: np.ndarray) -> np.ndarray:
    """Mirror positive-r interface segments across the symmetry axis."""
    if len(segments_rz) == 0:
        return segments_rz
    mirrored = segments_rz.copy()
    mirrored[..., 0] *= -1.0
    return np.concatenate([mirrored, segments_rz], axis=0)


def get_facets(helper_bin: Path, snapshot: Path) -> np.ndarray:
    """Return mirrored interface segments for a single snapshot."""
    raw = run_helper([str(helper_bin), project_relative(snapshot)])
    return mirror_segments_about_axis(map_segments_to_rz(parse_facet_segments(raw)))


def get_field_data(helper_bin: Path, snapshot: Path, ldomain: float, ny: int) -> FieldData:
    """
    Sample `D2` and `|u|` from one snapshot onto a uniform half-domain grid.

    #### Returns

    - `FieldData`: Parsed masked arrays and the corresponding coordinate axes.
    """
    raw = run_helper(
        [
            str(helper_bin),
            project_relative(snapshot),
            f"{0.0:.16g}",
            f"{0.0:.16g}",
            f"{ldomain:.16g}",
            f"{(ldomain / 2.0):.16g}",
            str(ny),
        ]
    )

    rows = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            rows.append([float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])])
        except ValueError:
            continue

    if not rows:
        raise RuntimeError(f"No field data parsed for {snapshot}")

    arr = np.asarray(rows, dtype=float)
    z = arr[:, 0]
    r = arr[:, 1]
    d2 = arr[:, 2]
    vel = arr[:, 3]

    z_unique = np.unique(z)
    r_unique = np.unique(r)
    iz = np.searchsorted(z_unique, z)
    ir = np.searchsorted(r_unique, r)

    d2_grid = np.full((len(r_unique), len(z_unique)), np.nan, dtype=float)
    vel_grid = np.full((len(r_unique), len(z_unique)), np.nan, dtype=float)
    d2_grid[ir, iz] = d2
    vel_grid[ir, iz] = vel

    d2_invalid = (~np.isfinite(d2_grid)) | (np.abs(d2_grid) > 1e20)
    vel_invalid = (~np.isfinite(vel_grid)) | (np.abs(vel_grid) > 1e20)

    return FieldData(
        z=z_unique,
        r=r_unique,
        d2=np.ma.array(d2_grid, mask=d2_invalid),
        vel=np.ma.array(vel_grid, mask=vel_invalid),
    )


def mirror_field(field_positive: np.ma.MaskedArray, r_positive: np.ndarray) -> tuple[np.ndarray, np.ma.MaskedArray]:
    """Mirror a half-domain field and return the full radial coordinate vector."""
    field_rz_positive = np.ma.array(field_positive.T, copy=False)
    r_negative = -r_positive[::-1]
    field_negative = field_rz_positive[:, ::-1]
    r_full = np.concatenate([r_negative, r_positive])
    field_full = np.ma.concatenate([field_negative, field_rz_positive], axis=1)
    return r_full, field_full


def mask_field_to_side(field_rz: np.ma.MaskedArray, r_full: np.ndarray, side: str) -> np.ma.MaskedArray:
    """Hide one side of a mirrored field so the two diagnostics can share one axis."""
    masked = np.ma.array(field_rz, copy=True)
    if side == "left":
        masked[:, r_full > 0.0] = np.ma.masked
        return masked
    if side == "right":
        masked[:, r_full < 0.0] = np.ma.masked
        return masked
    raise ValueError(f"Unsupported side selector: {side}")


def grid_extent(r_full: np.ndarray, z: np.ndarray) -> list[float]:
    """Compute `imshow()` extents from cell-centered radial and axial coordinates."""
    dr = float(np.median(np.diff(r_full))) if len(r_full) > 1 else 1.0
    dz = float(np.median(np.diff(z))) if len(z) > 1 else 1.0
    return [r_full[0] - 0.5 * dr, r_full[-1] + 0.5 * dr, z[0] - 0.5 * dz, z[-1] + 0.5 * dz]


def auto_limits(field: np.ma.MaskedArray) -> tuple[float | None, float | None]:
    """Estimate robust plotting limits from the 2nd and 98th percentiles."""
    values = field.compressed()
    if values.size == 0:
        return None, None
    vmin = float(np.percentile(values, 2.0))
    vmax = float(np.percentile(values, 98.0))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
        vmin = float(np.nanmin(values))
        vmax = float(np.nanmax(values))
    return vmin, vmax


def add_colorbar(fig: plt.Figure, ax: plt.Axes, mappable, side: str, label: str) -> None:
    """Attach a side-specific vertical colorbar outside the main movie frame."""
    left, bottom, width, height = ax.get_position().bounds
    cb_width = 0.025
    cb_gap = 0.035
    if side == "left":
        cb_ax = fig.add_axes([left - cb_gap - cb_width, bottom, cb_width, height])
    else:
        cb_ax = fig.add_axes([left + width + cb_gap, bottom, cb_width, height])
    colorbar = fig.colorbar(mappable, cax=cb_ax, orientation="vertical")
    colorbar.set_label(label, fontsize=18, labelpad=6)
    colorbar.ax.tick_params(labelsize=14, width=1.2, length=4, direction="out")
    colorbar.ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.2f}"))
    if side == "left":
        colorbar.ax.yaxis.set_ticks_position("left")
        colorbar.ax.yaxis.set_label_position("left")


"""
## Frame Rendering

The functions below transform helper output into mirrored fields, paint the two
diagnostics on one canvas, and optionally parallelize rendering across worker
processes.
"""

def render_single_snapshot(
    frame_index: int,
    snapshot: Path,
    facet_bin: Path,
    data_bin: Path,
    output_dir: Path,
    ldomain: float,
    ny: int,
    tsnap: float,
    cache_root: Path,
    d2_limits: tuple[float | None, float | None],
    vel_limits: tuple[float | None, float | None],
    d2_cmap: str,
    vel_cmap: str,
) -> Path:
    """
    Render one PNG frame for a single snapshot.

    #### Returns

    - `Path`: Path to the written `frame_*.png` image.
    """
    configure_worker_environment(cache_root)

    fields = get_field_data(data_bin, snapshot, ldomain, ny)
    facets = get_facets(facet_bin, snapshot)

    r_full_d2, d2_rz = mirror_field(fields.d2, fields.r)
    r_full_vel, vel_rz = mirror_field(fields.vel, fields.r)
    if len(r_full_d2) != len(r_full_vel) or not np.allclose(r_full_d2, r_full_vel):
        raise RuntimeError(f"Inconsistent radial grids in {snapshot}")

    d2_rz = mask_field_to_side(d2_rz, r_full_d2, "left")
    vel_rz = mask_field_to_side(vel_rz, r_full_vel, "right")
    extent = grid_extent(r_full_d2, fields.z)
    output_path = output_dir / f"frame_{frame_index:06d}.png"
    time_value = snapshot_time(snapshot, tsnap, frame_index)

    fig, ax = plt.subplots(figsize=(19.20, 10.80), dpi=180)

    d2_image = ax.imshow(
        d2_rz,
        origin="lower",
        extent=extent,
        cmap=d2_cmap,
        vmin=d2_limits[0],
        vmax=d2_limits[1],
        aspect="equal",
        interpolation="nearest",
        zorder=1,
    )
    vel_image = ax.imshow(
        vel_rz,
        origin="lower",
        extent=extent,
        cmap=vel_cmap,
        vmin=vel_limits[0],
        vmax=vel_limits[1],
        aspect="equal",
        interpolation="nearest",
        zorder=2,
    )

    if len(facets):
        ax.add_collection(LineCollection(facets, colors="white", linewidths=2.8, alpha=0.9, zorder=3))
        ax.add_collection(LineCollection(facets, colors="black", linewidths=1.4, alpha=1.0, zorder=4))

    rmax = ldomain / 2.0
    ax.plot([0.0, 0.0], [0.0, ldomain], "--", color="0.5", linewidth=1.0, zorder=5)
    ax.plot([-rmax, -rmax], [0.0, ldomain], "-", color="black", linewidth=1.8, zorder=5)
    ax.plot([rmax, rmax], [0.0, ldomain], "-", color="black", linewidth=1.8, zorder=5)
    ax.plot([-rmax, rmax], [0.0, 0.0], "-", color="black", linewidth=1.8, zorder=5)
    ax.plot([-rmax, rmax], [ldomain, ldomain], "-", color="black", linewidth=1.8, zorder=5)

    ax.set_xlim(-rmax, rmax)
    ax.set_ylim(0.0, ldomain)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(rf"$V_0 t/R_0 = {time_value:4.3f}$", fontsize=24, pad=16)

    fig.tight_layout(rect=(0.10, 0.03, 0.90, 0.96))
    add_colorbar(fig, ax, d2_image, "left", r"$\log_{10}\!\left(\|\mathcal{D}\|\right)$")
    add_colorbar(fig, ax, vel_image, "right", r"$|\mathbf{u}|$")

    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_snapshots(
    snapshots: list[Path],
    cpus: int,
    facet_bin: Path | None,
    data_bin: Path | None,
    output_dir: Path,
    ldomain: float,
    ny: int,
    tsnap: float,
    d2_limits: tuple[float | None, float | None],
    vel_limits: tuple[float | None, float | None],
    d2_cmap: str,
    vel_cmap: str,
) -> list[Path]:
    """Render all requested snapshots, either serially or in CPU-sized batches."""
    if not snapshots:
        return []
    if cpus <= 0:
        raise ValueError("--cpus must be > 0")
    if facet_bin is None or data_bin is None:
        raise RuntimeError("Helper binaries are required when snapshots are present")

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    tasks = list(enumerate(snapshots))
    total = len(tasks)
    rendered: list[Path] = []

    if cpus == 1:
        for frame_index, snapshot in tasks:
            frame_path = render_single_snapshot(
                frame_index,
                snapshot,
                facet_bin,
                data_bin,
                output_dir,
                ldomain,
                ny,
                tsnap,
                CACHE_ROOT,
                d2_limits,
                vel_limits,
                d2_cmap,
                vel_cmap,
            )
            rendered.append(frame_path)
            print(f"[{frame_index + 1}/{total}] wrote {frame_path}", flush=True)
        return rendered

    with ProcessPoolExecutor(max_workers=cpus) as executor:
        for start in range(0, total, cpus):
            batch = tasks[start : start + cpus]
            futures = [
                executor.submit(
                    render_single_snapshot,
                    frame_index,
                    snapshot,
                    facet_bin,
                    data_bin,
                    output_dir,
                    ldomain,
                    ny,
                    tsnap,
                    CACHE_ROOT,
                    d2_limits,
                    vel_limits,
                    d2_cmap,
                    vel_cmap,
                )
                for frame_index, snapshot in batch
            ]
            batch_results = [future.result() for future in futures]
            rendered.extend(batch_results)
            for frame_index, frame_path in sorted(zip((item[0] for item in batch), batch_results), key=lambda pair: pair[0]):
                print(f"[{frame_index + 1}/{total}] wrote {frame_path}", flush=True)
    return sorted(rendered)


def count_rendered_frames(output_dir: Path) -> int:
    """Count PNG frames produced in `output_dir`."""
    return sum(1 for _ in output_dir.glob("frame_*.png"))


def movie_output_path(case_dir: Path) -> Path:
    """Return the default MP4 path `<case_dir>/<case_no>.mp4`."""
    return case_dir / f"{case_dir.name}.mp4"


def choose_video_fps(frame_count: int, fps_override: int | None) -> int:
    """Choose a frame rate that targets a short movie while honoring `--fps`."""
    if frame_count <= 0:
        raise ValueError("frame_count must be > 0")
    if fps_override is not None:
        if fps_override < MIN_VIDEO_FPS:
            raise ValueError(f"--fps must be >= {MIN_VIDEO_FPS}")
        return fps_override
    return max(MIN_VIDEO_FPS, math.ceil(frame_count / TARGET_VIDEO_SECONDS))


def assemble_video(output_dir: Path, output_path: Path, fps: int) -> None:
    """Encode rendered frames into an H.264 MP4 using `ffmpeg`."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required unless --skip-video is used")
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        "0",
        "-i",
        str(output_dir / "frame_%06d.png"),
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


"""
## Command-Line Entry Point

`main()` validates the CLI, renders frames, and optionally assembles the final
movie once all PNGs are present.
"""

def main() -> None:
    """Run the end-to-end rendering pipeline for one simulation case."""
    args = parse_args()
    if args.cpus <= 0:
        raise SystemExit("--cpus must be > 0")
    if args.ny <= 2:
        raise SystemExit("--ny must be > 2")
    if args.fps is not None and args.fps < MIN_VIDEO_FPS:
        raise SystemExit(f"--fps must be >= {MIN_VIDEO_FPS}")

    case_dir = Path(args.case_dir).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = case_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_existing_frames(output_dir)

    snapshots = list_snapshots(case_dir, args.max_frames)
    if not snapshots:
        raise SystemExit(f"No snapshots found under {case_dir / 'intermediate'}")

    facet_bin, data_bin = precompile_get_helpers(snapshots)
    if facet_bin is None or data_bin is None:
        raise SystemExit("Unable to compile helper binaries")

    first_fields = get_field_data(data_bin, snapshots[0], args.ldomain, args.ny)
    auto_d2 = auto_limits(first_fields.d2)
    auto_vel = auto_limits(first_fields.vel)
    d2_limits = (
        args.d2_vmin if args.d2_vmin is not None else auto_d2[0],
        args.d2_vmax if args.d2_vmax is not None else auto_d2[1],
    )
    vel_limits = (
        args.vel_vmin if args.vel_vmin is not None else auto_vel[0],
        args.vel_vmax if args.vel_vmax is not None else auto_vel[1],
    )

    rendered = render_snapshots(
        snapshots,
        args.cpus,
        facet_bin,
        data_bin,
        output_dir,
        args.ldomain,
        args.ny,
        args.tsnap,
        d2_limits,
        vel_limits,
        args.d2_cmap,
        args.vel_cmap,
    )
    print(f"Rendered {len(rendered)} frame(s) into {output_dir}")

    if rendered and not args.skip_video:
        frame_count = count_rendered_frames(output_dir)
        fps = choose_video_fps(frame_count, args.fps)
        output_path = movie_output_path(case_dir)
        print(f"Encoding {frame_count} frame(s) into {output_path} at {fps} fps...", flush=True)
        assemble_video(output_dir, output_path, fps)
        print(f"Wrote {output_path} from {frame_count} frame(s) at {fps} fps")


if __name__ == "__main__":
    main()
