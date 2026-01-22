import datetime
from pickle import FALSE
import statistics
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from Indicator import Indicator

logger = logging.getLogger(__name__)

class EMAIndicator(Indicator):
    """MACD indicator implementation"""
    
    def __init__(self):
        super().__init__("Exponential Moving Average (EMA)")
        self.fast_ema_period = 12  # Default Fast EMA period
        self.slow_ema_period = 26  # Default Slow EMA period
        self.smoothing = 2  # Default smoothing factor
        self.historical_prices = []  # Store historical closing prices
        self.up_color = (0, 255, 0)  # Default up color (green)
        self.down_color = (255, 0, 0) # Default down color (red)
        self.default_color = (128, 128, 255)
        self.previous_fast_ema = None
        self.previous_slow_ema = None
        self.fast_smoothing_const = None
        self.slow_smoothing_const = None

    def get_options_schema(self) -> str:
        """Return JSON schema for the options panel"""
        schema = {
            "title": "MACD",
            "description": "Calculates the Moving Average Convergence Divergence (MACD) of closing prices",
            "properties": {
                "fastPeriod": {
                    "title": "Fast EMA Period",
                    "description": "Number of periods for the fast EMA",
                    "type": "integer",
                    "options": "1 .. 200",
                    "value": 12
                },
                "slowPeriod": {
                    "title": "Slow EMA Period",
                    "description": "Number of periods for the slow EMA",
                    "type": "integer",
                    "options": "1 .. 200",
                    "value": 26
                },
                "smoothing": {
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
                    "description": "Color for invalid data or data preceding sufficent data to calculate the EMA.",
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
        logger.info(f"MACD indicator started with properties: {props}")
        self.fast_ema_period = props['fastPeriod']['value']
        self.slow_ema_period = props['slowPeriod']['value']
        self.smoothing = props['smoothing']['value']
        self.up_color = self.parse_color(props['upColor']['value'])
        self.down_color = self.parse_color(props['downColor']['value'])
        self.default_color = self.parse_color(props['defaultColor']['value'])
        self.fast_smoothing_const = (1 - (self.smoothing / (self.fast_ema_period + 1)))
        self.slow_smoothing_const = (1 - (self.smoothing / (self.slow_ema_period + 1)))

        # Process historical data
        for candle in historical_data:
            result = self.process([candle])
        
        return True

    def stop(self):
        super().stop()
        """Cleanup resources"""
        logger.info("MACDIndicator stopped.")

    def _calculate_macd(self) -> float:
        """Calculate MACD values based on current prices"""
        fast_historical_ema = 0
        if self.previous_ema == None:
            fast_historical_ema = self.historical_prices[-1] * (1 - self.fast_smoothing_const)
        else:
            fast_historical_ema = self.previous_fast_ema * (1 - self.fast_smoothing_const)

        self.previous_fast_ema = fast_ema        
        fast_ema = self.historical_prices[-1] * self.fast_smoothing_const + fast_historical_ema
        
        slow_historical_ema = 0
        if self.previous_ema == None:
            slow_historical_ema = self.historical_prices[-1] * (1 - self.slow_smoothing_const)
        else:
            slow_historical_ema = self.previous_slow_ema * (1 - self.slow_smoothing_const)

        self.previous_slow_ema = slow_ema        
        slow_ema = self.historical_prices[-1] * self.slow_smoothing_const + slow_historical_ema


        return fast_ema - slow_ema
               

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
        max_history = max(self.slow_ema_period * 3, 100)
        if len(self.historical_prices) > max_history:
            self.historical_prices = self.historical_prices[-max_history:]
        elif len(self.historical_prices) < self.slow_ema_period:
            # Not enough data to calculate EMA
            logger.warning(f"Not enough historical prices to calculate EMA. Need at least {self.slow_ema_period} prices.")
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
            
            if self.previous_ema != None:
                if latest_ema > self.previous_ema:
                    logger.debug(f"EMA increased from {self.previous_ema } to {latest_ema}")
                    color = self.up_color
                elif latest_ema < self.previous_ema:
                    logger.debug(f"EMA decreased from {self.previous_ema } to {latest_ema}")
                    color = self.down_color

            self.previous_ema  = latest_ema            
            logger.debug(f"Calculated EMA: {latest_ema} for period {self.fast_ema_period}")

        else:
            logger.warning(f"Invalid EMA value. Default color and close price will be used.")

        # Return the indicator data
        result = {
            'label': f"MACD({self.fast_ema_period}-{self.slow_ema_period})",
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

        if last_datapoint_id <= 0 or newResult or valid_ema:
            self.historical_results.append(result)
            logger.debug(f"New EMA result added: {result}")

        return result
# Create an instance of the indicator for the module
indicator = EMAIndicator()

# Expose the methods at the module level for backward compatibility
get_options_schema = indicator.get_options_schema
start = indicator.start
process = indicator.process
get_historical_results = indicator.get_historical_results




