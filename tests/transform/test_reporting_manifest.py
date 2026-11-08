"""Rules every reporting model must follow, checked on the parsed dbt project.

These guard against a new or edited reporting model quietly skipping a rule that
`dbt build` itself would not notice: a model without an enforced contract still builds.
"""

from tests.transform.conftest import reporting_models

# Models that hold OLDER dataset versions by design, so their *_version_id columns must
# not be tested against the current version (they would always fail).
HOLDS_OLDER_VERSIONS = {"city_emission_revisions"}
# The lineage table itself: its dataset_version_id is the key the other columns point at.
LINEAGE_MODEL = "dataset_versions"
EXPECTED = {"cities", "city_emissions", "city_emissions_trend", "city_boundaries",
            "city_overlap", "dataset_versions"}


def _column_tests(manifest, model_unique_id: str) -> dict[str, set[str]]:
    """{column name: {generic test names}} for the tests attached to one model."""
    tests: dict[str, set[str]] = {}
    for node in manifest.nodes.values():
        if node.resource_type != "test" or not getattr(node, "test_metadata", None):
            continue
        if node.attached_node == model_unique_id and node.column_name:
            tests.setdefault(node.column_name, set()).add(node.test_metadata.name)
    return tests


def test_reporting_has_the_api_models(dbt_manifest):
    assert EXPECTED <= set(reporting_models(dbt_manifest))


def test_every_reporting_model_is_a_table_with_an_enforced_contract(dbt_manifest):
    problems = []
    for name, node in reporting_models(dbt_manifest).items():
        if node.config.materialized != "table":
            problems.append(f"{name}: materialized={node.config.materialized}, expected table")
        if not node.config.contract.enforced:
            problems.append(f"{name}: contract not enforced")
        if not node.columns:
            problems.append(f"{name}: no columns declared")
        problems += [f"{name}.{c}: no data_type" for c, col in node.columns.items() if not col.data_type]
    assert not problems, "\n".join(problems)


def test_every_version_column_points_at_dataset_versions(dbt_manifest):
    problems = []
    for name, node in reporting_models(dbt_manifest).items():
        if name == LINEAGE_MODEL:
            continue
        tests = _column_tests(dbt_manifest, node.unique_id)
        for column in node.columns:
            if column.endswith("_version_id") and "relationships" not in tests.get(column, set()):
                problems.append(f"{name}.{column}: no relationships test to dataset_versions")
    assert not problems, "\n".join(problems)


def test_version_columns_are_current_except_where_older_versions_are_by_design(dbt_manifest):
    problems = []
    for name, node in reporting_models(dbt_manifest).items():
        if name == LINEAGE_MODEL:
            continue
        tests = _column_tests(dbt_manifest, node.unique_id)
        for column in node.columns:
            if not column.endswith("_version_id"):
                continue
            has_current = "is_current_version" in tests.get(column, set())
            if name in HOLDS_OLDER_VERSIONS and has_current:
                problems.append(f"{name}.{column}: holds older versions by design; must not use is_current_version")
            if name not in HOLDS_OLDER_VERSIONS and not has_current:
                problems.append(f"{name}.{column}: missing is_current_version")
    assert not problems, "\n".join(problems)
