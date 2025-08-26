import json
from Algorithm import Algorithm

class SimpleTestAlgorithm(Algorithm):
    def __init__(self):
        super().__init__("SimpleTestAlgorithm")
        self.last_price = 0.0
        
    def get_options_schema(self) -> str:
        schema = {
            "title": "Simple Test Algorithm",
            "description": "A basic test algorithm for validation",
            "type": "object",
            "properties": {
                "test_parameter": {
                    "type": "number",
                    "title": "Test Parameter",
                    "description": "A test parameter",
                    "default": 100.0
                },
                "symbol": {
                    "type": "string", 
                    "title": "Trading Symbol",
                    "description": "Symbol to trade",
                    "default": "BTCUSD"
                }
            }
        }
        return json.dumps(schema)
    
    async def start(self, options):
        print(f"SimpleTestAlgorithm starting with options: {options}")
        await super().start(options)
        
        # Subscribe to symbol data if we have a symbol
        if 'symbol' in options:
            symbol = options['symbol']
            print(f"Would subscribe to {symbol}")
            # Example: await self.subscribe_symbol(symbol, exchange, depth_levels=10)
        
        return True
    
    def stop(self):
        print("SimpleTestAlgorithm stopped")
        
    def pause(self):
        print("SimpleTestAlgorithm paused")
        
    def resume(self):
        print("SimpleTestAlgorithm resumed")
    
    def process_candle(self, candles):
        print(f"Received {len(candles)} candlesticks")
        for candle in candles:
            print(f"Candle: {candle.symbol} O:{candle.open} H:{candle.high} L:{candle.low} C:{candle.close}")
            self.last_price = candle.close
        return None
    
    def process_trade(self, trades):
        print(f"Received {len(trades)} trades")
        for trade in trades:
            print(f"Trade: {trade.symbol} Price:{trade.price} Qty:{trade.quantity}")
            self.last_price = trade.price
        return None
    
    def process_dob(self, depth_data):
        print(f"Received {len(depth_data)} depth of book updates")
        for dob in depth_data:
            print(f"DOB: {dob.symbol} Bids:{len(dob.bidLevels)} Offers:{len(dob.offerLevels)}")
        return None
    
    def process_order_status(self, order_status):
        print(f"Order status update: {order_status.orderId} Status:{order_status.status}")

# Create algorithm instance
algorithm = SimpleTestAlgorithm()
