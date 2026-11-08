-- The API's read-only role can read every relation in `reporting` and nothing in raw or
-- modelled. Runs after every reporting model is (re)built (depends_on below), so it proves
-- the grant survives dbt dropping and recreating the tables. It relies on dbt connecting as
-- the role named in ALTER DEFAULT PRIVILEGES (db/init/lib/layers.sql); a table created by
-- any other role would show up here. One row per problem.
-- depends_on: {{ ref('cities') }} {{ ref('city_emissions') }} {{ ref('city_emissions_trend') }}
-- depends_on: {{ ref('city_boundaries') }} {{ ref('city_overlap') }} {{ ref('dataset_versions') }}
-- depends_on: {{ ref('city_emission_revisions') }}
{% set reader = env_var('TEST_API_READER_USER', 'test_api_reader') if target.name == 'test'
                else env_var('API_READER_USER', 'api_reader') %}
select 'cannot read reporting.' || c.relname as problem
from pg_class as c
where c.relnamespace = 'reporting'::regnamespace
  and c.relkind in ('r', 'v', 'm', 'p')
  and not has_table_privilege('{{ reader }}', c.oid, 'SELECT')
union all
select 'no USAGE on schema reporting'
where not has_schema_privilege('{{ reader }}', 'reporting', 'USAGE')
union all
select 'has USAGE on schema ' || s
from unnest(array['raw', 'modelled']) as s
where has_schema_privilege('{{ reader }}', s, 'USAGE')
