# Node Manifests

This directory holds per-node manifests.

Each node should keep only the minimum local description needed to answer:

- which roles are enabled on this machine
- what the node is optimized for
- which capabilities are intentionally absent
- which services are expected to be local vs remote

The point is to keep node selection explicit while still letting every node pull
the same repo and shared core updates from `main`.

Suggested pattern:

- `nodes/vps/`
- `nodes/engineering-pc/`
- `nodes/local-builder/`

Each node directory should contain:

- `roles.env` or `roles.env.example`
- a short `README.md`
- any small node-specific notes that should not leak into shared core docs

Do not use these manifests to fork shared workflows or contracts. Keep shared
behavior in common repo paths and use node manifests only to declare what is
enabled locally.
