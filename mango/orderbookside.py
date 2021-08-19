# # ⚠ Warning
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
# LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
# NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# [🥭 Mango Markets](https://mango.markets/) support is available at:
#   [Docs](https://docs.mango.markets/)
#   [Discord](https://discord.gg/67jySBhxrg)
#   [Twitter](https://twitter.com/mangomarkets)
#   [Github](https://github.com/blockworks-foundation)
#   [Email](mailto:hello@blockworks.foundation)

import typing

from decimal import Decimal
from solana.publickey import PublicKey

from .accountinfo import AccountInfo
from .addressableaccount import AddressableAccount
from .context import Context
from .layouts import layouts
from .metadata import Metadata
from .orders import Order, OrderType, Side
from .perpmarketdetails import PerpMarketDetails
from .version import Version

# # 🥭 OrderBookSide class
#
# `OrderBookSide` holds orders for one side of a market.
#


class OrderBookSide(AddressableAccount):
    def __init__(self, account_info: AccountInfo, version: Version,
                 meta_data: Metadata, perp_market_details: PerpMarketDetails, bump_index: Decimal,
                 free_list_len: Decimal, free_list_head: Decimal, root_node: Decimal,
                 leaf_count: Decimal, nodes: typing.Any):
        super().__init__(account_info)
        self.version: Version = version

        self.meta_data: Metadata = meta_data
        self.perp_market_details: PerpMarketDetails = perp_market_details
        self.bump_index: Decimal = bump_index
        self.free_list_len: Decimal = free_list_len
        self.free_list_head: Decimal = free_list_head
        self.root_node: Decimal = root_node
        self.leaf_count: Decimal = leaf_count
        self.nodes: typing.Any = nodes

    @staticmethod
    def from_layout(layout: layouts.ORDERBOOK_SIDE, account_info: AccountInfo, version: Version, perp_market_details: PerpMarketDetails) -> "OrderBookSide":
        meta_data = Metadata.from_layout(layout.meta_data)
        bump_index: Decimal = layout.bump_index
        free_list_len: Decimal = layout.free_list_len
        free_list_head: Decimal = layout.free_list_head
        root_node: Decimal = layout.root_node
        leaf_count: Decimal = layout.leaf_count
        nodes: typing.Any = layout.nodes

        return OrderBookSide(account_info, version, meta_data, perp_market_details, bump_index, free_list_len, free_list_head, root_node, leaf_count, nodes)

    @staticmethod
    def parse(context: Context, account_info: AccountInfo, perp_market_details: PerpMarketDetails) -> "OrderBookSide":
        data = account_info.data
        if len(data) != layouts.ORDERBOOK_SIDE.sizeof():
            raise Exception(
                f"OrderBookSide data length ({len(data)}) does not match expected size ({layouts.ORDERBOOK_SIDE.sizeof()})")

        layout = layouts.ORDERBOOK_SIDE.parse(data)
        return OrderBookSide.from_layout(layout, account_info, Version.V1, perp_market_details)

    @staticmethod
    def load(context: Context, address: PublicKey, perp_market_details: PerpMarketDetails) -> "OrderBookSide":
        account_info = AccountInfo.load(context, address)
        if account_info is None:
            raise Exception(f"OrderBookSide account not found at address '{address}'")
        return OrderBookSide.parse(context, account_info, perp_market_details)

    def orders(self):
        if self.leaf_count == 0:
            return

        if self.meta_data.data_type == layouts.DATA_TYPE.Bids:
            order_side = Side.BUY
        else:
            order_side = Side.SELL

        stack = [self.root_node]
        while len(stack) > 0:
            index = int(stack.pop())
            node = self.nodes[index]
            if node.type_name == "leaf":
                price = node.key["price"]
                quantity = node.quantity

                decimals_differential = self.perp_market_details.base_token.decimals - self.perp_market_details.quote_token.decimals
                native_to_ui = Decimal(10) ** decimals_differential
                quote_lot_size = self.perp_market_details.quote_lot_size
                base_lot_size = self.perp_market_details.base_lot_size
                actual_price = price * (quote_lot_size / base_lot_size) * native_to_ui

                base_factor = Decimal(10) ** self.perp_market_details.base_token.decimals
                actual_quantity = (quantity * self.perp_market_details.base_lot_size) / base_factor

                yield Order(int(node.key["order_id"]),
                            node.client_order_id,
                            node.owner,
                            order_side,
                            actual_price,
                            actual_quantity,
                            OrderType.UNKNOWN)
            elif node.type_name == "inner":
                if order_side == Side.BUY:
                    stack = [node.children[0], node.children[1], *stack]
                else:
                    stack = [node.children[1], node.children[0], *stack]

    def __str__(self) -> str:
        nodes = "\n        ".join([str(node).replace("\n", "\n        ") for node in self.orders()])
        return f"""« 𝙾𝚛𝚍𝚎𝚛𝙱𝚘𝚘𝚔𝚂𝚒𝚍𝚎 {self.version} [{self.address}]
    {self.meta_data}
    Perp Market: {self.perp_market_details}
    Bump Index: {self.bump_index}
    Free List: {self.free_list_head} (head) {self.free_list_len} (length)
    Root Node: {self.root_node}
    Leaf Count: {self.leaf_count}
        {nodes}
»"""