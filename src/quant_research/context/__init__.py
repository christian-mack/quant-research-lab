"""Program Context System (PCS).

A rebuildable retrieval layer over the program's git-tracked documentation.

The PCS is infrastructure, not a store of record: git holds the canonical
content and ``pcs reindex --all`` reconstructs the index from the repo. The
package is read-only with respect to the repo and the database from the
consumer's perspective (see the implementation spec, section 1.1).

Modules are added milestone by milestone (D1..D8). This is the D1 slice:
configuration, schema, and migration.
"""

from quant_research.context.config import PCSConfig, get_config

__all__ = ["PCSConfig", "get_config"]
