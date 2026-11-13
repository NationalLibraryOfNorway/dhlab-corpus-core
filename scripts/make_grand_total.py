"""Create grand_total.db: the frequency of every word in the whole collection, summed over all shards.

Usage: python scripts/make_grand_total.py <database_dir>
"""

import sqlite3
import sys
from pathlib import Path


def make_grand_total(database_dir: Path) -> Path:
    target = database_dir / "grand_total.db"
    target.unlink(missing_ok=True)
    shards = sorted(database_dir.glob("alto_*.db"))
    if not shards:
        raise SystemExit(f"No alto_*.db files in {database_dir}")

    connection = sqlite3.connect(target)
    try:
        connection.execute("CREATE TEMP TABLE shard_totals (word varchar, tf int)")
        for shard in shards:
            connection.execute("ATTACH DATABASE ? AS shard", (f"{shard.resolve().as_uri()}?mode=ro",))
            connection.execute("INSERT INTO shard_totals SELECT word, tf FROM shard.totals")
            connection.commit()
            connection.execute("DETACH DATABASE shard")
        connection.execute("CREATE TABLE grand_total (word varchar, tf int)")
        connection.execute(
            "INSERT INTO grand_total SELECT word, sum(tf) FROM shard_totals GROUP BY word ORDER BY sum(tf) DESC"
        )
        connection.execute("CREATE INDEX gt_tf_ ON grand_total (tf)")
        connection.commit()
    finally:
        connection.close()
    return target


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(make_grand_total(Path(sys.argv[1])))
