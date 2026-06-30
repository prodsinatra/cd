# OSINT Defensive Trigger Engine

Self-protection perimeter for research agents. Detects when a query targets
the operator, runs a two-stage privacy firewall, extracts any leaked
technical identifiers from upstream tool output, and appends a structured
audit entry every time.

This is a **defensive** system. It does not perform OSINT on third
parties; it watches your own research surface and blocks or warns when
something looks like deep profiling of you.

## Layout

```
osint_engine/
  config.py       # EngineConfig — operator identifiers + tunables
  firewall.py     # Stage 1 (deterministic) + Stage 2 (intent classifier)
  extractors.py   # IPv4/IPv6 + browser fingerprint extraction
  canary.py       # Honeytoken / OSINT-tool name detection
  audit.py        # Append-only markdown+JSON audit log
  banner.py       # Operator-facing alert banner formatter
  engine.py       # TriggerEngine — coordinates the above
  protective.py   # Protective OSINT workflow (proactive self-sweeps)
  cli.py          # python -m osint_engine.cli ...
```

## Configure

The default identifiers are placeholders. Provide a config file:

```json
{
  "self_identifiers": ["jdoe", "808szn", "my-business-llc"],
  "self_context_pairs": [["brooklyn", "music producer"]],
  "audit_log_path": "/path/you/control/osint_audit.md",
  "deep_threshold": 2,
  "borderline_threshold": 1
}
```

`self_context_pairs` matches only when **both** halves appear in the same
query/context — useful when a single token is too common on its own.

## Use programmatically

```python
from osint_engine import TriggerEngine, EngineConfig

engine = TriggerEngine(EngineConfig(
    self_identifiers=["808szn"],
    audit_log_path="osint_audit.md",
))

decision = engine.evaluate(
    query="public soundcloud mentions of 808szn",
    tool_name="web_search",
    previous_results="<raw output from upstream tool>",
)

if decision.should_block_research:
    raise RuntimeError(decision.message)
if decision.banner:
    print(decision.banner)
```

## Use from the shell

```
python -m osint_engine.cli --query "dox 808szn" --tool web_search
```

Exits non-zero when the decision is `BLOCK`, so it composes with shell
pipelines and CI gates.

## What fires what

| Situation                                              | Action              | Alert level             |
| ------------------------------------------------------ | ------------------- | ----------------------- |
| `dox`, `network mapping`, `full OSINT profile`, …      | `BLOCK`             | Level 2                 |
| Self-identifier + 2+ deep-intent markers               | `BLOCK`             | Level 2                 |
| Self-identifier + 1 deep marker, no light marker       | `ALLOW_WITH_WARNING`| Level 1 - Borderline    |
| Self-identifier + light lookup                         | `ALLOW`             | Level 1                 |
| No self-identifier, no canary hit                      | `ALLOW` (silent)    | None                    |
| Non-self query, but canary/OSINT-tool string present   | `ALLOW`             | Level 1 - Canary        |

## Protective OSINT sweep

```python
from osint_engine.protective import ScopedLookup, run_protective_osint

report = run_protective_osint(
    scopes=[
        ScopedLookup("soundcloud", "public soundcloud mentions of 808szn"),
        ScopedLookup("whois",      "WHOIS records mentioning my-business-llc"),
    ],
    lookup_fn=my_lookup_callable,   # your web/API client
    engine=engine,
)
print(report.recommendations)
```

Each scope is evaluated by the engine, so leaked IPs, fingerprints, and
canary-token references all surface in the report and the audit log under
the `PROTECTIVE_OSINT` tag.

## Audit log

Every trigger writes a markdown entry plus a fenced JSON block to
`config.audit_log_path`. Non-self silent allows are not logged; everything
else is.

## Tests

```
pip install pytest
python -m pytest tests/ -q
```

43 tests cover the firewall stages, extractors, canary detection, audit
writing, the protective workflow, and the module wrapper.
