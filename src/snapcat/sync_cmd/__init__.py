import asyncio
import aiosqlite
from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.util.ints import uint32

import logging
import rich_click as click
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    MofNCompleteColumn,
)

from snapcat.config import (
    chia_config,
    chia_root,
    full_node_rpc_port,
    self_hostname,
    start_height,
    target_height,
)

from snapcat.shared import Bytes32ParamType
from snapcat.sync_cmd.sync import get_full_node_synced, process_block

log = logging.getLogger("snapcat")
console = Console()
abort_height = 0


async def syncing_full_node(full_node_rpc, sync_progress):
    log.info("Syncing Full Node")
    full_node_sync_task_id = sync_progress.add_task(
        description="Waiting for full node to sync", total=None
    )

    while True:
        is_synced, sync_height, sync_progress_height = await get_full_node_synced(
            full_node_rpc
        )
        if is_synced:
            message = "Full Node is synced"
            sync_progress.update(
                full_node_sync_task_id,
                visible=False,
            )
            log.info(message)
            print(message)
            break

        sync_progress.update(
            full_node_sync_task_id,
            description="[bold bright_cyan]Syncing Full Node",
            completed=sync_progress_height,
            total=sync_height,
        )
        await asyncio.sleep(5)


async def process_blocks(full_node_rpc, sync_progress, db, tail_hash: bytes32):
    global abort_height
    async with db.execute(
        "SELECT value FROM config WHERE key = 'last_block_height'"
    ) as cursor:
        row = await cursor.fetchone()
        last_block_height = None if row is None else int(row[0])

    height = (
        start_height
        if last_block_height is None
        else max(start_height, last_block_height)
    )

    max_height = target_height if target_height > 0 else uint32.MAXIMUM

    log.info(f"Process Blocks starting from height {start_height} to peak height")
    process_blocks_task_id = sync_progress.add_task(
        description="[bold bright_cyan]Processing Blocks",
    )
    while True:
        _, peak_height, _ = await get_full_node_synced(full_node_rpc)
        end_height = min(peak_height, max_height)

        if height > end_height:
            message = f"Processed all blocks from {start_height} to {end_height}"
            sync_progress.update(process_blocks_task_id, visible=False)
            log.info(message)
            print(message)
            break

        await process_block(full_node_rpc, db, tail_hash, height)

        sync_progress.update(
            process_blocks_task_id,
            completed=height,
            total=end_height,
        )
        height = height + 1
        abort_height = height


@click.command(help="Sync or create (if not exist) the CAT holder database.")
@click.option(
    "-t",
    "--tail-hash",
    required=True,
    help="The TAIL hash of CAT",
    type=Bytes32ParamType(),
)
@click.pass_context
def sync(ctx, tail_hash: bytes32):
    async def _sync(tail_hash: bytes32) -> None:
        db_file_name = (
            ctx.obj["db_file_name"]
            if ctx.obj["db_file_name"] is not None
            else f"{tail_hash.hex()}.db"
        )
        console.print(f"database file name: {db_file_name}")

        async with aiosqlite.connect(db_file_name) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS coin_spends(
                    coin_name TEXT PRIMARY KEY,
                    spent_height INTEGER DEFAULT 0,
                    coins_created INTEGER DEFAULT 0
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS coins(
                    coin_name TEXT PRIMARY KEY,
                    inner_puzzle_hash TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    created_height INTEGER DEFAULT 0
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS config(
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            await db.execute(
                """
                INSERT OR IGNORE INTO config(key, value) VALUES('tail_hash', ?);
                """,
                [tail_hash.hex()],
            )
            await db.commit()

            block_progress = Progress(
                TextColumn("{task.description}"),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                SpinnerColumn("simpleDots"),
                transient=True,
                refresh_per_second=5,
            )
            with block_progress:
                async with FullNodeRpcClient.create_as_context(
                    self_hostname,
                    full_node_rpc_port,
                    chia_root,
                    chia_config,
                ) as full_node_rpc:
                    await syncing_full_node(full_node_rpc, block_progress)
                    await process_blocks(full_node_rpc, block_progress, db, tail_hash)

    try:
        console.print("[bold red]press Ctrl+C to exit.")
        console.print(f"tail hash: {tail_hash.hex()}")
        asyncio.run(_sync(tail_hash))
    except KeyboardInterrupt:
        message = f"Sync cancelled by user at height {abort_height}."
        console.print(f"[bold red]{message}")
        log.info(message)
