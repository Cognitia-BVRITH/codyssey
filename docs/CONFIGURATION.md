# Configuration and task input

## Current behavior

Install the package using [CONTRIBUTING.md](../CONTRIBUTING.md). Run
`codyssey validate-task path/to/task.json` to check a prepared task without
executing its repository or contacting any service.

The JSON fields are:

| Field | Meaning |
| --- | --- |
| `id` | Nonempty task identity |
| `repo_url` | Repository location; reachability is not checked yet |
| `base_commit` | Exact 40-character hexadecimal Git commit |
| `issue_title`, `issue_body` | Nonempty issue description |
| `environment_image` | Prepared target image name; existence is not checked yet |
| `test_command` | Nonempty argument array, for example `["python", "-m", "pytest"]` |
| `fail_to_pass` | Required failing pytest node IDs |
| `pass_to_pass` | Required regression pytest node IDs |

Unknown fields, overlapping groups, duplicate test identities, and blank list
entries are rejected. Schema validation does not establish that an environment
can build, the bug reproduces, or a patch is correct.

## Runtime settings

[config.example.yaml](../config.example.yaml) describes storage, provider, budget, and
sandbox settings. `codyssey.config.load_config(path)` reads a YAML file into a
validated `CodysseyConfig`; omitted sections and an empty file use the defaults,
and unknown keys, out-of-range values, and inconsistent combinations are rejected.
Copy the example to ignored `config.yaml` for local use.

Two combinations are rejected explicitly: a non-deterministic strategy with
`repair.max_llm_calls: 0`, and `repair.max_estimated_cost_usd` without both
`llm.input_usd_per_million_tokens` and `llm.output_usd_per_million_tokens`. The
price assumptions are part of the configuration saved with each run. Estimated cost
is calculated locally from provider-reported token counts and is not a billing
figure.

`storage.database_url` must be a `sqlite:///path` URL. `llm.api_key_env` names the
environment variable that holds the key; keys are never read from or written to
configuration or run records.

[.env.example](../.env.example) lists proposed provider environment variables.
There is no automatic dotenv loader. Future adapters should read credentials
from the environment and avoid logging them. Keep endpoint/model choices in
configuration and verify supported model IDs before use.

The example sandbox image is intentionally unset. Each real target needs a
compatible environment; installing the controller's Python dependencies does not
prepare a target repository. Sandbox resource settings become effective only when
the sandbox validator enforces them; budget settings are enforced by the controller
(see the architecture document).
