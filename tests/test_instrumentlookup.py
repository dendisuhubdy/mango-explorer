from .context import mango

from solana.publickey import PublicKey


def test_spl_token_lookup() -> None:
    data = {
        "tokens": [
            {
                "address": "So11111111111111111111111111111111111111112",
                "symbol": "SOL",
                "name": "Wrapped SOL",
                "decimals": 9,
            },
            {
                "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "symbol": "USDC",
                "name": "USD Coin",
                "decimals": 6,
            },
            {
                "address": "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E",
                "symbol": "BTC",
                "name": "Wrapped Bitcoin (Sollet)",
                "decimals": 6,
            },
            {
                "address": "2FPyTwcZLUg1MDrwsyoP4D6s1tM7hAkHYRjkNb5w6Pxk",
                "symbol": "ETH",
                "name": "Wrapped Ethereum (Sollet)",
                "decimals": 6,
            }]
    }
    actual = mango.SPLTokenLookup("test-filename", data)
    assert actual is not None
    assert actual.logger is not None
    eth = actual.find_by_symbol("ETH")
    assert eth is not None
    assert eth.name == "Wrapped Ethereum (Sollet)"
    btc = actual.find_by_symbol("BTC")
    assert btc is not None
    assert btc.name == "Wrapped Bitcoin (Sollet)"


def test_spl_token_lookups_with_full_data() -> None:
    actual = mango.SPLTokenLookup.load(mango.SPLTokenLookup.DefaultDataFilepath)
    btc = actual.find_by_symbol("BTC")
    assert btc is not None
    assert btc.mint == PublicKey("9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E")
    eth = actual.find_by_symbol("ETH")
    assert eth is not None
    assert eth.mint == PublicKey("2FPyTwcZLUg1MDrwsyoP4D6s1tM7hAkHYRjkNb5w6Pxk")
    srm = actual.find_by_mint(PublicKey("AKJHspCwDhABucCxNLXUSfEzb7Ny62RqFtC9uNjJi4fq"))
    assert srm is not None
    assert srm.symbol == "SRM-SOL"
    usdt = actual.find_by_mint(PublicKey("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"))
    assert usdt is not None
    assert usdt.symbol == "USDT"