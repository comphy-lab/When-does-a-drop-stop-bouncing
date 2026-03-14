# Repository Guidelines

## Structure
- `simulationCases/` contains Basilisk entry points and generated per-case run directories.
- `src-local/` contains project-local headers and parameter parsing helpers.
- `postProcess/` contains offline extraction, plotting, and manuscript-analysis tooling.
- Repository root contains parameter files and launcher scripts.

## Runtime Workflow
- Prefer `bash runSimulation.sh [case-params-file]` for single runs.
- Prefer `bash runParameterSweep.sh [--dry-run] [sweep-params-file]` for Cartesian sweeps.
- Keep runtime parameters in `key=value` files; do not reintroduce positional CLI arguments.
- Treat `simulationCases/<CaseNo>/` as generated run output and preserve contents during refactors unless explicitly asked otherwise.

## Editing Rules
- Keep Basilisk-specific headers in `src-local/` and include them explicitly from simulation sources.
- Keep helper extractors in `postProcess/` and compile them from the project root or through script-managed paths.
- Update `README.md` when runner contracts, layout, or post-processing usage changes.
- `CLAUDE.md` is a local pointer only and should stay ignored.
