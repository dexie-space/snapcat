from dotenv import load_dotenv
import logging
import os
import pathlib

from chia.util.config import load_config
from chia.util.default_root import DEFAULT_ROOT_PATH


chia_root = pathlib.Path(
    os.path.expanduser(os.environ.get("CHIA_ROOT", DEFAULT_ROOT_PATH))
)
chia_config = load_config(chia_root, "config.yaml")
self_hostname = chia_config["self_hostname"]
full_node_rpc_port = chia_config["full_node"]["rpc_port"]
wallet_rpc_port = chia_config["wallet"]["rpc_port"]


load_dotenv()

loggin_level = os.getenv("LOGGING_LEVEL", "INFO")

log_file = os.getenv("LOG_FILE", "snapcat.log")
logging.basicConfig(
    filename=log_file,
    filemode="a",
    format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=loggin_level,
)

database_path = os.getenv("DB_SOURCE_DIR", ".")
# CAT2 start height: 2,311,760
start_height: int = int(os.getenv("START_HEIGHT", "0"))
target_height: int = int(os.getenv("TARGET_HEIGHT", "-1"))

if start_height < 0:
    raise Exception(
        "START_HEIGHT environment variable must be set to a number greater than 0"
    )
