import asyncio
import uuid
import time
from typing import Any, Dict, List, Optional
from datetime import datetime
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog

logger = structlog.get_logger(__name__)

EXCHANGE_SEGMENTS = {
    "NSECM": 1,
    "NSEFO": 2,
    "NSECD": 3,
    "MCXFO": 4,
    "BSECM": 11,
    "BSEFO": 12,
}

EXCHANGE_SEGMENT_NAMES = {v: k for k, v in EXCHANGE_SEGMENTS.items()}


class XTSAPIError(Exception):
    def __init__(self, message: str, code: str = "", description: str = ""):
        super().__init__(message)
        self.code = code
        self.description = description


class RateLimiter:
    def __init__(self, calls_per_second: float):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()


class XTSMarketDataClient:
    def __init__(self, url: str, app_key: str, secret_key: str, source: str = "WebAPI"):
        self.url = url.rstrip("/")
        self.app_key = app_key
        self.secret_key = secret_key
        self.source = source
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._order_limiter = RateLimiter(10)
        self._query_limiter = RateLimiter(1)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["authorization"] = self.token
        return headers

    def _handle_response(self, resp: httpx.Response) -> Dict:
        if resp.is_error:
            logger.warning(
                "XTS API error response",
                status_code=resp.status_code,
                url=str(resp.url),
                body=resp.text[:500],
            )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("type") == "error":
            raise XTSAPIError(
                data.get("description", "API error"),
                code=data.get("code", ""),
                description=data.get("description", ""),
            )
        return data

    async def login(self) -> Dict:
        client = await self._get_client()
        payload = {"appKey": self.app_key, "secretKey": self.secret_key, "source": self.source}
        resp = await client.post(f"{self.url}/apimarketdata/auth/login", json=payload)
        data = self._handle_response(resp)
        result = data.get("result", data)
        self.token = result.get("token")
        self.user_id = result.get("userID")
        logger.info("XTS Market Data login successful", user_id=self.user_id)
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def get_master(self, exchange_segment_list: List[str]) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        payload = {"exchangeSegmentList": exchange_segment_list}
        resp = await client.post(
            f"{self.url}/apimarketdata/instruments/master",
            json=payload,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def get_option_symbol(
        self, exchange_segment: str, series: str, symbol: str,
        expiry_date: str, option_type: str, strike_price: float
    ) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        params = {
            "exchangeSegment": exchange_segment,
            "series": series,
            "symbol": symbol,
            "expiryDate": expiry_date,
            "optionType": option_type,
            "strikePrice": str(strike_price),
        }
        resp = await client.get(
            f"{self.url}/apimarketdata/instruments/instrument/optionsymbol",
            params=params,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def get_expiry_dates(self, exchange_segment: str, series: str, symbol: str) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        params = {"exchangeSegment": exchange_segment, "series": series, "symbol": symbol}
        resp = await client.get(
            f"{self.url}/apimarketdata/instruments/instrument/expiryDate",
            params=params,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def subscribe(self, instruments: List[Dict], xts_message_code: int) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        payload = {"instruments": instruments, "xtsMessageCode": xts_message_code}
        resp = await client.post(
            f"{self.url}/apimarketdata/instruments/subscription",
            json=payload,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def unsubscribe(self, instruments: List[Dict], xts_message_code: int) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        payload = {"instruments": instruments, "xtsMessageCode": xts_message_code}
        resp = await client.put(
            f"{self.url}/apimarketdata/instruments/subscription",
            json=payload,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def get_quotes(self, instruments: List[Dict]) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        # XTS quotes API requires exchangeSegment as an integer code, not a string name.
        converted = [
            {**inst, "exchangeSegment": EXCHANGE_SEGMENTS.get(inst["exchangeSegment"], inst["exchangeSegment"])}
            if isinstance(inst.get("exchangeSegment"), str)
            else inst
            for inst in instruments
        ]
        # xtsMessageCode 1502 = TouchlineData (LTP, bid, ask, volume, OI).
        # 1512 is a socket-only subscription code and is rejected by the REST endpoint.
        payload = {"instruments": converted, "xtsMessageCode": 1502}
        resp = await client.post(
            f"{self.url}/apimarketdata/instruments/quotes",
            json=payload,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def get_ohlc(
        self, exchange_segment: str, exchange_instrument_id: int,
        start_time: str, end_time: str, compression_value: int = 1
    ) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        params = {
            "exchangeSegment": exchange_segment,
            "exchangeInstrumentID": exchange_instrument_id,
            "startTime": start_time,
            "endTime": end_time,
            "compressionValue": compression_value,
        }
        resp = await client.get(
            f"{self.url}/apimarketdata/instruments/ohlc",
            params=params,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def search_instruments(self, exchange_segment: str, search_string: str) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        params = {"exchangeSegment": exchange_segment, "searchString": search_string}
        resp = await client.get(
            f"{self.url}/apimarketdata/search/instruments",
            params=params,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class XTSInteractiveClient:
    def __init__(self, url: str, app_key: str, secret_key: str, source: str = "WebAPI"):
        self.url = url.rstrip("/")
        self.app_key = app_key
        self.secret_key = secret_key
        self.source = source
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._order_limiter = RateLimiter(10)
        self._query_limiter = RateLimiter(1)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["authorization"] = self.token
        return headers

    def _handle_response(self, resp: httpx.Response) -> Dict:
        if resp.is_error:
            logger.warning(
                "XTS API error response",
                status_code=resp.status_code,
                url=str(resp.url),
                body=resp.text[:500],
            )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("type") == "error":
            raise XTSAPIError(
                data.get("description", "API error"),
                code=data.get("code", ""),
                description=data.get("description", ""),
            )
        return data

    def generate_order_unique_id(self) -> str:
        return str(uuid.uuid4()).replace("-", "")[:18]

    async def login(self) -> Dict:
        client = await self._get_client()
        payload = {"appKey": self.app_key, "secretKey": self.secret_key, "source": self.source}
        resp = await client.post(f"{self.url}/interactive/user/session", json=payload)
        data = self._handle_response(resp)
        result = data.get("result", data)
        self.token = result.get("token")
        self.user_id = result.get("userID")
        logger.info("XTS Interactive login successful", user_id=self.user_id)
        return result

    async def place_order(
        self, exchange_segment: str, exchange_instrument_id: int,
        product_type: str, order_type: str, order_side: str,
        time_in_force: str, disclosed_quantity: int, order_quantity: int,
        limit_price: float = 0.0, stop_price: float = 0.0,
        order_unique_identifier: Optional[str] = None,
    ) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        payload = {
            "exchangeSegment": exchange_segment,
            "exchangeInstrumentID": exchange_instrument_id,
            "productType": product_type,
            "orderType": order_type,
            "orderSide": order_side,
            "timeInForce": time_in_force,
            "disclosedQuantity": disclosed_quantity,
            "orderQuantity": order_quantity,
            "limitPrice": limit_price,
            "stopPrice": stop_price,
            "orderUniqueIdentifier": order_unique_identifier or self.generate_order_unique_id(),
        }
        resp = await client.post(f"{self.url}/interactive/orders", json=payload, headers=self._headers())
        return self._handle_response(resp)

    async def place_bracket_order(
        self, exchange_segment: str, exchange_instrument_id: int,
        order_side: str, order_quantity: int, limit_price: float,
        squareoff: float, stop_loss_price: float,
        trailing_stoploss: float = 0.0, product_type: str = "MIS",
        order_type: str = "LIMIT", time_in_force: str = "DAY",
        is_pro_order: bool = False,
        order_unique_identifier: Optional[str] = None,
    ) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        payload = {
            "exchangeSegment": exchange_segment,
            "exchangeInstrumentID": exchange_instrument_id,
            "orderSide": order_side,
            "orderQuantity": order_quantity,
            "limitPrice": limit_price,
            "squarOff": squareoff,
            "stopLossPrice": stop_loss_price,
            "trailingStoploss": trailing_stoploss,
            "productType": product_type,
            "orderType": order_type,
            "timeInForce": time_in_force,
            "isProOrder": is_pro_order,
            "orderUniqueIdentifier": order_unique_identifier or self.generate_order_unique_id(),
            "disclosedQuantity": 0,
        }
        resp = await client.post(f"{self.url}/interactive/orders/bracket", json=payload, headers=self._headers())
        return self._handle_response(resp)

    async def place_cover_order(
        self, exchange_segment: str, exchange_instrument_id: int,
        order_side: str, order_quantity: int, limit_price: float,
        stop_price: float, product_type: str = "MIS",
        order_type: str = "LIMIT", time_in_force: str = "DAY",
        order_unique_identifier: Optional[str] = None,
    ) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        payload = {
            "exchangeSegment": exchange_segment,
            "exchangeInstrumentID": exchange_instrument_id,
            "orderSide": order_side,
            "orderQuantity": order_quantity,
            "limitPrice": limit_price,
            "stopPrice": stop_price,
            "productType": product_type,
            "orderType": order_type,
            "timeInForce": time_in_force,
            "orderUniqueIdentifier": order_unique_identifier or self.generate_order_unique_id(),
            "disclosedQuantity": 0,
        }
        resp = await client.post(f"{self.url}/interactive/orders/cover", json=payload, headers=self._headers())
        return self._handle_response(resp)

    async def modify_order(self, app_order_id: str, **kwargs) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        payload = {"appOrderID": app_order_id, **kwargs}
        resp = await client.put(f"{self.url}/interactive/orders", json=payload, headers=self._headers())
        return self._handle_response(resp)

    async def cancel_order(self, app_order_id: str) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        params = {"appOrderID": app_order_id}
        resp = await client.delete(f"{self.url}/interactive/orders", params=params, headers=self._headers())
        return self._handle_response(resp)

    async def cancel_bracket_order(self, bo_entry_order_id: str) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        params = {"boEntryOrderId": bo_entry_order_id}
        resp = await client.delete(f"{self.url}/interactive/orders/bracket", params=params, headers=self._headers())
        return self._handle_response(resp)

    async def exit_cover_order(self, app_order_id: str) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        payload = {"appOrderID": app_order_id}
        resp = await client.put(f"{self.url}/interactive/orders/cover", json=payload, headers=self._headers())
        return self._handle_response(resp)

    async def cancel_all_orders(self) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        resp = await client.post(f"{self.url}/interactive/orders/cancelall", json={}, headers=self._headers())
        return self._handle_response(resp)

    async def squareoff_position(
        self, exchange_segment: str, exchange_instrument_id: int,
        product_type: str, squareoff_mode: str = "DayWise",
        position_squareoff_quantity_type: str = "ExactQty",
        squareoff_qty_value: int = 0,
        block_order_sending: bool = True,
        cancel_orders: bool = True,
    ) -> Dict:
        await self._order_limiter.acquire()
        client = await self._get_client()
        payload = {
            "exchangeSegment": exchange_segment,
            "exchangeInstrumentID": exchange_instrument_id,
            "productType": product_type,
            "squareoffMode": squareoff_mode,
            "positionSquareOffQuantityType": position_squareoff_quantity_type,
            "squareOffQtyValue": squareoff_qty_value,
            "blockOrderSending": block_order_sending,
            "cancelOrders": cancel_orders,
        }
        resp = await client.put(f"{self.url}/interactive/portfolio/squareoff", json=payload, headers=self._headers())
        return self._handle_response(resp)

    async def get_order_book(self, app_order_id: Optional[str] = None) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        params = {}
        if app_order_id:
            params["appOrderID"] = app_order_id
        resp = await client.get(f"{self.url}/interactive/orders", params=params, headers=self._headers())
        return self._handle_response(resp)

    async def get_trade_book(self) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        resp = await client.get(f"{self.url}/interactive/orders/trades", headers=self._headers())
        return self._handle_response(resp)

    async def get_positions(self, day_or_net: str = "NetWise") -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        params = {"dayOrNet": day_or_net}
        resp = await client.get(f"{self.url}/interactive/portfolio/positions", params=params, headers=self._headers())
        return self._handle_response(resp)

    async def get_balance(self) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        resp = await client.get(f"{self.url}/interactive/user/balance", headers=self._headers())
        return self._handle_response(resp)

    async def get_holdings(self) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        resp = await client.get(f"{self.url}/interactive/portfolio/holdings", headers=self._headers())
        return self._handle_response(resp)

    async def get_profile(self) -> Dict:
        await self._query_limiter.acquire()
        client = await self._get_client()
        resp = await client.get(f"{self.url}/interactive/user/profile", headers=self._headers())
        return self._handle_response(resp)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
