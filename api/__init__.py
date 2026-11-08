"""Read-only HTTP API over the `reporting` schema (Stage 6).

The API connects only as the read-only reader role, which can read `reporting` and
nothing else (db/init/lib/layers.sql). It never joins, aggregates or calls PostGIS:
each endpoint reads one reporting table, built for it by dbt.
"""
