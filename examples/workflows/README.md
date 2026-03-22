# Workflow examples

This directory holds the high-level workflow specs that sit above low-level `run-plan` files.

- `fluent\steady_run.yaml`: steady single-phase solve from an existing case, case-data, or mesh
- `fluent\reflow_melting.yaml`: transient multiphase reflow/melting solve from an existing case or mesh
- `plans\`: advanced low-level action plans for manual orchestration and debugging

Use the workflow examples with:

```powershell
ansysctl start-workflow fluent.steady_run --spec .\examples\workflows\fluent\steady_run.yaml --workspace .\runs\steady-demo
ansysctl start-workflow fluent.reflow_melting --spec .\examples\workflows\fluent\reflow_melting.yaml --workspace .\runs\reflow-demo
```

These specs assume you already have a mesh or case file.
Geometry import, meshing, Workbench handoff, and Mechanical handoff are outside the Fluent v1 scope.
