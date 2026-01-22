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
        self.logger.info(f"SimpleTestAlgorithm starting with options: {options}")
        await super().start(options)
        
        # Subscribe to symbol data if we have a symbol
        if 'symbol' in options:
            symbol = options['symbol']
            self.logger.info(f"Would subscribe to {symbol}")
            # Example: await self.subscribe_symbol(symbol, exchange, depth_levels=10)
        
        return True
    
    def stop(self):
        self.logger.info("SimpleTestAlgorithm stopped")
        
    def pause(self):
        self.logger.info("SimpleTestAlgorithm paused")
        
    def resume(self):
        self.logger.info("SimpleTestAlgorithm resumed")
    
    def process_candle(self, candles):
        self.logger.info(f"Received {len(candles)} candlesticks")
        for candle in candles:
            self.logger.info(f"Candle: {candle.symbol} O:{candle.open} H:{candle.high} L:{candle.low} C:{candle.close}")
            self.last_price = candle.close
        return None
    
    def process_trade(self, trades):
        self.logger.info(f"Received {len(trades)} trades")
        for trade in trades:
            self.logger.info(f"Trade: {trade.symbol} Price:{trade.price} Qty:{trade.quantity}")
            self.last_price = trade.price
        return None
    
    def process_dob(self, depth_data):
        self.logger.info(f"Received {len(depth_data)} depth of book updates")
        for dob in depth_data:
            self.logger.info(f"DOB: {dob.symbol} Bids:{len(dob.bidLevels)} Offers:{len(dob.offerLevels)}")
        return None
    
    def process_order_status(self, order_status):
        self.logger.info(f"Order status update: {order_status.orderId} Status:{order_status.status}")

# Create algorithm instance
algorithm = SimpleTestAlgorithm()
