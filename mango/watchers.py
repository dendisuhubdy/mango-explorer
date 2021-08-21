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

import logging
import typing

from pyserum.market import Market as PySerumMarket
from pyserum.market.orderbook import OrderBook as PySerumOrderBook
from solana.publickey import PublicKey

from .account import Account
from .accountinfo import AccountInfo
from .combinableinstructions import CombinableInstructions
from .context import Context
from .group import Group
from .healthcheck import HealthCheck
from .instructions import build_create_serum_open_orders_instructions
from .inventory import Inventory, InventorySource
from .market import Market
from .observables import DisposePropagator, LatestItemObserverSubscriber
from .openorders import OpenOrders
from .oracle import Price
from .oraclefactory import OracleProvider, create_oracle_provider
from .orderbookside import OrderBookSideType, PerpOrderBookSide
from .orders import Order
from .perpmarket import PerpMarket
from .placedorder import PlacedOrdersContainer
from .serummarket import SerumMarket
from .spotmarket import SpotMarket
from .spotmarketinstructionbuilder import SpotMarketInstructionBuilder
from .spotmarketoperations import SpotMarketOperations
from .tokenaccount import TokenAccount
from .wallet import Wallet
from .watcher import Watcher, LamdaUpdateWatcher
from .websocketsubscription import WebSocketAccountSubscription, WebSocketSubscription, WebSocketSubscriptionManager


def build_group_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, group: Group) -> Watcher[Group]:
    group_subscription = WebSocketAccountSubscription[Group](
        context, group.address, lambda account_info: Group.parse(context, account_info))
    manager.add(group_subscription)
    latest_group_observer = LatestItemObserverSubscriber[Group](group)
    group_subscription.publisher.subscribe(latest_group_observer)
    health_check.add("group_subscription", group_subscription.publisher)
    return latest_group_observer


def build_account_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, account: Account, group_observer: Watcher[Group]) -> typing.Tuple[WebSocketSubscription[Account], Watcher[Account]]:
    account_subscription = WebSocketAccountSubscription[Account](
        context, account.address, lambda account_info: Account.parse(account_info, group_observer.latest))
    manager.add(account_subscription)
    latest_account_observer = LatestItemObserverSubscriber[Account](account)
    account_subscription.publisher.subscribe(latest_account_observer)
    health_check.add("account_subscription", account_subscription.publisher)
    return account_subscription, latest_account_observer


def build_spot_open_orders_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, wallet: Wallet, account: Account, group: Group, spot_market: SpotMarket) -> Watcher[PlacedOrdersContainer]:
    market_index = group.find_spot_market_index(spot_market.address)
    open_orders_address = account.spot_open_orders[market_index]
    if open_orders_address is None:
        spot_market_instruction_builder: SpotMarketInstructionBuilder = SpotMarketInstructionBuilder.load(
            context, wallet, spot_market.group, account, spot_market)
        market_operations: SpotMarketOperations = SpotMarketOperations(
            context, wallet, spot_market.group, account, spot_market, spot_market_instruction_builder)
        open_orders_address = market_operations.create_openorders()
        logging.info(f"Created {spot_market.symbol} OpenOrders at: {open_orders_address}")

    spot_open_orders_subscription = WebSocketAccountSubscription[OpenOrders](
        context, open_orders_address, lambda account_info: OpenOrders.parse(account_info, spot_market.base.decimals, spot_market.quote.decimals))
    manager.add(spot_open_orders_subscription)
    initial_spot_open_orders = OpenOrders.load(
        context, open_orders_address, spot_market.base.decimals, spot_market.quote.decimals)
    latest_open_orders_observer = LatestItemObserverSubscriber[PlacedOrdersContainer](
        initial_spot_open_orders)
    spot_open_orders_subscription.publisher.subscribe(latest_open_orders_observer)
    health_check.add("open_orders_subscription", spot_open_orders_subscription.publisher)
    return latest_open_orders_observer


def build_serum_open_orders_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, serum_market: SerumMarket, wallet: Wallet) -> Watcher[PlacedOrdersContainer]:
    all_open_orders = OpenOrders.load_for_market_and_owner(
        context, serum_market.address, wallet.address, context.dex_program_id, serum_market.base.decimals, serum_market.quote.decimals)
    if len(all_open_orders) > 0:
        initial_serum_open_orders: OpenOrders = all_open_orders[0]
        open_orders_address = initial_serum_open_orders.address
    else:
        raw_market = PySerumMarket.load(context.client.compatible_client, serum_market.address)
        create_open_orders = build_create_serum_open_orders_instructions(
            context, wallet, raw_market)

        open_orders_address = create_open_orders.signers[0].public_key()

        logging.info(f"Creating OpenOrders account for market {serum_market.symbol} at {open_orders_address}.")
        signers: CombinableInstructions = CombinableInstructions.from_wallet(wallet)
        transaction_ids = (signers + create_open_orders).execute(context)
        context.client.wait_for_confirmation(transaction_ids)
        initial_serum_open_orders = OpenOrders.load(
            context, open_orders_address, serum_market.base.decimals, serum_market.quote.decimals)

    serum_open_orders_subscription = WebSocketAccountSubscription[OpenOrders](
        context, open_orders_address, lambda account_info: OpenOrders.parse(account_info, serum_market.base.decimals, serum_market.quote.decimals))

    manager.add(serum_open_orders_subscription)

    latest_serum_open_orders_observer = LatestItemObserverSubscriber[PlacedOrdersContainer](
        initial_serum_open_orders)
    serum_open_orders_subscription.publisher.subscribe(latest_serum_open_orders_observer)
    health_check.add("open_orders_subscription", serum_open_orders_subscription.publisher)
    return latest_serum_open_orders_observer


def build_perp_open_orders_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, perp_market: PerpMarket, account: Account, group: Group, account_subscription: WebSocketSubscription[Account]) -> Watcher[PlacedOrdersContainer]:
    index = group.find_perp_market_index(perp_market.address)
    initial_perp_account = account.perp_accounts[index]
    if initial_perp_account is None:
        raise Exception(f"Could not find perp account at index {index} of account {account.address}.")
    initial_open_orders = initial_perp_account.open_orders
    latest_open_orders_observer = LatestItemObserverSubscriber[PlacedOrdersContainer](initial_open_orders)
    account_subscription.publisher.subscribe(
        on_next=lambda updated_account: latest_open_orders_observer.on_next(updated_account.perp_accounts[index].open_orders))
    health_check.add("open_orders_subscription", account_subscription.publisher)
    return latest_open_orders_observer


def build_price_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, disposer: DisposePropagator, provider_name: str, market: Market) -> LatestItemObserverSubscriber[Price]:
    oracle_provider: OracleProvider = create_oracle_provider(context, provider_name)
    oracle = oracle_provider.oracle_for_market(context, market)
    if oracle is None:
        raise Exception(f"Could not find oracle for market {market.symbol} from provider {provider_name}.")

    initial_price = oracle.fetch_price(context)
    price_feed = oracle.to_streaming_observable(context)
    latest_price_observer = LatestItemObserverSubscriber(initial_price)
    price_disposable = price_feed.subscribe(latest_price_observer)
    disposer.add_disposable(price_disposable)
    health_check.add("price_subscription", price_feed)
    return latest_price_observer


def build_serum_inventory_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, disposer: DisposePropagator, wallet: Wallet, market: Market) -> Watcher[Inventory]:
    base_account = TokenAccount.fetch_largest_for_owner_and_token(
        context, wallet.address, market.base)
    if base_account is None:
        raise Exception(
            f"Could not find token account owned by {wallet.address} for base token {market.base}.")
    base_token_subscription = WebSocketAccountSubscription[TokenAccount](
        context, base_account.address, lambda account_info: TokenAccount.parse(account_info, market.base))
    manager.add(base_token_subscription)
    latest_base_token_account_observer = LatestItemObserverSubscriber[TokenAccount](base_account)
    base_subscription_disposable = base_token_subscription.publisher.subscribe(latest_base_token_account_observer)
    disposer.add_disposable(base_subscription_disposable)

    quote_account = TokenAccount.fetch_largest_for_owner_and_token(
        context, wallet.address, market.quote)
    if quote_account is None:
        raise Exception(
            f"Could not find token account owned by {wallet.address} for quote token {market.quote}.")
    quote_token_subscription = WebSocketAccountSubscription[TokenAccount](
        context, quote_account.address, lambda account_info: TokenAccount.parse(account_info, market.quote))
    manager.add(quote_token_subscription)
    latest_quote_token_account_observer = LatestItemObserverSubscriber[TokenAccount](quote_account)
    quote_subscription_disposable = quote_token_subscription.publisher.subscribe(latest_quote_token_account_observer)
    disposer.add_disposable(quote_subscription_disposable)

    def serum_inventory_accessor() -> Inventory:
        return Inventory(InventorySource.SPL_TOKENS,
                         latest_base_token_account_observer.latest.value,
                         latest_quote_token_account_observer.latest.value)

    return LamdaUpdateWatcher(serum_inventory_accessor)


def build_perp_orderbook_side_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, perp_market: PerpMarket, side: OrderBookSideType) -> Watcher[typing.Sequence[Order]]:
    orderbook_address: PublicKey = perp_market.underlying_perp_market.bids if side == OrderBookSideType.BIDS else perp_market.underlying_perp_market.asks
    orderbook_side_info = AccountInfo.load(context, orderbook_address)
    if orderbook_side_info is None:
        raise Exception(f"Could not find perp order book side at address {orderbook_address}.")
    initial_orderbook_side: PerpOrderBookSide = PerpOrderBookSide.parse(
        context, orderbook_side_info, perp_market.underlying_perp_market)

    orders_subscription = WebSocketAccountSubscription[typing.Sequence[Order]](
        context, orderbook_address, lambda account_info: PerpOrderBookSide.parse(context, account_info, perp_market.underlying_perp_market).orders())
    manager.add(orders_subscription)

    latest_orders_observer = LatestItemObserverSubscriber[typing.Sequence[Order]](initial_orderbook_side.orders())

    orders_subscription.publisher.subscribe(latest_orders_observer)
    health_check.add("orderbook_side_subscription", orders_subscription.publisher)
    return latest_orders_observer


def build_serum_orderbook_side_watcher(context: Context, manager: WebSocketSubscriptionManager, health_check: HealthCheck, underlying_serum_market: PySerumMarket, side: OrderBookSideType) -> Watcher[typing.Sequence[Order]]:
    orderbook_address: PublicKey = underlying_serum_market.state.bids if side == OrderBookSideType.BIDS else underlying_serum_market.state.asks
    orderbook_side_info = AccountInfo.load(context, orderbook_address)
    if orderbook_side_info is None:
        raise Exception(f"Could not find Serum order book side at address {orderbook_address}.")

    def account_info_to_orderbook(account_info: AccountInfo) -> typing.Sequence[Order]:
        serum_orderbook_side = PySerumOrderBook.from_bytes(
            underlying_serum_market.state, account_info.data)
        return list(map(Order.from_serum_order, serum_orderbook_side.orders()))

    initial_orderbook_side: typing.Sequence[Order] = account_info_to_orderbook(orderbook_side_info)

    orders_subscription = WebSocketAccountSubscription[typing.Sequence[Order]](
        context, orderbook_address, account_info_to_orderbook)
    manager.add(orders_subscription)

    latest_orders_observer = LatestItemObserverSubscriber[typing.Sequence[Order]](initial_orderbook_side)

    orders_subscription.publisher.subscribe(latest_orders_observer)
    health_check.add("orderbook_side_subscription", orders_subscription.publisher)
    return latest_orders_observer
