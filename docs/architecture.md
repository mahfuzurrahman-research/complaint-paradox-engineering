# Public Engineering Architecture

This companion demonstrates an intentionally bounded analytical system.

```text
synthetic CSV
   ↓
input monitor
   ↓
DuckDB staging table
   ↓
normalized core view
   ↓
analytical marts
   ↓
quality checks
   ↓
JSON / Markdown report
   ↓
static HTML dashboard
   ↓
CI / Docker verification
```

The design goal is inspectable engineering, not disclosure of the private scientific workflow.

## Responsibility boundaries

- **Python:** orchestration, validation, reporting and tests.
- **DuckDB SQL:** relational modeling, marts and data-quality checks.
- **Synthetic data:** deterministic demonstration fixture only.
- **GitHub Actions:** clean-environment verification.
- **Docker:** portable execution of the public companion.

No component consumes private research data.
