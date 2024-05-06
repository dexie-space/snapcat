from clvm.casts import int_to_bytes
from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.coin_spend import CoinSpend
from chia.util.hash import std_hash
from chia.util.ints import uint32
from chia.wallet.cat_wallet.cat_utils import CAT_MOD
import logging
from typing import List, Optional, Tuple

from snapcat.cat_utils import create_coin_conditions_for_inner_puzzle, extract_cat

log = logging.getLogger("snapcat")


async def get_full_node_synced(
    full_node_rpc: FullNodeRpcClient,
) -> Tuple[bool, uint32, uint32]:
    blockchain_state = await full_node_rpc.get_blockchain_state()
    sync_state = blockchain_state["sync"]
    synced = sync_state["synced"]
    if not synced:
        return False, sync_state["sync_tip_height"], sync_state["sync_progress_height"]
    else:
        return True, blockchain_state["peak"].height, None


async def process_coin_spends(
    db,
    expected_tail_hash: bytes32,
    height,
    header_hash: str,
    coin_spends: Optional[List[CoinSpend]],
):
    if coin_spends is None or len(coin_spends) == 0:
        return None

    log.info(
        "Processing %i coin spends for block %s at height %i",
        len(coin_spends),
        header_hash,
        height,
    )

    for coin_spend in coin_spends:
        result = extract_cat(expected_tail_hash, coin_spend)

        if result is None:
            log.debug(f"{expected_tail_hash.hex()} CAT coin spend not found")
        else:
            outer_puzzle = coin_spend.puzzle_reveal.to_program()
            outer_solution = coin_spend.solution.to_program()
            inner_solution = outer_solution.first()
            (_, outer_puzzle, _, inner_puzzle, _) = result

            coin_spend_coin_name = coin_spend.coin.name().hex()

            # create coin conditions
            inner_puzzle_create_coin_conditions = (
                create_coin_conditions_for_inner_puzzle(
                    bytes32.fromhex(coin_spend_coin_name), inner_puzzle, inner_solution
                )
            )

            await db.execute(
                """
                INSERT OR IGNORE INTO coin_spends values (?, ?, ?)
                """,
                [
                    coin_spend_coin_name,
                    height,
                    len(inner_puzzle_create_coin_conditions),
                ],
            )
            for coin in inner_puzzle_create_coin_conditions:
                outer_puzzle_hash = CAT_MOD.curry(
                    CAT_MOD.get_tree_hash(),
                    expected_tail_hash,
                    coin.puzzle_hash,
                ).get_tree_hash_precalc(coin.puzzle_hash)

                created_coin_name = std_hash(
                    bytes32.fromhex(coin_spend_coin_name)
                    + outer_puzzle_hash
                    + int_to_bytes(coin.amount)
                ).hex()

                await db.execute(
                    """
                    INSERT OR IGNORE INTO coins values (?, ?, ?, ?)
                    """,
                    [
                        created_coin_name,
                        coin.puzzle_hash.hex(),
                        coin.amount,
                        height,
                    ],
                )


async def process_block(
    full_node_rpc: FullNodeRpcClient, db, tail_hash: bytes32, height: int
):
    block_record = await full_node_rpc.get_block_record_by_height(height)
    if block_record is None:
        log.error("Failed to get block record at height: %i", height)
        return

    log.debug("Got block record %s at height: %i", block_record.header_hash, height)

    if block_record.timestamp is not None:
        log.debug("Processing transaction block %s", block_record.header_hash)

        coin_spends = await full_node_rpc.get_block_spends(block_record.header_hash)

        if coin_spends is not None and len(coin_spends) > 0:
            log.debug("%i spends found in block %i", len(coin_spends), height)
            await process_coin_spends(
                db, tail_hash, height, block_record.header_hash, coin_spends
            )

        else:
            log.debug("None at %i", height)
    else:
        log.debug("Skipping non-transaction block at height %i", height)

    await db.execute(
        """
        INSERT INTO config(key, value)
        VALUES('last_block_height', ?)
        ON CONFLICT(key) DO UPDATE SET value=?;
        """,
        [height, height],
    )
    await db.commit()
