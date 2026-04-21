# Role Overlays

This directory is the landing zone for role-oriented stack overlays.

The repo should evolve around:

- shared core contracts
- composable role overlays
- node manifests that enable those roles

Do not treat role overlays as separate forks of the stack. They exist so one
repo can support multiple nodes without "everything on every machine."

Initial role vocabulary:

- `core`: shared continuity, artifacts, common contracts
- `vps`: user-facing hub and orchestration surfaces
- `media-cpu`: smoke-test and fallback media generation
- `media-gpu`: practical media generation on GPU-backed nodes
- `builder`: page-build and packaging workflows
- `tools`: MCP and operator-facing authoring/debugging surfaces

As the split becomes real, add role-specific compose fragments, env examples,
and activation notes here instead of scattering machine-specific copies across
the repo.

The first concrete role fragments now exist:

- `media-cpu`: makes ComfyUI's CPU-safe default explicit
- `media-gpu`: removes the `--cpu` fallback so a GPU-capable target can opt into
  the same logical media role without rewriting the base stack
- `tools`: tags the authoring/debugging surface from a dedicated role fragment

These fragments are selected through `stack/topology/roles.json` and resolved by
`./bin/start-1215.py compose-cmd <node> ...`.
