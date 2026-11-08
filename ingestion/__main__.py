"""Command line entry point.

    python -m ingestion load --mode download                 # fetch real files, load into warehouse
    python -m ingestion load --mode download --source edgar
    python -m ingestion load --mode sample --target test     # offline sample -> warehouse_test only
    python -m ingestion make-sample                          # rebuild boundary + GHS-UCDB samples from latest downloads
    python -m ingestion make-synthetic                       # regenerate the SYNTHETIC EDGAR fixtures (files only)

Sample and synthetic data are refused by any database not named *_test, so
`load --mode sample` without `--target test` exits with an error.
"""

import argparse

import psycopg

from ingestion.config import SAMPLE_DIR, Settings
from ingestion.pipeline import SOURCES, run_download, run_sample
from ingestion.sample import make_boundary_sample, make_synthetic_edgar, make_ucdb_sample
from ingestion.versioning import NotATestDatabaseError


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ingestion")
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("load", help="load source files into the raw schema")
    # No default: the two modes write to different databases, so the choice is explicit.
    load.add_argument("--mode", choices=["sample", "download"], required=True)
    load.add_argument("--target", choices=["warehouse", "test"], default="warehouse",
                      help="database to load into (default: warehouse). Sample loads need 'test'.")
    load.add_argument("--source", choices=sorted(SOURCES), action="append",
                      help="limit to one source (repeatable); default: all")
    commands.add_parser("make-sample", help="rebuild the boundary and GHS-UCDB samples from the latest downloads")
    commands.add_parser("make-synthetic", help="regenerate the SYNTHETIC EDGAR fixture (no database)")
    args = parser.parse_args()

    if args.command == "make-synthetic":
        for entry in make_synthetic_edgar():
            print(f"SYNTHETIC {entry['source_name']} {entry['rows']} rows -> data/sample/{entry['path']}")
        return

    # autocommit: each file's load is committed by its own `conn.transaction()` block.
    target = args.target if args.command == "load" else "warehouse"  # make-sample reads real downloads
    with psycopg.connect(Settings().dsn(target), autocommit=True) as conn:
        if args.command == "make-sample":
            for f in [*make_boundary_sample(conn), make_ucdb_sample(conn)]:
                size_kb = (SAMPLE_DIR / f["path"]).stat().st_size / 1024
                print(f"{f['source_name']:14} {f['source_key']:11} {f['rows']:>4} rows "
                      f"{size_kb:>8.1f} KB -> {f['path']}")
            return

        sources = [SOURCES[s] for s in (args.source or SOURCES)]
        run = run_sample if args.mode == "sample" else run_download
        try:
            results = run(conn, sources)
        except NotATestDatabaseError as exc:
            raise SystemExit(f"error: {exc}") from None
        for r in results:
            if r.error:
                status = f"FAILED: {r.error}"
            elif r.skipped:
                status = "skipped (already loaded)"
            else:
                status = f"loaded {r.rows_loaded} rows"
            print(f"{r.source_name:14} {r.source_key:11} version={r.dataset_version_id}  {status}")
            for warning in r.warnings:
                print(f"{'':14} check warning: {warning}")
        failed = [r for r in results if r.error]
        if failed:
            raise SystemExit(f"{len(failed)} file(s) failed; re-run to retry them (loaded files are skipped)")


if __name__ == "__main__":
    main()
