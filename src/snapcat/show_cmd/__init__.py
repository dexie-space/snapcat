import aiosqlite
import asyncio
import logging
import os
import rich_click as click
from rich.console import Console
from typing import Optional

from chia.types.blockchain_format.sized_bytes import bytes32

from snapcat.shared import Bytes32ParamType

log = logging.getLogger("snapcat")
console = Console()


async def get_cat_db_last_block_height(db):
    async with db.execute(
        "SELECT value FROM config WHERE key = 'last_block_height'"
    ) as cursor:
        row = await cursor.fetchone()
        last_block_height = None if row is None else int(row[0])

    return last_block_height


async def get_cat_db_info(db):
    async with db.execute("SELECT count(*) FROM coin_spends") as cursor:
        row = await cursor.fetchone()
        spend_count = row[0]
    async with db.execute("SELECT count(*) FROM coins") as cursor:
        row = await cursor.fetchone()
        coins_count = row[0]
    return spend_count, coins_count


async def get_puzzle_hash_db_info(db, puzzle_hash: bytes32):
    async with db.execute(
        """
            SELECT coins.coin_name, coins.inner_puzzle_hash, coins.amount
            FROM coins
            LEFT JOIN coin_spends
                ON coins.coin_name = coin_spends.coin_name
            WHERE coin_spends.coin_name IS null
            AND coins.inner_puzzle_hash = ?
            ORDER BY coins.created_height ASC
        """,
        [puzzle_hash.hex()],
    ) as cursor:
        rows = await cursor.fetchall()
        unspent_coins = len(rows)
        unspent_balance = sum([row[2] for row in rows]) / 1e3

    return unspent_coins, unspent_balance


@click.command(help="Display the CAT db information.")
@click.option(
    "-p",
    "--puzzle-hash",
    required=False,
    default=None,
    help="The (inner) puzzle hash to show the unspent coins and available balance for",
    type=Bytes32ParamType(),
)
@click.pass_context
def show(ctx, puzzle_hash: Optional[bytes32]):
    async def _show():
        db_file_name = ctx.obj["db_file_name"]
        if db_file_name is None:
            message = "No database file name provided"
            log.error(message)
            console.print(f"[bold red]{message}")
            exit()

        if not os.path.exists(db_file_name):
            message = "No database file found, please sync first"
            log.error(message)
            console.print(f"[bold red]{message}")
            exit()

        async with aiosqlite.connect(db_file_name) as db:
            async with db.execute(
                "SELECT value FROM config WHERE key = 'tail_hash'"
            ) as cursor:
                row = await cursor.fetchone()
                tail_hash = None if row is None else row[0]
                if tail_hash is None:
                    message = "No tail hash found, please sync first"
                    log.error(message)
                    console.print(f"[bold red]{message}")
                    exit()

            last_block_height = await get_cat_db_last_block_height(db)

            console.print(f"Tail Hash: [bold bright_cyan]{tail_hash}")
            console.print(f"Last Block Height: {last_block_height}")

            if puzzle_hash is not None:
                # show puzzle hash info
                console.print(f"Puzzle Hash: [bold bright_cyan]{puzzle_hash}")
                unspent_coins, unspent_balance = await get_puzzle_hash_db_info(
                    db, puzzle_hash
                )
                console.print(f"# of Unspent Coins: [bold bright_cyan]{unspent_coins}")
                unspent_balance_str = f"{unspent_balance:,.3f}"
                console.print(
                    f"Available Balance: [bold bright_cyan]{unspent_balance_str}"
                )
            else:
                # show db cat info
                spend_count, coins_count = await get_cat_db_info(db)

                console.print(f"# of Coins Spent: {spend_count}")
                console.print(f"# of Coins Created: {coins_count}")

    asyncio.run(_show())
