import argparse
import asyncio
import grpc
import os
import sys
import types
import json
import datetime
import concurrent.futures
from concurrent import futures
from google.protobuf.timestamp_pb2 import Timestamp

# Add the current directory to path to find the generated proto files
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Import the generated proto files
try:
    import charts_pb2 as charts_pb2
    import charts_pb2_grpc as charts_pb2_grpc
except ImportError:
    print("Error: Proto files not found. Make sure to run compile_proto.py first.")
    print("Installing required packages and compiling proto files...")
    # Try to install required packages
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools"])
    # Try to compile the proto file
    import compile_proto
    # Retry importing
    import charts_pb2 as charts_pb2
    import charts_pb2_grpc as charts_pb2_grpc

# Import the indicator base class
try:
    from Indicator import Indicator
except ImportError:
    print("Error: Indicator base class not found. Make sure Indicator.py is in the same directory.")

# Create a global event loop for each thread
def get_or_create_event_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        # If there's no event loop in this thread, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

class IndicatorContext:
    """Stores context for an active indicator"""
    def __init__(self, indicator_id, symbol, name, indicator=None):
        self.id = indicator_id
        self.symbol = symbol
        self.name = name
        self.indicator = indicator

async def load_indicator_from_file(id, symbol, path):
    """Load an indicator from a file"""
    try:
        # Get the module name from the file path
        mod_name = os.path.basename(path).replace('.py', '')
        
        # Add the directory to the Python path
        script_dir = os.path.dirname(path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        
        # Import the module
        try:
            # Try to import the module directly first
            module = __import__(mod_name)
            
            # Reload to ensure we have the latest version
            import importlib
            module = importlib.reload(module)
            
        except ImportError:
            # If that fails, fall back to the old method of loading from file
            print(f"Loading module {mod_name} using file-based import")
            module = types.ModuleType(mod_name)
            
            with open(path, 'r') as f:
                code = f.read()
            exec(code, module.__dict__)
        
        # Look for the indicator instance
        indicator = None
        
        # First try to get the predefined indicator instance
        if hasattr(module, 'indicator') and isinstance(module.indicator, Indicator):
            indicator = module.indicator
            indicator.id = id
            indicator.symbol = symbol
            print(f"Found indicator instance in module {mod_name}")
        else:
            # Look for an Indicator subclass in the module
            indicator_classes = [
                cls for name, cls in module.__dict__.items()
                if isinstance(cls, type) and issubclass(cls, Indicator) and cls is not Indicator
            ]
            
            if indicator_classes:
                # Use the first found indicator class
                indicator = indicator_classes[0]()
                print(f"Created indicator instance from class {indicator_classes[0].__name__}")
            else:
                # Fall back to using module-level functions if available
                required_functions = ['get_options_schema', 'start', 'process']
                has_functions = all(hasattr(module, func) for func in required_functions)
                
                if has_functions:
                    # Create a wrapper indicator that delegates to the module-level functions
                    class ModuleFunctionWrapper(Indicator):
                        def __init__(self, module, id, symbol, name):
                            super().__init__(name)
                            self.id = id
                            self.symbol = symbol
                            self.module = module
                            module.id = id
                            module.symbol = symbol
                            print(f"Created function wrapper for module {name} with id {id} and symbol {symbol}")
                        
                        def get_options_schema(self):
                            return self.module.get_options_schema()
                        
                        def start(self, historical_data, options):
                            return self.module.start(historical_data, options)
                        
                        def process(self, candles):
                            return self.module.process(candles)
                    
                    indicator = ModuleFunctionWrapper(module, id, symbol, mod_name)
                    print(f"Created function wrapper indicator for module {mod_name}")
        
        if indicator:
            # Print available methods in the indicator for debugging
            methods = [name for name, obj in indicator.__class__.__dict__.items() 
                    if callable(obj) and not name.startswith('_')]
            print(f"Loaded indicator {mod_name} with methods: {', '.join(methods)}")

            return indicator
        else:
            print(f"No valid indicator found in module {mod_name}")
            return None
    except Exception as e:
        print(f"Error loading indicator from {path}: {e}")
        import traceback
        traceback.print_exc()
        return None

def timestamp_to_datetime(timestamp):
    """Convert protobuf Timestamp to Python datetime"""
    return datetime.datetime.fromtimestamp(
        timestamp.seconds + timestamp.nanos / 1e9, 
        tz=datetime.timezone.utc
    )

def candlestick_to_dict(cs):
    """Convert protobuf DoyenCandlestick to Python dict"""
    return {
        'exchange': cs.exchange,
        'timeframe': cs.timeframe,
        'timestamp': timestamp_to_datetime(cs.timestamp),
        'start_time': timestamp_to_datetime(cs.timeStart),
        'end_time': timestamp_to_datetime(cs.timeEnd),
        'open': cs.open,
        'high': cs.high,
        'low': cs.low,
        'close': cs.close
    }

def datetime_to_timestamp(dt):
    """Convert Python datetime to protobuf Timestamp"""
    timestamp = Timestamp()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    timestamp.FromDatetime(dt)
    return timestamp

class ChartsServicer(charts_pb2_grpc.ChartsServerServicer):
    """Implementation of the ChartsServer gRPC service"""
    def __init__(self):
        self.active_indicators = {}
    
    async def initialize_indicator_async(self, request, context):
        """Initialize an indicator script"""
        print(f"Initializing indicator: {request.name} for {request.symbol} (ID: {request.id})")
        
        try:
            # Find the script file
            script_path = f"{request.name}.py"
            if not os.path.exists(script_path):
                # Try in the current directory
                script_path = os.path.join(current_dir, f"{request.name}.py")
                if not os.path.exists(script_path):
                    print(f"Indicator script not found: {request.name}.py")
                    return charts_pb2.InitializeIndicatorResponse(
                        id=request.id,
                        success=False,
                        reason=f"Script not found: {request.name}.py",
                        hasOptionsPanel=False
                    )
            
            # Load the indicator
            indicator = await load_indicator_from_file(request.id, request.symbol, script_path)
            if not indicator:
                print(f"Failed to load indicator: {request.name}")
                return charts_pb2.InitializeIndicatorResponse(
                    id=request.id,
                    success=False,
                    reason="Failed to load indicator",
                    hasOptionsPanel=False
                )
            # Store the indicator context
            indicator_context = IndicatorContext(request.id, request.symbol, request.name, indicator)
            self.active_indicators[request.id] = indicator_context
            print(f"Indicator {request.name} initialized successfully with ID {request.id}")
            print(f"Active indicators: {list(self.active_indicators.keys())}")
            
            # Get options schema
            try:
                options_json = indicator.get_options_schema()
                has_options = bool(options_json)
            except Exception as e:
                print(f"Error getting options schema: {e}")
                options_json = ""
                has_options = False
            
            return charts_pb2.InitializeIndicatorResponse(
                id=request.id,
                success=True,
                reason="",
                hasOptionsPanel=has_options,
                optionsJsonDataRequest=options_json
            )
            
        except Exception as e:
            print(f"Error initializing indicator: {e}")
            import traceback
            traceback.print_exc()
            return charts_pb2.InitializeIndicatorResponse(
                id=request.id,
                success=False,
                reason=f"Error: {str(e)}",
                hasOptionsPanel=False
            )
    
    def InitializeIndicator(self, request, context):
        """gRPC handler for InitializeIndicator"""
        loop = get_or_create_event_loop()
        return loop.run_until_complete(self.initialize_indicator_async(request, context))
    
    async def start_indicator_async(self, request, context):
        """Start an indicator with historical data and options"""
        print(f"Starting indicator: {request.id}")
        
        try:
            if request.id not in self.active_indicators:
                print(f"Indicator not found: {request.id}")
                return charts_pb2.StartIndicatorResponse(
                    id=request.id,
                    success=False,
                    reason="Indicator not initialized"
                )
            
            context_obj = self.active_indicators[request.id]
            indicator = context_obj.indicator
            
            # Process options JSON if provided
            options = {}
            if request.optionsJsonDataResponse:
                try:
                    options = json.loads(request.optionsJsonDataResponse)
                except json.JSONDecodeError:
                    print(f"Invalid options JSON: {request.optionsJsonDataResponse}")
            
            # Convert historical data
            historical_data = [candlestick_to_dict(cs) for cs in request.historicalData]
            
            # Start the indicator
            try:
                success = indicator.start(historical_data, options)
                if not success:
                    return charts_pb2.StartIndicatorResponse(
                        id=request.id,
                        success=False,
                        reason="Indicator start function returned failure"
                    )
                
                processed_data = []
                # Publish historical results if available
                if hasattr(indicator, 'get_historical_results'):
                    results = indicator.get_historical_results()
                    print(f"{request.id} indicator has {len(results)} historical results")
                    index = 0;
                    for result in results:

                        indicator_data = charts_pb2.IndicatorData(
                            label=result.get('label', ''),
                            type=result.get('type', charts_pb2.IndicatorMessageType.MESSAGE_LINE),
                            startTimestamp=datetime_to_timestamp(historical_data[index].get('start_time', datetime.datetime.now(datetime.timezone.utc))),
                            endTimestamp=datetime_to_timestamp(historical_data[index].get('end_time', datetime.datetime.now(datetime.timezone.utc)))
                        )
                        
                        # Set dataPointId if present
                        if 'dataPointId' in result:
                            indicator_data.dataPointId = result['dataPointId']

                        # Set timestamp
                        if 'timestamp' in result:
                            if isinstance(result['timestamp'], datetime.datetime):
                                indicator_data.timestamp.CopyFrom(datetime_to_timestamp(result['timestamp']))
                            else:
                                dt = datetime.datetime.fromtimestamp(result['timestamp'] / 1000, tz=datetime.timezone.utc)
                                indicator_data.timestamp.CopyFrom(datetime_to_timestamp(dt))

                        # Set RGB values
                        if 'r' in result:
                            indicator_data.r = result['r']
                        if 'g' in result:
                            indicator_data.g = result['g']
                        if 'b' in result:
                            indicator_data.b = result['b']

                        # Set the appropriate message based on type
                        if result.get('type') == charts_pb2.IndicatorMessageType.MESSAGE_LINE or result.get('type') == 2:
                            indicator_data.lineMessage.value = float(result.get('value', 0))
                        elif result.get('type') == charts_pb2.IndicatorMessageType.MESSAGE_CANDLESTICK or result.get('type') == 1:
                            indicator_data.candlestickMessage.open = float(result.get('open', 0))
                            indicator_data.candlestickMessage.high = float(result.get('high', 0))
                            indicator_data.candlestickMessage.low = float(result.get('low', 0))
                            indicator_data.candlestickMessage.close = float(result.get('close', 0))
                        elif result.get('type') == charts_pb2.IndicatorMessageType.MESSAGE_BAR or result.get('type') == 3:
                            indicator_data.barMessage.bottom = float(result.get('bottom', 0))
                            indicator_data.barMessage.top = float(result.get('top', 0))
                        
                        index += 1
                        processed_data.append(indicator_data)
            
            except Exception as e:
                print(f"Error starting indicator: {e}")
                return charts_pb2.StartIndicatorResponse(
                    id=request.id,
                    success=False,
                    reason=f"Error in start function: {str(e)}"
                )
            
            return charts_pb2.StartIndicatorResponse(
                id=request.id,
                success=True,
                reason="",
                historicalData=processed_data
            )
            
        except Exception as e:
            print(f"Error starting indicator: {e}")
            import traceback
            traceback.print_exc()
            return charts_pb2.StartIndicatorResponse(
                id=request.id,
                success=False,
                reason=f"Error: {str(e)}"
            )
    
    def StartIndicator(self, request, context):
        """gRPC handler for StartIndicator"""
        loop = get_or_create_event_loop()
        return loop.run_until_complete(self.start_indicator_async(request, context))
    
    async def stop_indicator_async(self, request, context):
        """Stop an indicator"""
        print(f"Stopping indicator: {request.id}")
        
        try:
            if request.id not in self.active_indicators:
                print(f"Indicator not found: {request.id}")
                return charts_pb2.StopIndicatorResponse(
                    id=request.id,
                    success=False,
                    reason="Indicator not found"
                )
            
            context_obj = self.active_indicators[request.id]
            indicator = context_obj.indicator
            
            # Stop the indicator
            try:
                indicator.stop()
            except Exception as e:
                print(f"Error stopping indicator: {e}")
                return charts_pb2.StopIndicatorResponse(
                    id=request.id,
                    success=False,
                    reason=f"Error in stop function: {str(e)}"
                )
            
            # Remove the indicator from active indicators
            del self.active_indicators[request.id]
            
            return charts_pb2.StopIndicatorResponse(
                id=request.id,
                success=True,
                reason=""
            )
            
        except Exception as e:
            print(f"Error stopping indicator: {e}")
            import traceback
            traceback.print_exc()
            return charts_pb2.StopIndicatorResponse(
                id=request.id,
                success=False,
                reason=f"Error: {str(e)}"
            )
    
    def StopIndicator(self, request, context):
        """gRPC handler for StopIndicator"""
        loop = get_or_create_event_loop()
        return loop.run_until_complete(self.stop_indicator_async(request, context))
    
    async def process_data_async(self, request, context, candlesticks, indicator):
        """Process new data with the indicator"""
        print(f"Processing data for symbol: {request.symbol}")
        
        try:
            # Find any active indicator to process this data
            if not self.active_indicators or indicator.indicator.symbol != request.symbol:
                print("No active indicators to process data")
                return charts_pb2.DataMessageResponse(
                    id="",
                    data=None
                )
            else:
                print(f"Processing data with indicator {indicator.id} for symbol {request.symbol}")
            
            # Process the data with the indicator
            try:
                result = indicator.indicator.process(candlesticks)
                
                if result:
                    # Create the response
                    indicator_data = charts_pb2.IndicatorData(
                        id=indicator.id,
                        label=result.get('label', ''),
                        type=result.get('type', charts_pb2.IndicatorMessageType.MESSAGE_LINE)
                    )
                    
                    # Set dataPointId if present
                    if 'dataPointId' in result:
                        indicator_data.dataPointId = int(result['dataPointId'])
                    
                    # Set timestamp if provided
                    if 'timestamp' in result:
                        if isinstance(result['timestamp'], datetime.datetime):
                            indicator_data.timestamp.CopyFrom(datetime_to_timestamp(result['timestamp']))
                        else:
                            # Assume timestamp is in milliseconds since epoch
                            dt = datetime.datetime.fromtimestamp(result['timestamp'] / 1000, tz=datetime.timezone.utc)
                            indicator_data.timestamp.CopyFrom(datetime_to_timestamp(dt))
                    
                    # Set RGB values if provided
                    if 'r' in result:
                        indicator_data.r = result['r']
                    if 'g' in result:
                        indicator_data.g = result['g']
                    if 'b' in result:
                        indicator_data.b = result['b']
                    
                    indicator_data.startTimestamp.CopyFrom(datetime_to_timestamp(candlesticks[-1].get('start_time', datetime.datetime.now(datetime.timezone.utc))))
                    indicator_data.endTimestamp.CopyFrom(datetime_to_timestamp(candlesticks[-1].get('end_time', datetime.datetime.now(datetime.timezone.utc))))
                    
                    # Set the appropriate message based on type
                    if result.get('type') == charts_pb2.IndicatorMessageType.MESSAGE_LINE or result.get('type') == 2:
                        indicator_data.lineMessage.value = float(result.get('value', 0))
                        print(f"Processed line message with value: {indicator_data.lineMessage.value}")
                    elif result.get('type') == charts_pb2.IndicatorMessageType.MESSAGE_CANDLESTICK or result.get('type') == 1:
                        indicator_data.candlestickMessage.open = float(result.get('open', 0))
                        indicator_data.candlestickMessage.high = float(result.get('high', 0))
                        indicator_data.candlestickMessage.low = float(result.get('low', 0))
                        indicator_data.candlestickMessage.close = float(result.get('close', 0))
                    elif result.get('type') == charts_pb2.IndicatorMessageType.MESSAGE_BAR or result.get('type') == 3:
                        indicator_data.barMessage.bottom = float(result.get('bottom', 0))
                        indicator_data.barMessage.top = float(result.get('top', 0))

                    return charts_pb2.DataMessageResponse(
                        id=indicator.id,
                        data=indicator_data
                    )

            except Exception as e:
                print(f"Error processing data with indicator: {e}")
                import traceback
                traceback.print_exc()
            
            # If we get here, we couldn't process the data
            return charts_pb2.DataMessageResponse(
                id=indicator.id,
                data=None
            )
            
        except Exception as e:
            print(f"Error processing data: {e}")
            import traceback
            traceback.print_exc()
            return charts_pb2.DataMessageResponse(
                id="",
                data=None
            )
    
    def ProcessData(self, request, context):
        """gRPC handler for ProcessData"""
        # Convert candlesticks
        candlesticks = [candlestick_to_dict(cs) for cs in request.candlesticks]
            
        for indicator in self.active_indicators.values():
            loop = get_or_create_event_loop()
            yield loop.run_until_complete(self.process_data_async(request, context, candlesticks, indicator))

async def start_grpc_server(address):
    """Start the gRPC server"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    charts_pb2_grpc.add_ChartsServerServicer_to_server(ChartsServicer(), server)
    server_address = address
    server.add_insecure_port(server_address)
    await server.start()
    print(f"gRPC server started on {server_address}")
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        await server.stop(0)
        print("gRPC server stopped")
        sys.exit(0)
    except Exception as e:
        print(f"gRPC server terminated unexpectedly: {e}")
        sys.exit(1)
    # If wait_for_termination returns without exception, exit as well
    print("gRPC server terminated, exiting script.")
    sys.exit(0)

async def main(address):
    """Main function to start both the gRPC server and message processing"""
    print("Starting Doyen Script Manager...")
    
    # Start the gRPC server
    server_task = asyncio.create_task(start_grpc_server(address))
    
    # Wait for all tasks
    try:
        await asyncio.gather(server_task)
    except asyncio.CancelledError:
        print("Main tasks cancelled")
    except Exception as e:
        print(f"Error in main tasks: {e}")
    finally:
        # Ensure all tasks are properly cancelled
        for task in [server_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

if __name__ == "__main__":
    # Check if grpcio and grpcio-tools are installed
    try:
        import grpc.aio
    except ImportError:
        print("Error: grpcio package is not installed.")
        print("Installing required packages...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools"])
        import grpc.aio
    
    # Run the async main function
    try:
        parser = argparse.ArgumentParser(description="Doyen Script Manager")
        parser.add_argument("--address", type=str, default="0.0.0.0:5000", help="Address to run the gRPC server on")
        args = parser.parse_args()
        asyncio.run(main(args.address))
    except KeyboardInterrupt:
        print("Script manager terminated by user")
    except Exception as e:
        print(f"Fatal error: {e}")
