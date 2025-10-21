import datetime
import json
from typing import Dict, List, Optional, Any
from Algorithm import Algorithm
import algos_pb2
import algos_pb2_grpc

class ScalpBot(Algorithm):
    """Spread trading bot using gRPC protocol."""
    def __init__(self):
        super().__init__("Scalpbot")
        self.grid_orders = {}
        self.grid_levels = []
        self.symbol = None
        self.exchanges = None
        self.order_quantity = 0.0
        self.upperDelta = 0,0
        self.lowerDelta = 0,0
        self.lowerPrice = 0.0
        self.upperPrice = 0.0
        self.grid_count = 10

    def get_display_name(self) -> str:
        return "Scalpbot Algorithm"

    def get_description(self) -> str:
        return "A scalping algorithm that places buy orders near bid levels and attempts to close near the offer."

    def get_version(self) -> str:
        return "2.0.1"

    def get_author(self) -> str:
        return "Doyen @ 1130 Lab"

    def get_tags(self) -> List[str]:
        return ["grid", "trading", "automated", "volatility", "market-making"]

    def refresh(self):
        """Refresh the algorithm state."""
        self.order = {}
        self.symbol = None
        self.exchanges = None
        self.order_quantity = 0.0
        self.upperDelta = 0,0
        self.lowerDelta = 0,0
        self.lowerPrice = 0.0
        self.upperPrice = 0.0
        self.grid_count = 10

    def get_options_schema(self) -> str:
        schema = {
            "title": self.name,
            "description": "Simple grid trading bot.",
            "properties": {
                "symbol": { 
                    "title": "Symbols", 
                    "description": "Comma-separated symbols to trade. (e.g BTCUSDT, ETHUSDT)", 
                    "type": "string", 
                    "options": "Any valid trading symbol.",
                    "value": "BTC-USDT"
                },
                "exchange": 
                {
                    "title": "Exchange",
                    "description": "The exchange to use for trading.",
                    "options": "Any valid exchange.",
                    "type": "string", 
                    "value": "BinanceUS"},
                "offer_threshold": {
                    "title": "Offer Threshold",
                    "description": "The threshold for grid levels relative to the offer in dollars. ex. 50 for a pair offered at $100,000 would make our best bid price $99,950.",
                    "options": "0.0 .. 1000",
                    "type": "number", "value": 50},
                "order_ttk": {
                    "title": "Order TTK",
                    "description": "The time to keep orders in the book in seconds.",
                    "type": "integer", 
                    "options": "1 .. 1000", 
                    "value": 10},
                "order_quantity": {
                    "title": "Order Quantity",
                    "description": "The quantity of each order.",
                    "type": "number", 
                    "options": "0 .. Account Balance", 
                    "value": 0.0001}
            }
        }
        return json.dumps(schema)

    def start(self, options: Dict[str, Any]) -> bool:
        super().start(options)
        self.refresh()
        props = options['properties']
        self.symbol = props['symbol']['value']
        self.exchanges = props['exchange']['value']
        self.lowerDelta = float(props['lower_price']['value'])
        self.upperDelta = float(props['upper_price']['value'])
        self.grid_count = int(props['grid_count']['value'])
        self.order_quantity = float(props['order_quantity']['value'])
        self.offer_threshold = float(props['offer_threshold']['value'])

        exchanges = self.exchanges.split(",") if isinstance(self.exchanges, str) else self.exchanges

        for exchange in exchanges:
            subscribe_result = self.subscribe_symbol(self.symbol, exchange, get_historical=True)
            if not subscribe_result.get("success", False):
                print(f"Failed to subscribe symbol: {subscribe_result.get('reason', '')}")
                return False
        return True

    def place_order(self, side: str, price: float):
        # Place order via the interface
        if not self.interface:
            print("Interface not set. Cannot place order.")
            return
        import time
        message_id = int(time.time() * 1000000)
        
        exchange = self.exchanges[0] if isinstance(self.exchanges, list) else self.exchanges
        response = self.interface.send_order(self.symbol, exchange, price, self.order_quantity, side, "limit", message_id)
        if response is None:
            print(f"Failed to place {side} order at {price}: Paused or invalid state")
        elif not response.success:
            print(f"Failed to place {side} order at {price}: {response.reason}")
            return
        self.orders[response.orderId] = {"side": side, "price": price, "quantity": self.order_quantity}
        print(f"Placing {side} order at {price} for {self.order_quantity} {self.symbol}")
        self.grid_orders[response.orderId] = {"side": side, "price": price}

    def on_order_filled(self, order_id: str, filled_price: float, side: str):
        # When an order is filled, place a new order on the opposite side at the next grid level
        if side == "buy_open":
            next_level = min([lvl for lvl in self.grid_levels if lvl > filled_price], default=None)
            if next_level:
                self.place_order("sell_close", next_level)
        elif side == "sell_close":
            next_level = max([lvl for lvl in self.grid_levels if lvl < filled_price], default=None)
            if next_level:
                self.place_order("buy_open", next_level)

    def process_order_status(self, order_status):
        """Process order status updates"""
        if(order_status.status == algos_pb2.OrderStatus.ORDER_STATUS_FILLED):
            order_id = order_status.orderId
            if order_id in self.grid_orders:
                order_info = self.grid_orders[order_id]
                filled_price = order_info['price']
                side = order_info['side']
                print(f"Order {order_id} filled at {filled_price} for {side}")
                # Trigger the on_order_filled logic
                self.on_order_filled(order_id, filled_price, side)
            else:
                print(f"Received filled status for unknown order: {order_id}")

    def process_dob(self, book):
        super().process_dob(book)
        # if we're through the historical data, we can start placing orders
        if book.historical == False:
            print("Processing live depth of book data")
            print(f"Current book: {book.symbol} on {book.exchange}: {book.bidLevels[0].price} / {book.offerLevels[0].price}")
            if not self.grid_orders:
                midpoint = (book.bidLevels[0].price + book.offerLevels[0].price) / 2
                print(f"Current midpoint price: {midpoint}")
                self.upperPrice = min(book.bidLevels[0].price * (1.0 + self.upperDelta), book.offerLevels[0].price - self.offer_threshold)
                self.lowerPrice = self.upperPrice * (1.0 - self.lowerDelta)
                # Calculate grid levels
                self.grid_levels = [self.lowerPrice + i * (self.upperPrice - self.lowerPrice) / (self.grid_count - 1) for i in range(self.grid_count)]
                print(f"Grid levels: {self.grid_levels}")
                # Place initial buy_open/sell_close orders at each grid level
                for i in range(self.grid_count // 2):
                    self.place_order("buy_open", self.grid_levels[i])
                print(f"Grid levels initialized: {self.grid_levels}")

# Create an instance of the GridTrader algorithm
# This allows the script to be run directly or imported without executing the algorithm
indicator = GridTrader()
get_options_schema = indicator.get_options_schema
start = indicator.start