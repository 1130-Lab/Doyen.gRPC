import datetime
import json
import logging
from typing import Dict, List, Optional, Any
from Indicator import Indicator

logger = logging.getLogger(__name__)

class PriceDisplayIndicator(Indicator):
    """Indicator for displaying price data as candlesticks or bars"""
    def __init__(self):
        super().__init__("Price Display")
        self.display_mode = "candlestick"  # Options: "candlestick" or "bar" or "line"
        self.up_color = (0, 255, 0)
        self.down_color = (255, 0, 0)

    def get_options_schema(self) -> str:
        schema = {
            "title": self.name,
            "description": "Simple indicator to display price data",
            "properties": {
                "displayMode": {
                    "title": "Display Mode",
                    "description": "How to display the price data",
                    "type": "string",
                    "options": "candlestick, bar, line",
                    "value": "candlestick"
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
                }
            }
        }
        return json.dumps(schema)

    def start(self, historical_data: List[Dict], options: Dict[str, Any]) -> bool:
        super().start(historical_data, options)
        # Load config from options
        props = options['properties']
        logger.info(f"Starting PriceDisplayIndicator with properties: {props}")
        self.display_mode = props['displayMode']['value']
        self.up_color = self.parse_color(props['upColor']['value'])
        self.down_color = self.parse_color(props['downColor']['value'])
        logger.info(f"Price display indicator started with mode: {self.display_mode}, up_color: {self.up_color}, down_color: {self.down_color}")
        # Process historical data
        for candle in historical_data:
            result = self.process([candle])
            if result:
                self.historical_results.append(result)
        return True

    def stop(self) -> None:
        super().stop()
        logger.info("PriceDisplayIndicator stopped.")

    def process(self, candles: List[Dict]) -> Optional[Dict]:
        if not candles or len(candles) == 0:
            return None
        candle = candles[0]
        is_up = candle['close'] >= candle['open']
        color = self.up_color if is_up else self.down_color
        datapoint_id = self.get_datapoint_id(candle['start_time'], candle['end_time'])
        if self.display_mode == "bar":
            return {
                'label': 'bardata',
                'timestamp': candle['timestamp'],
                'type': 3,  # BAR
                'bottom': min(candle['open'], candle['close']),
                'top': max(candle['open'], candle['close']),
                'r': color[0],
                'g': color[1],
                'b': color[2],
                'dataPointId': datapoint_id
            }
        elif self.display_mode == "line":
            return {
                'label': 'linedata',
                'timestamp': candle['timestamp'],
                'type': 2,  # LINE
                'value': candle['close'],
                'r': color[0],
                'g': color[1],
                'b': color[2],
                'dataPointId': datapoint_id
            }
        else:
            return {
                'label': 'candledata',
                'timestamp': candle['timestamp'],
                'type': 1,  # CANDLESTICK
                'open': candle['open'],
                'high': candle['high'],
                'low': candle['low'],
                'close': candle['close'],
                'r': color[0],
                'g': color[1],
                'b': color[2],
                'dataPointId': datapoint_id
            }

indicator = PriceDisplayIndicator()
get_options_schema = indicator.get_options_schema
start = indicator.start
process = indicator.process
get_historical_results = indicator.get_historical_results