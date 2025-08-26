import datetime
import json
from enum import IntEnum
from typing import Dict, List, Optional, Any

class IndicatorType(IntEnum):
    UNKNOWN = 0
    CANDLESTICK = 1
    LINE = 2
    BAR = 3

class Indicator:
    """Base class for all indicators"""
    def __init__(self, name: str = ""):
        self.id = "default"
        self.symbol = "default"
        self.name = name
        self.options = {}
        self.historical_data = []
        self.historical_results = []
        self.datapoint_ids = {}  # (start, end) -> id
        self.next_datapoint_id = 1

    def get_options_schema(self) -> str:
        schema = {
            "title": self.name,
            "description": "Base indicator",
            "properties": {}
        }
        return json.dumps(schema)

    def start(self, historical_data: List[Dict], options: Dict[str, Any]) -> bool:
        self.historical_data = historical_data
        self.options = options

        # Initialize historical results and datapoint tracking
        self.historical_results = []
        self.datapoint_ids = {}
        self.next_datapoint_id = 1

        return True

    def stop(self):
        self.historical_results = []
        self.last_processed_time = None
        self.datapoint_ids = {}

    def process(self, candles: List[Dict]) -> Optional[Dict]:
        return None
    
    def get_historical_results(self) -> List[Dict]:
        return self.historical_results

    def get_datapoint_id(self, start, end):
        key = (start, end)
        if key not in self.datapoint_ids:
            self.datapoint_ids[key] = self.next_datapoint_id
            self.next_datapoint_id += 1
        return self.datapoint_ids[key]

    def parse_color(self, color_val):
        if isinstance(color_val, tuple) and len(color_val) == 3:
            return color_val
        if isinstance(color_val, str):
            color_val = color_val.strip()
            if color_val.startswith('#'):
                # Hex string
                color_val = color_val.lstrip('#')
                lv = len(color_val)
                if lv == 6:
                    return tuple(int(color_val[i:i+2], 16) for i in (0, 2, 4))
            elif ',' in color_val:
                # Comma-separated string
                parts = color_val.split(',')
                if len(parts) == 3:
                    return tuple(int(float(p.strip())) for p in parts)
        # Fallback to green/red
        return (0, 255, 0)