import datetime
from pickle import FALSE
import statistics
import json
from typing import Dict, List, Optional, Any, Tuple
from Indicator import Indicator

class EMAIndicator(Indicator):
    """Simple Moving Average indicator implementation"""
    
    def __init__(self):
        super().__init__("Exponential Moving Average (EMA)")
        self.ema_period = 30  # Default EMA period
        self.smoothing = 2  # Default smoothing factor
        self.historical_prices = []  # Store historical closing prices
        self.up_color = (0, 255, 0)  # Default up color (green)
        self.down_color = (255, 0, 0) # Default down color (red)
        self.default_color = (128, 128, 255)

    def get_options_schema(self) -> str:
        """Return JSON schema for the options panel"""
        schema = {
            "title": "Exponential Moving Average",
            "description": "Calculates the exponential moving average of closing prices",
            "properties": {
                "period": {
                    "title": "Period",
                    "description": "Number of periods to include in the moving average",
                    "type": "integer",
                    "options": "1 .. 200",
                    "value": 12
                },
                "smoothing":{
                    "title": "Smoothing",
                    "description": "Smoothing factor for EMA calculation",
                    "type": "integer",
                    "options": "1 .. 200",
                    "value": 2
                },
                "upColor": {
                    "title": "Up Color",
                    "description": "Color for price increases",
                    "type": "string",
                    "options": "R, G, B: (0..255, 0..255, 0..255)",
                    "value": "0, 255, 0"
                },
                "downColor": {
                    "title": "Down Color",
                    "description": "Color for price decreases",
                    "type": "string",
                    "options": "R, G, B: (0..255, 0..255, 0..255)",
                    "value": "255, 0, 0"
                },
                "defaultColor": {
                    "title": "Default Color",
                    "description": "Color for invalid data or data preceding sufficent data to calculate the SMA.",
                    "type": "string",
                    "options": "R, G, B: (0..255, 0..255, 0..255)",
                    "value": "128, 128, 255"
                }
            }
        }
        return json.dumps(schema)

    def start(self, historical_data: List[Dict], options: Dict[str, Any]) -> bool:
        """Initialize the indicator with historical data and options"""
        # Call the parent method to store data
        super().start(historical_data, options)
        
        self.historical_prices = []

        props = options['properties']
        print(f"SMA indicator started with properties: {props}")
        self.ema_period = props['period']['value']
        self.up_color = self.parse_color(props['upColor']['value'])
        self.down_color = self.parse_color(props['downColor']['value'])
        self.default_color = self.parse_color(props['defaultColor']['value'])
        
        # Process historical data
        for candle in historical_data:
            result = self.process([candle])
        
        return True

    def stop(self):
        super().stop()
        """Cleanup resources"""
        print("SMAIndicator stopped.")

    def _calculate_ema(self) -> float:
        """Calculate EMA values based on current prices"""
        # Need at least ema_period prices to calculate EMA
        if len(self.historical_prices) < self.ema_period:
            return
        
        return self.historical_prices[-1] * (self.smoothing / (self.ema_period + 1)) + self.previous_ema * (1 - (self.smoothing / (self.ema_period + 1)))

    def process(self, candles: List[Dict]) -> Optional[Dict]:
        """Process new price data and return updated indicator values"""
        if not candles or len(candles) == 0:
            return None
        
        # Get the latest candlestick
        latest_candle = candles[0]
        close_price = latest_candle['close']
        
        valid_ema = True
        latest_ema = close_price
        color = self.default_color

        # Keep only the needed history (ema_period + some extra)
        max_history = max(self.ema_period * 3, 100)
        if len(self.historical_prices) > max_history:
            self.historical_prices = self.historical_prices[-max_history:]
        elif len(self.historical_prices) < self.ema_period:
            # Not enough data to calculate EMA
            print(f"Not enough historical prices to calculate EMA. Need at least {self.ema_period} prices.")
            valid_ema = False
        
        # Get timestamp from the candle
        dt = latest_candle['timestamp'] or datetime.datetime.now(datetime.timezone.utc)
        
        last_datapoint_id = self.next_datapoint_id - 1
        start_ts = latest_candle.get('start_time', dt)
        end_ts = latest_candle.get('end_time', dt)
        datapoint_id = self.get_datapoint_id(start_ts, end_ts)
        
        newResult = last_datapoint_id != datapoint_id
        if newResult:
            self.historical_prices.append(close_price)
        else:
            self.historical_prices[-1] = close_price  # Update the last price if same datapoint_id

        if valid_ema:            
            # Recalculate EMA
            latest_ema = self._calculate_ema()
            print(f"Calculated EMA: {latest_ema} for period {self.ema_period}")
            # Compare with the previous historical result's EMA value, not ema_values array
            if len(self.historical_results) > 0:
                previous_ema = self.historical_results[-1]['value']
                if latest_ema >= previous_ema:
                    print(f"EMA increased from {previous_ema} to {latest_ema}")
                    color = self.up_color
                else:
                    print(f"EMA decreased from {previous_ema} to {latest_ema}")
                    color = self.down_color
        
        if valid_ema == False:
            print(f"Invalid SMA value. Default color and close price will be used.")

        # Return the indicator data
        result = {
            'label': f"EMA({self.ema_period})",
            'timestamp': dt,
            'type': 2,  # LINE
            'value': latest_ema,
            'r': color[0],
            'g': color[1],
            'b': color[2],
            'start_time': start_ts,
            'end_time': end_ts,
            'dataPointId': datapoint_id
        }

        if last_datapoint_id <= 0 or newResult or valid_ema == False:
            self.historical_results.append(result)
            print(f"New EMA result added: {result}")

        return result
# Create an instance of the indicator for the module
indicator = EMAIndicator()

# Expose the methods at the module level for backward compatibility
get_options_schema = indicator.get_options_schema
start = indicator.start
process = indicator.process
get_historical_results = indicator.get_historical_results




