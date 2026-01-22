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
        self.message_id = 0
        self.awaiting_cancel = False
        self.awaiting_open = False
        self.existing_balance = 0.0

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
        self.awaiting_cancel = False
        self.awaiting_open = False
        self.existing_balance = 0.0

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
                    "value": "BNB-USD"
                },
                "exchange": 
                {
                    "title": "Exchange",
                    "description": "The exchange to use for trading.",
                    "options": "Any valid exchange.",
                    "type": "string", 
                    "value": "BinanceUS"
               },
               "existing_balance":
               {
                   "title": "Starting Balance",
                   "description": "Starting balance of the asset. The algorithm will immediately attempt to sell this balance.",
                   "options": "0...Account Balance",
                   "type": "number",
                   "value": 0.0
               },
               "order_ttk": 
               {
                    "title": "Order TTK",
                    "description": "The time to keep orders in the book in seconds.",
                    "type": "integer", 
                    "options": "1 .. 1000", 
                    "value": 3
                },
                "order_quantity": 
                {
                    "title": "Order Quantity",
                    "description": "The quantity of each order.",
                    "type": "number", 
                    "options": "0 .. Account Balance", 
                    "value": 0.01
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
        self.existing_balance = props['existing_balance']['value']

        exchanges = self.exchanges.split(",") if isinstance(self.exchanges, str) else self.exchanges

        for exchange in exchanges:
            subscribe_result = self.subscribe_symbol(self.symbol, exchange, get_historical=True)
            if not subscribe_result.get("success", False):
                self.logger.error(f"Failed to subscribe symbol: {subscribe_result.get('reason', '')}")
                return False
        return True

    def place_order(self, side: str, price: float, qty: Optional[float] = None):
        # Place order via the interface
        if not self.interface:
            self.logger.error("Interface not set. Cannot place order.")
            return
        self.message_id += 1
        
        exchange = self.exchanges[0] if isinstance(self.exchanges, list) else self.exchanges
        order_qty = qty if qty is not None else self.order_quantity
        response = self.interface.send_order(self.symbol, exchange, price, order_qty, side, "limit", self.message_id)
        if response is None:
            self.logger.error(f"Failed to place {side} order at {price}: Paused or invalid state")
        elif not response.result == 1:
            self.logger.error(f"Failed to place {side} order at {price}: {response.reason}")
            return
        self.current_order = { "id": response.orderId, "side": side, "price": price, "filled_quantity": 0, "quantity": self.order_quantity, "timestamp": datetime.datetime.utcnow()}
        self.logger.info(f"Placing {side} order at {price} for {self.order_quantity} {self.symbol}")
        self.awaiting_open = False

    def on_order_partial_filled(self, order_id: str, filled_quantity: float, filled_price: float, side: str):
        self.existing_balance += filled_quantity if side == "buy_open" else -filled_quantity
        self.logger.info(f"Order {order_id} partially filled at {filled_price} for {filled_quantity} {self.symbol}")
        if side == "buy_open":
            self.awaiting_cancel = True
            self.cancel_order(order_id)

    def on_order_filled(self, order_id: str, filled_quantity: float, filled_price: float, side: str):
        self.logger.info(f"Order {order_id} filled at {filled_price} for {filled_quantity} {self.symbol}")
        self.existing_balance += filled_quantity if side == "buy_open" else -filled_quantity
        # When an order is filled, place a new order closing the existing balance or opening a new buy order
        self.current_order = None
        self.awaiting_cancel = False

    def process_order_status(self, order_status):
        """Process order status updates"""
        if self.current_order["id"] != order_status.orderId:
            return
        self.logger.info(f"Processing order status update: {order_status}")
        if order_status.status == algos_pb2.OrderStatus.ORDER_STATUS_PARTIAL_FILLED:
            self.on_order_partial_filled(order_status.orderId, order_status.filledQuantity, self.current_order["price"], self.current_order["side"])
        if order_status.status == algos_pb2.OrderStatus.ORDER_STATUS_FILLED:
            self.on_order_filled(order_status.orderId, order_status.filledQuantity, self.current_order["price"], self.current_order["side"])
        elif order_status.status == algos_pb2.OrderStatus.ORDER_STATUS_CANCELLED:
            self.logger.info(f"Order {order_status.orderId} canceled.")
            self.awaiting_cancel = False
            self.current_order = None

    def open_new_order(self):
        self.awaiting_open = True
        self.logger.info(f"Opening new order. Existing balance: {self.existing_balance}")
        # If we have an existing balance, attempt to close it.
        if self.existing_balance > 0:
            # Place a sell order for the existing balance
            self.place_order("sell_close", self.dob.offerLevels[0].price, self.existing_balance)
        else:
            # Place a buy order at the best bid level
            self.place_order("buy_open", self.dob.bidLevels[0].price)

    def process_dob(self, book):
        super().process_dob(book)
        self.dob = book
        # if we're through the historical data, we can start placing orders
        if book.historical == False:
            self.logger.info("Processing live depth of book data")
            self.logger.info(f"Current book: {book.symbol} on {book.exchange}: {book.bidLevels[0].price} / {book.offerLevels[0].price}")
            self.logger.info(f"Awaiting Open: {self.awaiting_open}, Awaiting Cancel: {self.awaiting_cancel}, Current Order: {self.current_order}")
            if not self.awaiting_open and not self.awaiting_cancel:
                if self.current_order is None:
                    self.open_new_order()
                elif self.current_order["timestamp"] + datetime.timedelta(seconds=self.order_ttk) < datetime.datetime.utcnow():
                    self.awaiting_cancel = True
                    self.cancel_order(self.current_order["id"])
# Create an instance of the GridTrader algorithm
# This allows the script to be run directly or imported without executing the algorithm
indicator = ScalpBot()
get_options_schema = indicator.get_options_schema
start = indicator.start