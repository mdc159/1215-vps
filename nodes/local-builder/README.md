# Local Builder Node

The local builder node is for page generation, asset packaging, and isolated
non-GPU worker behavior.

Recommended roles:

- `core`
- `builder`
- optional `tools`

This node is a good fit for page-build pipelines, verification workers, and
agent/tool experimentation that should not sit directly on the shared VPS.
