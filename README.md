# When does a drop stop bouncing?

Axisymmetric Basilisk study of an impacting droplet that repeatedly rebounds
from a substrate until viscous dissipation and gravity suppress the bounce.
The repository now follows the CoMPhy project layout: solver sources live in
`simulationCases/`, project-local headers live in `src-local/`, and offline
analysis tools live in `postProcess/`.

## Requirements

- Basilisk with `qcc`
- Python 3 for post-processing scripts
- `ffmpeg` only if video assembly is needed

## Quick Start

Single-case run from the editable root parameter file:

```bash
bash runSimulation.sh
```

Single-case run from a custom parameter file:

```bash
bash runSimulation.sh path/to/custom-case.params
```

Parameter sweep preview:

```bash
bash runParameterSweep.sh --dry-run
```

Parameter sweep execution:

```bash
bash runParameterSweep.sh
```

Legacy launcher compatibility:

```bash
bash job.sh
```

## Parameter Files

- `default.params` is the canonical base configuration used by the sweep runner.
- `case.params` is the editable one-off run configuration at the repository root.
- `sweep.params` defines the Cartesian sweep with `SWEEP_*` variables and the
  deterministic `CASE_START` / `CASE_END` range.
- Default case numbering starts at `1000`, so the first generated cases are
  `simulationCases/1000/`, `simulationCases/1001/`, and so on.
- The default runtime is single-core: `OMP_NUM_THREADS=1` and the default
  compile flags are `-Wall -O2` without `-fopenmp`.
- Each run is materialized in `simulationCases/<CaseNo>/case.params`, alongside
  the compiled executable, `log`, `dump`, and `intermediate/snapshot-*` output.

The Basilisk solver reads `key=value` parameters through
`src-local/parse_params.h` and `src-local/params.h`, so the simulation no
longer depends on fragile positional CLI arguments.

## Post-Processing

- `postProcess/VideoFullDomain.py` renders deterministic `frame_%06d.png`
  outputs from `simulationCases/<CaseNo>/intermediate/` and supports
  batched parallel rendering with `--cpus` / `--CPUs`.
- `postProcess/getEnergyScript.py` and `postProcess/getEpsNForce.py` are
  case-aware wrappers around the `getEnergyAxi` and `getEpsForce` helper
  binaries.
- Helper extractors such as `postProcess/getFacet.c`,
  `postProcess/getDataDropOnly.c`, and `postProcess/getEnergyAxi.c` remain in
  C for direct Basilisk snapshot access.

Example frame render:

```bash
python3 postProcess/VideoFullDomain.py \
  --case-dir simulationCases/1000 \
  --ldomain 4.0 \
  --tsnap 0.01 \
  --skip-video \
  --cpus 4
```

## Repository Structure

```
.github/ - CoMPhy documentation and CI/CD scaffold
├── assets/ - static site assets for generated docs
├── ISSUE_TEMPLATE/ - issue templates
├── scripts/ - documentation build and preview scripts
└── workflows/ - GitHub Actions workflows
AGENTS.md - project-specific agent instructions
case.params - editable one-off runtime configuration
default.params - default simulation parameter template
job.sh - legacy compatibility wrapper for runSimulation.sh
postProcess/ - offline analysis, extraction, and rendering tools
├── FinalManuscript_VelRel.py - legacy manuscript plotting script
├── VideoFullDomain.py - parallel whole-domain frame renderer
├── getData.c - snapshot field extractor
├── getDataDropOnly.c - drop-only field extractor
├── getEnergyAxi.c - integral energy extractor
├── getEnergyScript.py - case-aware energy extraction wrapper
├── getEpsForce.c - wall-force and dissipation extractor
├── getEpsNForce.py - case-aware force extraction wrapper
└── getFacet.c - interface facet extractor
runParameterSweep.sh - deterministic sweep launcher
runSimulation.sh - compile-and-run entry point for one case
simulationCases/ - Basilisk entry points and generated case directories
└── bounce.c - main axisymmetric bouncing-drop solver
src-local/ - project-local headers and shared parameter helpers
├── params.h - typed runtime parameter accessors
├── params.sh - shared shell helpers for parameter files
└── parse_params.h - low-level key=value parser for the solver
sweep.params - sweep definition with SWEEP_* variables
```

## Documentation Site

The repository ships with the standard CoMPhy `.github/` documentation system.
To build and preview the docs locally:

```bash
.github/scripts/build.sh
.github/scripts/deploy.sh
```
