"""Command line entry point.

    python -m ingestion load --mode sample           # offline, from data/sample (default)
    python -m ingestion load --mode download         # fetch real files, then load
    python -m ingestion load --mode download --source edgar
    python -m ingestion make-sample                  # rebuild boundary sample from latest downloads
    python -m ingestion make-synthetic               # regenerate the SYNTHETIC EDGAR fixture
"""

import argparse

import psycopg

from ingestion.config import Settings
from ingestion.pipeline import SOURCES, run_download, run_sample
from ingestion.sample import make_boundary_sample, make_synthetic_edgar


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ingestion")
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("load", help="load source files into the raw schema")
    load.add_argument("--mode", choices=["sample", "download"], default="sample")
    load.add_argument("--source", choices=sorted(SOURCES), action="append",
                      help="limit to one source (repeatable); default: all")
    commands.add_parser("make-sample", help="rebuild the boundary sample from the latest downloads")
    commands.add_parser("make-synthetic", help="regenerate the SYNTHETIC EDGAR fixture (no database)")
    args = parser.parse_args()

    if args.command == "make-synthetic":
        entry = make_synthetic_edgar()
        print(f"SYNTHETIC {entry['source_name']} {entry['rows']} rows -> data/sample/{entry['path']}")
        return

    # autocommit: each file's load is committed by its own `conn.transaction()` block.
    with psycopg.connect(Settings().pipeline_dsn, autocommit=True) as conn:
        if args.command == "make-sample":
            for f in make_boundary_sample(conn):
                print(f"{f['source_name']:14} {f['source_key']:10} {f['rows']:>4} rows -> {f['path']}")
            return

        sources = [SOURCES[s] for s in (args.source or SOURCES)]
        run = run_sample if args.mode == "sample" else run_download
        results = run(conn, sources)
        for r in results:
            if r.error:
                status = f"FAILED: {r.error}"
            elif r.skipped:
                status = "skipped (already loaded)"
            else:
                status = f"loaded {r.rows_loaded} rows"
            print(f"{r.source_name:14} {r.source_key:10} version={r.dataset_version_id}  {status}")
        failed = [r for r in results if r.error]
        if failed:
            raise SystemExit(f"{len(failed)} file(s) failed; re-run to retry them (loaded files are skipped)")


if __name__ == "__main__":
    main()
