"""
Debug script for get_spot_price (and any InstrumentManager method).
Run via VS Code: select "Debug get_spot_price" in the Run & Debug panel and press F5.
Set breakpoints anywhere in instrument_manager.py or xts_client.py before running.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from core.xts_client import XTSMarketDataClient
from engine.instrument_manager import InstrumentManager


async def main():
    client = XTSMarketDataClient(
        url=os.getenv("XTS_MARKET_DATA_URL"),
        app_key=os.getenv("XTS_MARKET_DATA_KEY"),
        secret_key=os.getenv("XTS_MARKET_DATA_SECRET"),
        verify_ssl=os.getenv("XTS_VERIFY_SSL", "true").lower() != "false",
    )
    await client.login()

    im = InstrumentManager(client)

    # ── set a breakpoint on any line below ──────────────────────────────────
    for symbol in ["NIFTY", "BANKNIFTY"]:
        price = await im.get_spot_price(symbol)   # <-- breakpoint here
        print(f"{symbol} spot price: {price}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
