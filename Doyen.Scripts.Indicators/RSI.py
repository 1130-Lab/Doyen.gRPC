import datetime
from pickle import FALSE
from re import S
import statistics
import json
from typing import Dict, List, Optional, Any, Tuple
from Indicator import Indicator

class RSIIndicator(Indicator):
    """Relative Strength Index indicator implementation"""
    
    def __init__(self):
        super().__init__("Relative Strength Index (RSI)")
        self.rsi_period = 14  # Default RSI period
        self.historical_candles = []  # Store historical closing prices
        self.upperBand = 70.0  # Default upper band
        self.lowerBand = 30.0  # Default lower band
        self.upperBand_color = (0, 255, 0)  # Default upper band color (green)
        self.lowerBand_color = (255, 0, 0) # Default lower band color (red)
        self.default_color = (128, 128, 255)

    def get_options_schema(self) -> str:
        """Return JSON schema for the options panel"""
        schema = {
            "title": "Relative Strength Index",
            "description": "Calculates the relative strength index of closing prices",
            "properties": {
                "period": {
                    "title": "Period",
                    "description": "Number of periods to include in the moving average",
                    "type": "integer",
                    "options": "1 .. 200",
                    "value": 14
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
        print(f"RSI indicator started with properties: {props}")
        self.rsi_period = props['period']['value']
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
        print("SMAIndicator stopped.")

    def _calculate_rsi(self) -> float:
        """Calculate SMA values based on current prices"""
        # Need at least sma_period prices to calculate SMA
        if len(self.historical_candles) < self.rsi_period:
            return

        # Calculate RSI for each window of prices
        window = self.historical_candles[-self.rsi_period:]
        gains = []
        losses = []
        for price in window:
            if price["open"] > price["close"]:
                losses.append(price["open"] - price["close"])
            elif price["close"] > price["open"]:
                gains.append(price["close"] - price["open"])

        if not gains and not losses:
            return 0

        avg_gain = statistics.mean(gains) if gains else 0
        avg_loss = statistics.mean(losses) if losses else 0

        # Calculate RSI
        rs = avg_gain / avg_loss if avg_loss else 0
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def process(self, candles: List[Dict]) -> Optional[Dict]:
        """Process new price data and return updated indicator values"""
        if not candles or len(candles) == 0:
            return None
        
        # Get the latest candlestick
        latest_candle = candles[0]
        
        valid_rsi = True
        latest_rsi = 50
        color = self.default_color

        # Keep only the needed history (sma_period + some extra)
        max_history = max(self.rsi_period * 3, 100)
        if len(self.historical_candles) > max_history:
            self.historical_candles = self.historical_candles[-max_history:]
        elif len(self.historical_candles) < self.rsi_period:
            # Not enough data to calculate SMA
            print(f"Not enough historical prices to calculate SMA. Need at least {self.rsi_period} prices.")
            valid_rsi = False
        
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

        if valid_rsi:
            # Recalculate SMA
            latest_rsi = self._calculate_rsi()
            print(f"Calculated RSI: {latest_rsi} for period {self.rsi_period}")
            # Compare with the previous historical result's RSI value, not rsi_values array
            if len(self.historical_results) > 0:
                if latest_rsi >= self.upperBand:
                    print(f"RSI {latest_rsi} exceeds upper band {self.upperBand}")
                    color = self.upperBand_color
                elif latest_rsi <= self.lowerBand:
                    print(f"RSI {latest_rsi} falls below lower band {self.lowerBand}")
                    color = self.lowerBand_color
        
        if valid_rsi == False:
            print(f"Invalid RSI value. Default color and close price will be used.")

        # Return the indicator data
        result = {
            'label': f"RSI({self.rsi_period})",
            'timestamp': dt,
            'type': 2,  # LINE
            'value': latest_rsi,
            'r': color[0],
            'g': color[1],
            'b': color[2],
            'start_time': start_ts,
            'end_time': end_ts,
            'dataPointId': datapoint_id
        }

        if last_datapoint_id <= 0 or newResult or valid_rsi == False:
            self.historical_results.append(result)
            print(f"New SMA result added: {result}")

        return result
# Create an instance of the indicator for the module
indicator = RSIIndicator()

# Expose the methods at the module level for backward compatibility
get_options_schema = indicator.get_options_schema
start = indicator.start
process = indicator.process
get_historical_results = indicator.get_historical_results




