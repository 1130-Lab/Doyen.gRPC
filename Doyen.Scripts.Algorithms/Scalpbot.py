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
        self.symbol = None
        self.exchanges = None
        self.order_quantity = 0.0
        self.order_ttk = 10
        self.current_order = None
        self.dob = None

    def get_display_name(self) -> str:
        return "Scalpbot Algorithm"

    def get_description(self) -> str:
        return "A scalping algorithm that places buy orders near bid levels and attempts to close near the offer."

    def get_version(self) -> str:
        return "1.0.0"

    def get_author(self) -> str:
        return "Doyen @ 1130 Lab"

    def get_tags(self) -> List[str]:
        return ["grid", "trading", "automated", "volatility", "market-making"]

    def refresh(self):
        """Refresh the algorithm state."""
        self.symbol = None
        self.exchanges = None
        self.order_quantity = 0.0
        self.order_ttk = 10
        self.current_order = None
        self.dob = None

    def get_options_schema(self) -> str:
        schema = {
            "title": self.name,
            "description": "Simple scalping bot.",
            "properties": {
                "symbol": 
                { 
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
                    "value": "BinanceUS"
               },
               "order_ttk": 
               {
                    "title": "Order TTK",
                    "description": "The time to keep orders in the book in seconds.",
                    "type": "integer", 
                    "options": "1 .. 1000", 
                    "value": 10
                },
                "order_quantity": 
                {
                    "title": "Order Quantity",
                    "description": "The quantity of each order.",
                    "type": "number", 
                    "options": "0 .. Account Balance", 
                    "value": 0.0001
                }
            }
        }
        return json.dumps(schema)

    def start(self, options: Dict[str, Any]) -> bool:
        super().start(options)
        self.refresh()
        props = options['properties']
        self.symbol = props['symbol']['value']
        self.exchanges = props['exchange']['value']        
        self.order_ttk = props["order_ttk"]['value']
        self.order_quantity = props['order_quantity']['value']

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
        self.message_id += 1
        
        exchange = self.exchanges[0] if isinstance(self.exchanges, list) else self.exchanges
        response = self.interface.send_order(self.symbol, exchange, price, self.order_quantity, side, "limit", self.message_id)
        if response is None:
            print(f"Failed to place {side} order at {price}: Paused or invalid state")
        elif not response.success:
            print(f"Failed to place {side} order at {price}: {response.reason}")
            return
        self.current_orders = { "id": response.orderId, "side": side, "price": price, "filled_quantity": 0, "quantity": self.order_quantity, "timestamp": datetime.datetime.utcnow()}
        print(f"Placing {side} order at {price} for {self.order_quantity} {self.symbol}")

    def on_order_filled(self, order_id: str, filled_quantity: float, filled_price: float, side: str):
        # When an order is filled, place a new order on the opposite side at the next grid level
        if self.current_order == None:
            if(filled_quantity >= self.order_quantity):
                if side == "buy_open":
                    self.place_order("sell_close", self.dob.offerLevels[0].price)
                elif side == "sell_close":
                    self.current_order = None
            else:
                self.current_order["filled_quantity"] += filled_quantity
                print(f"Order {order_id} partially filled: {self.current_order['filled_quantity']} / {self.current_order['quantity']}")

    def process_order_status(self, order_status):
        """Process order status updates"""
        if order_status.status == algos_pb2.OrderStatus.ORDER_STATUS_FILLED or order_status.status == algos_pb2.OrderStatus.ORDER_STATUS_PARTIALLY_FILLED:
            order_id = order_status.orderId
            if order_id == self.current_order["id"]:                
                self.on_order_filled(order_id, self.current_order["filled_quantity"], self.current_order["price"], self.current_order["side"])

    def process_dob(self, book):
        super().process_dob(book)
        self.dob = book
        # if we're through the historical data, we can start placing orders
        if book.historical == False:
            print("Processing live depth of book data")
            print(f"Current book: {book.symbol} on {book.exchange}: {book.bidLevels[0].price} / {book.offerLevels[0].price}")
            if self.current_order is None:
                # Place a buy order at the best bid level
                self.place_order("buy_open", book.bidLevels[0].price)
            elif self.current_order["timestamp"] + datetime.timedelta(seconds=self.order_ttk) < datetime.datetime.utcnow():
                if self.place_order["filled_quantity"] > 0:
                    if self.current_order["side"] == "buy_open":
                        self.place_order("sell_close", book.offerLevels[0].price)
                self.cancel_order(self.current_order["id"])
# Create an instance of the GridTrader algorithm
# This allows the script to be run directly or imported without executing the algorithm
indicator = ScalpBot()
get_options_schema = indicator.get_options_schema
start = indicator.start