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

Current manifest keys:

- `NODE_NAME`
- `TARGET`
- `ENABLED_ROLES`

`TARGET` points at the current runnable compose target. Right now all example
manifests resolve through `prototype-local` because that is the first complete
runnable substrate. As dedicated node targets appear later, the manifests can
move to those without changing the shared control CLI shape.

Do not use these manifests to fork shared workflows or contracts. Keep shared
behavior in common repo paths and use node manifests only to declare what is
enabled locally.
