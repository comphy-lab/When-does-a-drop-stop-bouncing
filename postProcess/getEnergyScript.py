"""Extract integral energy diagnostics from case snapshots."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTPROCESS_DIR = PROJECT_ROOT / "postProcess"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_no", type=int)
    parser.add_argument("rhor", type=float)
    parser.add_argument("ohd", type=float)
    parser.add_argument("ohs", type=float)
    parser.add_argument("bond", type=float)
    parser.add_argument("we", type=float)
    parser.add_argument("--case-dir", default=None, help="Defaults to simulationCases/<case_no>.")
    parser.add_argument("--tsnap", type=float, default=0.01)
    parser.add_argument("--max-frames", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    case_dir = Path(args.case_dir).resolve() if args.case_dir else PROJECT_ROOT / "simulationCases" / str(args.case_no)
    output_path = case_dir / f"{args.case_no}_getEnergy.dat"
    helper_bin = POSTPROCESS_DIR / "getEnergyAxi"

    if output_path.exists():
        print(f"File {output_path} found; new data will be appended")

    for ti in range(args.max_frames):
        snapshot = case_dir / "intermediate" / f"snapshot-{args.tsnap * ti:5.4f}"
        if not snapshot.exists():
            print(f"File {snapshot} not found!")
            continue
        subprocess.run(
            [
                str(helper_bin),
                str(snapshot),
                str(output_path),
                str(args.rhor),
                str(args.ohd),
                str(args.ohs),
                str(args.bond),
                str(args.we),
            ],
            check=True,
        )
        print(f"Done {ti + 1} of {args.max_frames}")


if __name__ == "__main__":
    main()
