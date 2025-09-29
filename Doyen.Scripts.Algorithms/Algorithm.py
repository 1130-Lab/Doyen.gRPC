import json
from typing import Dict, List, Optional, Any
import algos_pb2
import algos_pb2_grpc

class Algorithm:
    """Base class for all algorithms"""
    def __init__(self, name: str = "",simulated=True):
        self.name = name
        self.interface = None  # Will be set by ScriptManager
        self.algo_id = "base_algorithm"
        self.options = {}
        self.historical_candles = []
        self.historical_dob = []
        self.historical_trades = []
        self.orders = {}
        self.simulated = simulated
        # Doyen will prevent the algorithm from sending orders while paused.
        self.paused = False # this isn't necessary but it's cleaner to handle pause/resume logic. 

    def get_display_name(self) -> str:
        """Get the display name for the algorithm (human-readable)"""
        return self.name

    def get_description(self) -> str:
        """Get the description of the algorithm"""
        return "A trading algorithm"

    def get_version(self) -> str:
        """Get the version of the algorithm"""
        return "1.0.0"

    def get_author(self) -> str:
        """Get the author of the algorithm"""
        return "Unknown"

    def get_tags(self) -> List[str]:
        """Get tags/categories for the algorithm"""
        return ["trading"]

    def get_options_schema(self) -> str:
        """Get the options schema JSON for the algorithm's configuration panel"""
        schema = {
            "title": self.name,
            "description": "Base algorithm",
            "properties": {
                ""
                }
        }
        return json.dumps(schema)
    
    def start(self, options: Dict[str, Any]) -> bool:
        # Initialize historical results and datapoint tracking
        self.historical_candles = []
        self.historical_dob = []
        self.historical_trades = []
        self.options = options
        self.orders = {}
        return True
    
    def pause(self):
        """Called when algorithm is paused"""
        self.paused = True
        print(f"{self.name} algorithm paused")

    def resume(self):
        """Called when algorithm is resumed"""
        self.paused = False
        print(f"{self.name} algorithm resumed")

    def stop(self):
        """Stop the algorithm and clean up resources"""
        pass
        
    def process_trade(self, trade):
        """Process incoming trade data"""
        return None

    def process_dob(self, book):
        """Process incoming depth of book data"""
        return None

    def process_candle(self, candle):
        """Process incoming candlestick data"""
        return None
        
    def process_order_status(self, order_status):
        """Process order status updates"""
        pass

    def send_order(self, symbol: str, exchange : str, price: float, quantity: float, message_id: Optional[int] = None):
        """Send an order through the interface"""
        if self.paused:
            print(f"Error: Algorithm {self.name} is paused. Order prevented.")
            return None
        if not self.interface:
            print("Error: No interface connection available")
            return None
        if message_id is None:
            import time
            message_id = int(time.time() * 1000000)  # Use timestamp as message ID
        try:
            # Use the interface method which handles protobuf creation
            response = self.interface.send_order(symbol, exchange, price, quantity, message_id, self.simulated)
            return response
        except Exception as e:
            print(f"Error sending order: {e}")
            return None

    def cancel_order(self, order_id: str, message_id: Optional[int] = None):
        """Cancel an order through the interface"""
        if not self.interface:
            print("Error: No interface connection available")
            return None
        if message_id is None:
            import time
            message_id = int(time.time() * 1000000)
        try:
            # Use the interface method which handles protobuf creation
            response = self.interface.cancel_order(order_id, message_id, self.simulated)
            return response
        except Exception as e:
            print(f"Error cancelling order: {e}")
            return None

    def subscribe_symbol(self, symbol: str, exchange: str, get_historical: bool = False, depth_levels: int = 10, candles_timeframe: int = 2):
        """Subscribe to symbol data through the interface
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSD")
            exchange: Exchange name (e.g., "BINANCEUS", "COINBASE")
            get_historical: Whether to request historical data
            depth_levels: Number of depth levels for order book
            candles_timeframe: Timeframe for candles (2 = FIVE_MINUTES, 1 = ONE_MINUTE, etc.)
        """
        if not self.interface:
            print("Error: No interface connection available")
            return None
        try:
            # Use the interface method which handles protobuf creation
            response = self.interface.subscribe_symbol(symbol, exchange, get_historical, depth_levels, candles_timeframe)
            return response
        except Exception as e:
            print(f"Error subscribing to symbol: {e}")
            return None