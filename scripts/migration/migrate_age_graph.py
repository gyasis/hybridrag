#!/usr/bin/env python3
"""
Fast migration using asyncpg with proper graphid generation.
"""

import asyncio
import json
import struct
import networkx as nx


def make_graphid(label_id: int, seq: int) -> bytes:
    """Create AGE graphid as 8-byte little-endian."""
    # graphid = (label_id << 48) | seq
    gid = (label_id << 48) | seq
    return gid


async def migrate_graph():
    """Migrate GraphML to Apache AGE."""
    import asyncpg

    graphml_file = "/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db/graph_chunk_entity_relation.graphml"
    graph_name = "chunk_entity_relation"

    print(f"Loading GraphML from {graphml_file}...")
    G = nx.read_graphml(graphml_file)
    print(f"Graph stats: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    conn = await asyncpg.connect(
        host="localhost",
        port=5433,
        user="hybridrag",
        password="hybridrag_secure_2026",
        database="hybridrag"
    )

    try:
        # Setup AGE
        await conn.execute("LOAD 'age';")
        await conn.execute("SET search_path = ag_catalog, \"$user\", public;")

        # Get label IDs
        base_label = await conn.fetchval(
            "SELECT id FROM ag_catalog.ag_label WHERE graph = 44546 AND name = 'base'"
        )
        directed_label = await conn.fetchval(
            "SELECT id FROM ag_catalog.ag_label WHERE graph = 44546 AND name = 'DIRECTED'"
        )

        print(f"base label: {base_label}, DIRECTED label: {directed_label}")

        # Check current counts
        v_count = await conn.fetchval(
            f"SELECT count(*) FROM {graph_name}.base"
        )
        print(f"Current vertices: {v_count}")

        if v_count > 4:  # More than test nodes
            print("Clearing existing data...")
            await conn.execute(f'DELETE FROM {graph_name}."DIRECTED"')
            await conn.execute(f"DELETE FROM {graph_name}.base")
            print("Cleared.")

        # === MIGRATE VERTICES using raw SQL with agtype cast ===
        print("\nMigrating vertices...")
        nodes = list(G.nodes(data=True))
        total_nodes = len(nodes)
        batch_size = 500
        node_to_gid = {}

        for i in range(0, total_nodes, batch_size):
            batch = nodes[i:i+batch_size]

            for j, (node_id, attrs) in enumerate(batch):
                seq = i + j + 1
                gid = make_graphid(base_label, seq)
                node_to_gid[node_id] = gid

                # Build properties
                props = dict(attrs)
                props["id"] = node_id
                props_json = json.dumps(props)

                # Insert using Cypher-compatible agtype
                await conn.execute(
                    f"""
                    INSERT INTO {graph_name}.base (id, properties)
                    VALUES (
                        ag_catalog._graphid({base_label}::integer, {seq}::bigint),
                        $1::agtype
                    )
                    """,
                    props_json
                )

            if (i + batch_size) % 10000 == 0 or (i + batch_size) >= total_nodes:
                print(f"  Vertices: {min(i + batch_size, total_nodes):,}/{total_nodes:,}")

        print(f"Migrated {total_nodes:,} vertices")

        # === MIGRATE EDGES ===
        print("\nMigrating edges...")
        edges = list(G.edges(data=True))
        total_edges = len(edges)
        batch_size = 1000
        migrated = 0
        skipped = 0

        for i in range(0, total_edges, batch_size):
            batch = edges[i:i+batch_size]

            for j, (src, tgt, attrs) in enumerate(batch):
                if src not in node_to_gid or tgt not in node_to_gid:
                    skipped += 1
                    continue

                seq = migrated + 1
                start_gid = node_to_gid[src]
                end_gid = node_to_gid[tgt]

                props = dict(attrs) if attrs else {}
                props_json = json.dumps(props)

                src_seq = node_to_gid[src] & 0xFFFFFFFFFFFF  # Extract sequence
                tgt_seq = node_to_gid[tgt] & 0xFFFFFFFFFFFF

                await conn.execute(
                    f"""
                    INSERT INTO {graph_name}."DIRECTED" (id, start_id, end_id, properties)
                    VALUES (
                        ag_catalog._graphid({directed_label}::integer, {seq}::bigint),
                        ag_catalog._graphid({base_label}::integer, {src_seq}::bigint),
                        ag_catalog._graphid({base_label}::integer, {tgt_seq}::bigint),
                        $1::agtype
                    )
                    """,
                    props_json
                )
                migrated += 1

            if (i + batch_size) % 20000 == 0 or (i + batch_size) >= total_edges:
                print(f"  Edges: {min(i + batch_size, total_edges):,}/{total_edges:,}")

        print(f"Migrated {migrated:,} edges ({skipped} skipped)")

        # === VERIFY ===
        print("\n=== VERIFICATION ===")
        final_v = await conn.fetchval(f"SELECT count(*) FROM {graph_name}.base")
        final_e = await conn.fetchval(f'SELECT count(*) FROM {graph_name}."DIRECTED"')

        print(f"Final vertices: {final_v:,} (expected: {total_nodes:,})")
        print(f"Final edges: {final_e:,} (expected: {len(edges):,})")

        if final_v >= total_nodes * 0.95:
            print("\n✅ Graph migration complete!")
        else:
            print("\n⚠️ Migration incomplete")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate_graph())
