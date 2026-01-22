import datetime
from pickle import FALSE
import statistics
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from Indicator import Indicator

logger = logging.getLogger(__name__)

class StochasticOscillator(Indicator):
    """Stochastic Oscillator indicator implementation"""
    
    def __init__(self):
        super().__init__("Stochastic Oscillator")
        self.period = 5  # Default Stochastic period
        self.historical_candles = []  # Store historical closing prices
        self.up_color = (0, 255, 0)  # Default up color (green)
        self.down_color = (255, 0, 0) # Default down color (red)
        self.default_color = (128, 128, 255)

    def get_options_schema(self) -> str:
        """Return JSON schema for the options panel"""
        schema = {
            "title": "Stochastic Oscillator",
            "description": "Calculates the Stochastic Oscillator of closing prices",
            "properties": {
                "period": {
                    "title": "Period",
                    "description": "Number of periods to include in the Stochastic calculation",
                    "type": "integer",
                    "options": "1 .. 200",
                    "value": 5
                },
                "upperBand": {
                    "title": "Upper Band",
                    "description": "Upper band threshold",
                    "type": "integer",
                    "options": "0 .. 100",
                    "value": 70
                },
                "upperBandColor": {
                    "title": "Upper Band Color",
                    "description": "Color when RSI exceeds upper band",
                    "type": "string",
                    "options": "R, G, B: (0..255, 0..255, 0..255)",
                    "value": "0, 255, 0"
                },
                "lowerBand": {
                    "title": "Lower Band",
                    "description": "Lower band threshold",
                    "type": "integer",
                    "options": "0 .. 100",
                    "value": 30
                },
                "lowerBandColor": {
                    "title": "Lower Band Color",
                    "description": "Color when RSI falls below lower band",
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
        
        self.historical_candles = []

        props = options['properties']
        logger.info(f"Stochastic Oscillator started with properties: {props}")
        self.period = props['period']['value']
        self.upperBand = props['upperBand']['value']
        self.lowerBand = props['lowerBand']['value']
        self.upperBand_color = self.parse_color(props['upperBandColor']['value'])
        self.lowerBand_color = self.parse_color(props['lowerBandColor']['value'])
        self.default_color = self.parse_color(props['defaultColor']['value'])
        
        # Process historical data
        for candle in historical_data:
            result = self.process([candle])
        
        return True

    def stop(self):
        super().stop()
        """Cleanup resources"""
        logger.info("SMAIndicator stopped.")

    def _calculate_stochastic(self) -> float:
        """Calculate SMA values based on current prices"""
        # Need at least sma_period prices to calculate SMA
        if len(self.historical_candles) < self.period:
            return

        # Get high and low from window
        window = self.historical_candles[-self.period:]
        low = min(candle['low'] for candle in window)
        high = max(candle['high'] for candle in window)

        if high == low:
            return 0

        # Calculate Stochastic Oscillator
        latest_stoch = (window[-1]['close'] - low) / (high - low) * 100
        return latest_stoch

    def process(self, candles: List[Dict]) -> Optional[Dict]:
        """Process new price data and return updated indicator values"""
        if not candles or len(candles) == 0:
            return None
        
        # Get the latest candlestick
        latest_candle = candles[0]
        valid_stoch = True
        latest_stoch = 50
        color = self.default_color

        # Keep only the needed history (sma_period + some extra)
        max_history = max(self.period * 3, 100)
        if len(self.historical_candles) > max_history:
            self.historical_candles = self.historical_candles[-max_history:]
        elif len(self.historical_candles) < self.period:
            # Not enough data to calculate SMA
            logger.warning(f"Not enough historical prices to calculate SMA. Need at least {self.period} prices.")
            valid_stoch = False

        # Get timestamp from the candle
        dt = latest_candle['timestamp'] or datetime.datetime.now(datetime.timezone.utc)
        
        last_datapoint_id = self.next_datapoint_id - 1
        start_ts = latest_candle.get('start_time', dt)
        end_ts = latest_candle.get('end_time', dt)
        datapoint_id = self.get_datapoint_id(start_ts, end_ts)
        
        newResult = last_datapoint_id != datapoint_id
        if newResult:
            self.historical_candles.append(latest_candle)
        else:
            self.historical_candles[-1]["close"] = latest_candle["close"]  # Update the last candle if same datapoint_id

        if valid_stoch:
            # Recalculate Stochastic Oscillator
            latest_stoch = self._calculate_stochastic()
            logger.debug(f"Calculated Stochastic Oscillator: {latest_stoch} for period {self.period}")
            # Compare with the previous historical result's Stochastic value, not rsi_values array
            if len(self.historical_results) > 0:
                if latest_stoch >= self.upperBand:
                    logger.debug(f"Stochastic {latest_stoch} exceeds upper band {self.upperBand}")
                    color = self.upperBand_color
                elif latest_stoch <= self.lowerBand:
                    logger.debug(f"Stochastic {latest_stoch} falls below lower band {self.lowerBand}")
                    color = self.lowerBand_color
        
        if valid_stoch == False:
            logger.warning(f"Invalid Stochastic value. Default color and close price will be used.")

        # Return the indicator data
        result = {
            'label': f"Stochastic({self.period})",
            'timestamp': dt,
            'type': 2,  # LINE
            'value': latest_stoch,
            'r': color[0],
            'g': color[1],
            'b': color[2],
            'start_time': start_ts,
            'end_time': end_ts,
            'dataPointId': datapoint_id
        }

        if last_datapoint_id <= 0 or newResult or valid_stoch == False:
            self.historical_results.append(result)
            logger.debug(f"New SMA result added: {result}")

        return result
# Create an instance of the indicator for the module
indicator = StochasticOscillator()

# Expose the methods at the module level for backward compatibility
get_options_schema = indicator.get_options_schema
start = indicator.start
process = indicator.process
get_historical_results = indicator.get_historical_results




