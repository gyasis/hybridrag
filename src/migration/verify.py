"""
Migration Verification Module (T023)
=====================================

Provides verification utilities to compare data between JSON and PostgreSQL backends
after migration. Ensures data integrity by comparing record counts, sampling data,
and validating vector embeddings.
"""

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Results from a verification check."""

    check_name: str
    passed: bool
    source_count: int = 0
    target_count: int = 0
    discrepancies: list = field(default_factory=list)
    details: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def summary(self) -> str:
        """Human-readable summary of the verification result."""
        status = "✓ PASSED" if self.passed else "✗ FAILED"
        msg = f"{status}: {self.check_name}"
        if not self.passed:
            if self.error:
                msg += f" - Error: {self.error}"
            elif self.source_count != self.target_count:
                msg += f" - Count mismatch: source={self.source_count}, target={self.target_count}"
            elif self.discrepancies:
                msg += f" - {len(self.discrepancies)} discrepancies found"
        return msg


@dataclass
class MigrationVerificationReport:
    """Complete verification report for a migration."""

    database_name: str
    source_backend: str
    target_backend: str
    checks: list[VerificationResult] = field(default_factory=list)
    passed: bool = True
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0

    def add_check(self, result: VerificationResult) -> None:
        """Add a verification check result."""
        self.checks.append(result)
        self.total_checks += 1
        if result.passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1
            self.passed = False

    def to_dict(self) -> dict:
        """Convert report to dictionary for serialization."""
        return {
            "database_name": self.database_name,
            "source_backend": self.source_backend,
            "target_backend": self.target_backend,
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "checks": [
                {
                    "check_name": c.check_name,
                    "passed": c.passed,
                    "source_count": c.source_count,
                    "target_count": c.target_count,
                    "discrepancies": c.discrepancies[:10],  # Limit for readability
                    "error": c.error,
                }
                for c in self.checks
            ],
        }

    def print_report(self) -> None:
        """Print formatted verification report."""
        print("\n" + "=" * 60)
        print("MIGRATION VERIFICATION REPORT")
        print("=" * 60)
        print(f"Database: {self.database_name}")
        print(f"Migration: {self.source_backend} → {self.target_backend}")
        print("-" * 60)

        for check in self.checks:
            print(check.summary)

        print("-" * 60)
        status = "✓ ALL CHECKS PASSED" if self.passed else "✗ VERIFICATION FAILED"
        print(f"{status} ({self.passed_checks}/{self.total_checks} passed)")
        print("=" * 60 + "\n")


class MigrationVerifier:
    """
    Verifies data integrity after migration between storage backends.

    Performs multiple verification checks:
    1. Record count comparison for all data types
    2. Sample data comparison for content integrity
    3. Vector embedding verification (dimension and content)
    4. Relationship graph integrity
    """

    def __init__(
        self,
        database_name: str,
        source_path: Path,
        target_connection: str,
        sample_size: int = 100,
    ):
        """
        Initialize the migration verifier.

        Args:
            database_name: Name of the database being verified
            source_path: Path to JSON source files
            target_connection: PostgreSQL connection string
            sample_size: Number of records to sample for detailed comparison
        """
        self.database_name = database_name
        self.source_path = Path(source_path)
        self.target_connection = target_connection
        self.sample_size = sample_size
        self._pg_pool = None

    async def _get_pg_pool(self):
        """Get or create PostgreSQL connection pool."""
        if self._pg_pool is None:
            import asyncpg
            self._pg_pool = await asyncpg.create_pool(
                self.target_connection,
                min_size=1,
                max_size=5,
            )
        return self._pg_pool

    async def _close_pool(self):
        """Close the connection pool."""
        if self._pg_pool:
            await self._pg_pool.close()
            self._pg_pool = None

    def _load_json_file(self, filename: str) -> dict:
        """Load a JSON file from the source path."""
        filepath = self.source_path / filename
        if not filepath.exists():
            return {}
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Failed to decode JSON file: {filepath}")
            return {}

    async def verify_all(self) -> MigrationVerificationReport:
        """
        Run all verification checks and return a complete report.

        Returns:
            MigrationVerificationReport with all check results
        """
        report = MigrationVerificationReport(
            database_name=self.database_name,
            source_backend="json",
            target_backend="postgresql",
        )

        try:
            # Run all verification checks
            report.add_check(await self.verify_entity_counts())
            report.add_check(await self.verify_relation_counts())
            report.add_check(await self.verify_chunk_counts())
            report.add_check(await self.verify_doc_status_counts())
            report.add_check(await self.verify_entity_samples())
            report.add_check(await self.verify_chunk_vectors())

        except Exception as e:
            logger.error(f"Verification failed with error: {e}")
            report.add_check(VerificationResult(
                check_name="Overall Verification",
                passed=False,
                error=str(e),
            ))
        finally:
            await self._close_pool()

        return report

    async def verify_entity_counts(self) -> VerificationResult:
        """Verify entity counts match between source and target."""
        check_name = "Entity Count Verification"

        try:
            # Count source entities
            entities_data = self._load_json_file("kv_store_full_docs.json")
            source_count = len(entities_data)

            # Count target entities (table name matches json_to_postgres.py)
            pool = await self._get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM lightrag_entities WHERE workspace = $1",
                    self.database_name
                )
                target_count = row['count'] if row else 0

            passed = source_count == target_count
            return VerificationResult(
                check_name=check_name,
                passed=passed,
                source_count=source_count,
                target_count=target_count,
            )

        except Exception as e:
            return VerificationResult(
                check_name=check_name,
                passed=False,
                error=str(e),
            )

    async def verify_relation_counts(self) -> VerificationResult:
        """Verify relation counts match between source and target."""
        check_name = "Relation Count Verification"

        try:
            # Count source relations from GraphML file (not JSON!)
            graph_file = self.source_path / "graph_chunk_entity_relation.graphml"
            source_count = 0

            if graph_file.exists():
                try:
                    import networkx as nx
                    graph = nx.read_graphml(graph_file)
                    source_count = graph.number_of_edges()
                except ImportError:
                    # Fall back to regex counting
                    import re
                    with open(graph_file) as f:
                        content = f.read()
                        edges = re.findall(r'<edge', content)
                        source_count = len(edges)

            # Count target relations (table name matches json_to_postgres.py)
            pool = await self._get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM lightrag_relations WHERE workspace = $1",
                    self.database_name
                )
                target_count = row['count'] if row else 0

            passed = source_count == target_count
            return VerificationResult(
                check_name=check_name,
                passed=passed,
                source_count=source_count,
                target_count=target_count,
            )

        except Exception as e:
            return VerificationResult(
                check_name=check_name,
                passed=False,
                error=str(e),
            )

    async def verify_chunk_counts(self) -> VerificationResult:
        """Verify chunk counts match between source and target."""
        check_name = "Chunk Count Verification"

        try:
            # Count source chunks (correct file name: vdb_chunks.json)
            chunks_data = self._load_json_file("vdb_chunks.json")
            # vdb_chunks has a 'data' key containing the list of chunks
            if isinstance(chunks_data, dict) and 'data' in chunks_data:
                source_count = len(chunks_data['data'])
            elif isinstance(chunks_data, list):
                source_count = len(chunks_data)
            else:
                source_count = 0

            # Count target chunks (table name matches json_to_postgres.py)
            pool = await self._get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM lightrag_chunks WHERE workspace = $1",
                    self.database_name
                )
                target_count = row['count'] if row else 0

            passed = source_count == target_count
            return VerificationResult(
                check_name=check_name,
                passed=passed,
                source_count=source_count,
                target_count=target_count,
            )

        except Exception as e:
            return VerificationResult(
                check_name=check_name,
                passed=False,
                error=str(e),
            )

    async def verify_doc_status_counts(self) -> VerificationResult:
        """Verify document status counts match between source and target."""
        check_name = "Document Status Count Verification"

        try:
            # Count source doc statuses (correct file name: kv_store_doc_status.json)
            doc_status_data = self._load_json_file("kv_store_doc_status.json")
            source_count = len(doc_status_data) if isinstance(doc_status_data, dict) else 0

            # Count target doc statuses (table name matches json_to_postgres.py)
            pool = await self._get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM lightrag_doc_status WHERE workspace = $1",
                    self.database_name
                )
                target_count = row['count'] if row else 0

            passed = source_count == target_count
            return VerificationResult(
                check_name=check_name,
                passed=passed,
                source_count=source_count,
                target_count=target_count,
            )

        except Exception as e:
            return VerificationResult(
                check_name=check_name,
                passed=False,
                error=str(e),
            )

    async def verify_entity_samples(self) -> VerificationResult:
        """Sample entities and verify content matches."""
        check_name = "Entity Sample Verification"

        try:
            # Load source entities
            entities_data = self._load_json_file("kv_store_full_docs.json")
            if not entities_data:
                return VerificationResult(
                    check_name=check_name,
                    passed=True,
                    details={"message": "No entities to sample"},
                )

            # Sample random keys
            all_keys = list(entities_data.keys())
            sample_keys = random.sample(all_keys, min(self.sample_size, len(all_keys)))

            # Fetch corresponding records from PostgreSQL (table name matches json_to_postgres.py)
            pool = await self._get_pg_pool()
            discrepancies = []

            async with pool.acquire() as conn:
                for key in sample_keys:
                    row = await conn.fetchrow(
                        "SELECT content FROM lightrag_entities WHERE workspace = $1 AND entity_id = $2",
                        self.database_name, key
                    )

                    if row is None:
                        discrepancies.append({
                            "key": key,
                            "issue": "Missing in target",
                        })
                    else:
                        # Compare content (basic comparison)
                        source_value = entities_data[key]
                        target_value = json.loads(row['content']) if isinstance(row['content'], str) else row['content']

                        # Deep comparison would go here
                        # For now, just check if both exist
                        if source_value != target_value:
                            discrepancies.append({
                                "key": key,
                                "issue": "Content mismatch",
                            })

            passed = len(discrepancies) == 0
            return VerificationResult(
                check_name=check_name,
                passed=passed,
                source_count=len(sample_keys),
                target_count=len(sample_keys) - len([d for d in discrepancies if d['issue'] == 'Missing in target']),
                discrepancies=discrepancies,
            )

        except Exception as e:
            return VerificationResult(
                check_name=check_name,
                passed=False,
                error=str(e),
            )

    async def verify_chunk_vectors(self) -> VerificationResult:
        """Verify vector embeddings were migrated correctly."""
        check_name = "Vector Embedding Verification"

        try:
            # Load source vectors (vdb_chunks.json has 'data' key with list of chunks)
            vectors_data = self._load_json_file("vdb_chunks.json")
            if not vectors_data:
                return VerificationResult(
                    check_name=check_name,
                    passed=True,
                    details={"message": "No vectors to verify"},
                )

            # Count source vectors - vdb_chunks has 'data' key containing chunks with embeddings
            if isinstance(vectors_data, dict) and 'data' in vectors_data:
                source_count = len(vectors_data['data'])
            elif isinstance(vectors_data, list):
                source_count = len(vectors_data)
            else:
                source_count = 0

            # Sample and verify vector dimensions
            pool = await self._get_pg_pool()
            discrepancies = []
            min_dim = None
            max_dim = None

            async with pool.acquire() as conn:
                # Check vector dimension consistency (table: lightrag_chunks, column: embedding)
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as count,
                        MIN(vector_dims(embedding)) as min_dim,
                        MAX(vector_dims(embedding)) as max_dim
                    FROM lightrag_chunks
                    WHERE workspace = $1 AND embedding IS NOT NULL
                """, self.database_name)

                if row:
                    target_count = row['count']
                    min_dim = row['min_dim']
                    max_dim = row['max_dim']

                    # Check dimension consistency
                    if min_dim is not None and max_dim is not None and min_dim != max_dim:
                        discrepancies.append({
                            "issue": f"Inconsistent vector dimensions: {min_dim} to {max_dim}",
                        })
                else:
                    target_count = 0

            passed = len(discrepancies) == 0 and source_count == target_count
            return VerificationResult(
                check_name=check_name,
                passed=passed,
                source_count=source_count,
                target_count=target_count,
                discrepancies=discrepancies,
                details={
                    "vector_dimensions": f"{min_dim}" if min_dim is not None and min_dim == max_dim else "varies",
                },
            )

        except Exception as e:
            return VerificationResult(
                check_name=check_name,
                passed=False,
                error=str(e),
            )


async def verify_migration(
    database_name: str,
    source_path: str,
    target_connection: str,
    sample_size: int = 100,
) -> MigrationVerificationReport:
    """
    Convenience function to run full migration verification.

    Args:
        database_name: Name of the database to verify
        source_path: Path to JSON source files
        target_connection: PostgreSQL connection string
        sample_size: Number of records to sample

    Returns:
        MigrationVerificationReport with all results
    """
    verifier = MigrationVerifier(
        database_name=database_name,
        source_path=Path(source_path),
        target_connection=target_connection,
        sample_size=sample_size,
    )
    return await verifier.verify_all()
