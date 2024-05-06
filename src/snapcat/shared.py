import rich_click as click
from chia.types.blockchain_format.sized_bytes import bytes32


class Bytes32ParamType(click.ParamType):
    name = "bytes32"

    def convert(self, value, param, ctx):  # type: ignore
        try:
            bytes32_value: bytes32 = bytes32.from_hexstr(value)
            return bytes32_value
        except ValueError:
            self.fail(f"Invalid bytes32: {value}", param, ctx)
