import aiosqlite
import asyncio
import csv
import json
import logging
import os
from rich.console import Console
import rich_click as click

import snapcat.config as Config

log = logging.getLogger("snapcat")
console = Console()


async def get_cat_balance(db, coins: bool):
    cursor = (
        await db.execute(
            """
            SELECT coins.coin_name, coins.inner_puzzle_hash, coins.amount
            FROM coins
            LEFT JOIN coin_spends
                ON coins.coin_name = coin_spends.coin_name
            WHERE coin_spends.coin_name IS null
            ORDER BY coins.created_height ASC
        """
        )
        if coins
        else await db.execute(
            """
            SELECT coins.inner_puzzle_hash, sum(coins.amount)
            FROM coins
            LEFT JOIN coin_spends ON coins.coin_name = coin_spends.coin_name
            WHERE coin_spends.coin_name IS null
            GROUP BY coins.inner_puzzle_hash
            ORDER BY MIN(coins.created_height) ASC
        """
        )
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return rows


@click.command(help="Export the CAT holder as csv or json.")
@click.option(
    "-o",
    "--output",
    required=False,
    default=None,
    help="The name of the output file (default: <tail_hash>-<block>.csv or .json)",
)
@click.option(
    "-c",
    "--coins",
    is_flag=True,
    default=False,
    help="Show individual coins in output rather than collapsing on puzzle hash",
)
@click.option(
    "-j",
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Export as JSON instead of CSV",
)
@click.pass_context
def export(ctx, output: str, coins: bool, as_json: bool):
    async def _export(output: str, coins: bool, json: bool):
        db_file_name = ctx.obj["db_file_name"]
        if db_file_name is None:
            message = "No database file name provided"
            log.error(message)
            console.print(f"[bold red]{message}")
            exit()

        db_file = f"{Config.database_path}{db_file_name}"
        if not os.path.exists(db_file):
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
            log.info(f"Exporting CAT holders for {tail_hash}")
            console.print("Exporting CAT holders")
            console.print(f"Tail Hash: [bold bright_cyan]{tail_hash}")
            balances = await get_cat_balance(db, coins)

            async with db.execute(
                "SELECT value FROM config WHERE key = 'last_block_height'"
            ) as cursor:
                row = await cursor.fetchone()
                last_block_height = None if row is None else int(row[0])

            console.print(f"Last Block Height: {last_block_height}")

            if output is None:

                ext = "json" if json else "csv"
                output = (
                    f"{tail_hash}-{last_block_height}{'-coins' if coins else ''}.{ext}"
                )

            with open(output, "w") as f:
                if as_json:
                    data = json.dumps(
                        [
                            (
                                {
                                    "coin_name": balance[0],
                                    "puzzle_hash": balance[1],
                                    "amount": balance[2],
                                }
                                if coins
                                else {"puzzle_hash": balance[0], "amount": balance[1]}
                            )
                            for balance in balances
                        ]
                    )
                    f.write(data)
                else:
                    headers = (
                        ["coin_name", "puzzle_hash", "amount"]
                        if coins
                        else ["puzzle_hash", "amount"]
                    )
                    writer = csv.writer(f)
                    writer.writerows([headers] + balances)

    asyncio.run(_export(output, coins, json))
