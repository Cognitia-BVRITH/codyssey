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

## Planned runtime settings

[config.example.yaml](../config.example.yaml) describes proposed storage, provider,
budget, and sandbox settings. It is not loaded or validated by the current CLI.
Copy it to ignored `config.yaml` when runtime configuration is implemented.

[.env.example](../.env.example) lists proposed provider environment variables.
There is no automatic dotenv loader. Future adapters should read credentials
from the environment and avoid logging them. Keep endpoint/model choices in
configuration and verify supported model IDs before use.

The example sandbox image is intentionally unset. Each real target needs a
compatible environment; installing the controller's Python dependencies does not
prepare a target repository. Token/cost ceilings and sandbox resource settings
become effective only when their runtime enforcement is implemented.
