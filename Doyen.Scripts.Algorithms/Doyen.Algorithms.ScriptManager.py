import argparse
import asyncio
import grpc
import os
import sys
import types
import json
import datetime
import concurrent.futures as futures
from google.protobuf.timestamp_pb2 import Timestamp
import common_pb2
import common_pb2_grpc

# Add the current directory to path to find the generated proto files
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import the generated proto files
try:
    import algos_pb2 as algos_pb2
    import algos_pb2_grpc as algos_pb2_grpc
    import importlib
    # Force reload in case of changes
    importlib.reload(algos_pb2)
    importlib.reload(algos_pb2_grpc)
except ImportError:
    print("Error: Proto files not found. Make sure to run compile_proto.py first.")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools"])
    import algos_pb2
    import algos_pb2_grpc

# Import the Algorithm base class
try:
    from Algorithm import Algorithm
except ImportError:
    print("Error: Algorithm base class not found. Make sure Algorithm.py is in the same directory.")

active_algorithms = {}

class AlgorithmContext:
    def __init__(self, algo_id, name, algorithm=None):
        self.id = algo_id
        self.name = name
        self.algorithm = algorithm

def timestamp_to_datetime(timestamp):
    return datetime.datetime.fromtimestamp(
        timestamp.seconds + timestamp.nanos / 1e9,
        tz=datetime.timezone.utc
    )

def datetime_to_timestamp(dt):
    timestamp = Timestamp()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    timestamp.FromDatetime(dt)
    return timestamp

class ScriptServicer(algos_pb2_grpc.AlgorithmServerServicer):
    """
    This servicer handles both directions of communication:
    - Script → Doyen: SubscribeSymbol, SendOrder, CancelOrder (forwarded to Doyen via client)
    - Doyen → Script: InitializeAlgorithm, StartAlgorithm, TradeData, etc. (handled locally)
    """
    def __init__(self, client_stub):
        self.client = client_stub

    # Doyen → Script services (Doyen calls these on our server)
    def InitializeAlgorithm(self, request, context):
        """Handle algorithm initialization request from Doyen"""
        print(f"Initializing algorithm: {request.name} (ID: {request.algoId})")
        try:
            script_path = f"{request.name}.py"
            if not os.path.exists(script_path):
                script_path = os.path.join(current_dir, f"{request.name}.py")
                if not os.path.exists(script_path):
                    print(f"Algorithm script not found: {request.name}.py")
                    return algos_pb2.InitializeAlgorithmResponse(
                        algoId=request.algoId,
                        success=False,
                        reason="Script not found",
                        listenDepthOfBook=False,
                        listenTrades=False,
                        listenCandlesticks=False,
                        hasOptionsPanel=False
                    )
            algorithm = load_algorithm_from_file(self, request.algoId, script_path)
            if not algorithm:
                print(f"Failed to load algorithm: {request.name}")
                return algos_pb2.InitializeAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason="Failed to load algorithm",
                    listenDepthOfBook=False,
                    listenTrades=False,
                    listenCandlesticks=False,
                    hasOptionsPanel=False
                )
            algo_context = AlgorithmContext(request.algoId, request.name, algorithm)
            active_algorithms[request.algoId] = algo_context
            algorithm.algo_id = request.algoId
            # Get algorithm capabilities
            try:
                options_json = algorithm.get_options_schema()
                has_options = bool(options_json)
            except Exception as e:
                print(f"Error getting options schema: {e}")
                options_json = ""
                has_options = False
            # Determine what data types the algorithm wants to listen to
            listen_dob = hasattr(algorithm, 'process_dob') and callable(getattr(algorithm, 'process_dob'))
            listen_trades = hasattr(algorithm, 'process_trade') and callable(getattr(algorithm, 'process_trade'))
            listen_candles = hasattr(algorithm, 'process_candle') and callable(getattr(algorithm, 'process_candle'))
            print(f"Successfully initialized algorithm {request.name} with ID {request.algoId}")
            return algos_pb2.InitializeAlgorithmResponse(
                algoId=request.algoId,
                success=True,
                reason="",
                listenDepthOfBook=listen_dob,
                listenTrades=listen_trades,
                listenCandlesticks=listen_candles,
                hasOptionsPanel=has_options,
                optionsJsonDataRequest=options_json
            )
        except Exception as e:
            print(f"Error initializing algorithm: {e}")
            import traceback
            traceback.print_exc()
            return algos_pb2.InitializeAlgorithmResponse(
                algoId=request.algoId,
                success=False,
                reason=str(e),
                listenDepthOfBook=False,
                listenTrades=False,
                listenCandlesticks=False,
                hasOptionsPanel=False
            )

    def StartAlgorithm(self, request, context):
        """Handle algorithm start request from Doyen"""
        print(f"Starting algorithm: {request.algoId}")
        try:
            if request.algoId not in active_algorithms:
                print(f"Algorithm not found: {request.algoId}")
                return algos_pb2.StartAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason="Algorithm not initialized"
                )
            context_obj = active_algorithms[request.algoId]
            algorithm = context_obj.algorithm
            options = {}
            if request.optionsJsonDataResponse:
                try:
                    options = json.loads(request.optionsJsonDataResponse)
                except json.JSONDecodeError:
                    print(f"Invalid options JSON: {request.optionsJsonDataResponse}")
            try:
                success = algorithm.start(options)
                if not success:
                    return algos_pb2.StartAlgorithmResponse(
                        algoId=request.algoId,
                        success=False,
                        reason="Algorithm start function returned failure"
                    )
                # After successful start, subscribe to symbols from the algorithm's options
                # (No async, no doyen_client)
                print(f"Successfully started algorithm {request.algoId}")
                return algos_pb2.StartAlgorithmResponse(
                    algoId=request.algoId,
                    success=True,
                    reason=""
                )
            except Exception as e:
                print(f"Error starting algorithm: {e}")
                return algos_pb2.StartAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason=f"Error in start function: {str(e)}"
                )
        except Exception as e:
            print(f"Error starting algorithm: {e}")
            return algos_pb2.StartAlgorithmResponse(
                algoId=request.algoId,
                success=False,
                reason=str(e)
            )
        
    def PauseAlgorithm(self, request, context):
        """Handle algorithm pause request from Doyen"""
        print(f"Pausing algorithm: {request.algoId}")
        try:
            if request.algoId not in active_algorithms:
                print(f"Algorithm not found: {request.algoId}")
                return algos_pb2.PauseAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason="Algorithm not initialized"
                )
            context_obj = active_algorithms[request.algoId]
            algorithm = context_obj.algorithm
            try:
                algorithm.pause()
                print(f"Successfully paused algorithm {request.algoId}")
                return algos_pb2.PauseAlgorithmResponse(
                    algoId=request.algoId,
                    success=True,
                    reason=""
                )
            except Exception as e:
                print(f"Error pausing algorithm: {e}")
                return algos_pb2.PauseAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason=f"Error in pause function: {str(e)}"
                )
        except Exception as e:
            print(f"Error pausing algorithm: {e}")
            return algos_pb2.PauseAlgorithmResponse(
                algoId=request.algoId,
                success=False,
                reason=str(e)
            )
        
    def ResumeAlgorithm(self, request, context):
        """Handle algorithm resume request from Doyen"""
        print(f"Resuming algorithm: {request.algoId}")
        try:
            if request.algoId not in active_algorithms:
                print(f"Algorithm not found: {request.algoId}")
                return algos_pb2.ResumeAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason="Algorithm not initialized"
                )
            context_obj = active_algorithms[request.algoId]
            algorithm = context_obj.algorithm
            try:
                algorithm.resume()
                print(f"Successfully resumed algorithm {request.algoId}")
                return algos_pb2.ResumeAlgorithmResponse(
                    algoId=request.algoId,
                    success=True,
                    reason=""
                )
            except Exception as e:
                print(f"Error resuming algorithm: {e}")
                return algos_pb2.ResumeAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason=f"Error in resume function: {str(e)}"
                )
        except Exception as e:
            print(f"Error resuming algorithm: {e}")
            return algos_pb2.ResumeAlgorithmResponse(
                algoId=request.algoId,
                success=False,
                reason=str(e)
            )
    
    def StopAlgorithm(self, request, context):
        """Handle algorithm stop request from Doyen"""
        print(f"Stopping algorithm: {request.algoId}")
        try:
            if request.algoId not in active_algorithms:
                print(f"Algorithm not found: {request.algoId}")
                return algos_pb2.StopAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason="Algorithm not initialized"
                )
            context_obj = active_algorithms[request.algoId]
            algorithm = context_obj.algorithm
            try:
                algorithm.stop()
                del active_algorithms[request.algoId]
                print(f"Successfully stopped algorithm {request.algoId}")
                return algos_pb2.StopAlgorithmResponse(
                    algoId=request.algoId,
                    success=True,
                    reason=""
                )
            except Exception as e:
                print(f"Error stopping algorithm: {e}")
                return algos_pb2.StopAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason=f"Error in stop function: {str(e)}"
                )
        except Exception as e:
            print(f"Error stopping algorithm: {e}")
            return algos_pb2.StopAlgorithmResponse(
                algoId=request.algoId,
                success=False,
                reason=str(e)
            )

    def TradeData(self, request, context):
        """Handle incoming trade data and forward to algorithms"""
        try:
            for algo_id, algo_context in active_algorithms.items():
                algorithm = algo_context.algorithm
                if hasattr(algorithm, 'process_trade') and callable(getattr(algorithm, 'process_trade')):
                    try:
                        algorithm.process_trade([request])
                    except Exception as e:
                        print(f"Error processing trade data in algorithm {algo_id}: {e}")
            return algos_pb2.TradeAck(id=request.id)
        except Exception as e:
            print(f"Error handling trade data: {e}")
            return algos_pb2.TradeAck(id=request.id)

    def CandlestickData(self, request, context):
        """Handle incoming candlestick data and forward to algorithms"""
        try:
            for algo_id, algo_context in active_algorithms.items():
                algorithm = algo_context.algorithm
                if hasattr(algorithm, 'process_candle') and callable(getattr(algorithm, 'process_candle')):
                    try:
                        algorithm.process_candle([request])
                    except Exception as e:
                        print(f"Error processing candlestick data in algorithm {algo_id}: {e}")
            return algos_pb2.CandlestickAck(id=request.id)
        except Exception as e:
            print(f"Error handling candlestick data: {e}")
            return algos_pb2.CandlestickAck(id=request.id)

    def DepthOfBookData(self, request, context):
        """Handle incoming depth of book data and forward to algorithms"""
        try:
            for algo_id, algo_context in active_algorithms.items():
                algorithm = algo_context.algorithm
                if hasattr(algorithm, 'process_dob') and callable(getattr(algorithm, 'process_dob')):
                    try:
                        algorithm.process_dob(request)
                    except Exception as e:
                        print(f"Error processing depth of book data in algorithm {algo_id}: {e}")
            return algos_pb2.DepthOfBookAck(id=request.id)
        except Exception as e:
            print(f"Error handling depth of book data: {e}")
            return algos_pb2.DepthOfBookAck(id=request.id)

    def OrderStatusUpdate(self, request, context):
        """Handle order status updates and forward to algorithms"""
        try:
            if request.algoId in active_algorithms:
                algo_context = active_algorithms[request.algoId]
                algorithm = algo_context.algorithm
                if hasattr(algorithm, 'process_order_status') and callable(getattr(algorithm, 'process_order_status')):
                    try:
                        algorithm.process_order_status(request)
                    except Exception as e:
                        print(f"Error processing order status update in algorithm {request.algoId}: {e}")
            return algos_pb2.OrderStatusUpdateAck(
                algoId=request.algoId,
                messageId=request.messageId
            )
        except Exception as e:
            print(f"Error handling order status update: {e}")
            return algos_pb2.OrderStatusUpdateAck(
                algoId=request.algoId,
                messageId=request.messageId
            )


def load_algorithm_from_file(servicer : ScriptServicer, algo_id: str, path: str):
    try:
        mod_name = os.path.basename(path).replace('.py', '')
        script_dir = os.path.dirname(path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            module = __import__(mod_name)
            import importlib
            module = importlib.reload(module)
        except ImportError:
            print(f"Loading module {mod_name} using file-based import")
            module = types.ModuleType(mod_name)
            with open(path, 'r') as f:
                code = f.read()
            exec(code, module.__dict__)

        algorithm = None
        if hasattr(module, 'algorithm') and isinstance(module.algorithm, Algorithm):
            algorithm = module.algorithm
            print(f"Found algorithm instance in module {mod_name}")
        else:
            algo_classes = [
                cls for name, cls in module.__dict__.items()
                if isinstance(cls, type) and issubclass(cls, Algorithm) and cls is not Algorithm
            ]
            if algo_classes:
                algorithm = algo_classes[0]()
                print(f"Created algorithm instance from class {algo_classes[0].__name__}")
            else:
                required_functions = ['get_options_schema', 'start', 'process']
                has_functions = all(hasattr(module, func) for func in required_functions)
                if has_functions:
                    class ModuleFunctionWrapper(Algorithm):
                        def __init__(self, module, name):
                            super().__init__(name)
                            self.module = module
                        def get_options_schema(self):
                            return self.module.get_options_schema()
                        def start(self, historical_data, options):
                            return self.module.start(historical_data, options)
                        def process(self, candles):
                            return self.module.process(candles)
                    algorithm = ModuleFunctionWrapper(module, mod_name)
                    print(f"Created function wrapper algorithm for module {mod_name}")

        if algorithm:
            # Set up algorithm with interface to communicate back to ScriptManager/Doyen
            algorithm.algo_id = algo_id
            # Create a servicer instance for this algorithm to use
            algorithm.interface = AlgorithmInterface(algorithm.algo_id, servicer.client)
            methods = [name for name, obj in algorithm.__class__.__dict__.items()
                       if callable(obj) and not name.startswith('_')]
            print(f"Loaded algorithm {mod_name} with methods: {', '.join(methods)}")
            return algorithm
        else:
            print(f"No valid algorithm found in module {mod_name}")
            return None
    except Exception as e:
        print(f"Error loading algorithm from {path}: {e}")
        import traceback
        traceback.print_exc()
        return None

# Global client handler instance (placeholder - need to add DoyenClientHandler class)
# doyen_client = DoyenClientHandler()

class AlgorithmInterface:
    """Clean interface for algorithms to interact with Doyen via ScriptServicer"""
    def __init__(self, algo_id: str, stub):
        self.algo_id = algo_id
        self.client = stub

    def send_order(self, symbol: str, exchange: str, price: float, quantity: float,  order_side : str, order_type : str, message_id: int = None, simulated: bool = False):
        """Send an order - handles protobuf message creation internally"""
        if message_id is None:
            import time
            message_id = int(time.time() * 1000000)
        
        try:
            algo_exchange = self.get_algo_exchange(exchange)
            algo_order_side = self.get_algo_order_side(order_side)
            algo_order_type = self.get_algo_order_type(order_type)
            request = algos_pb2.SendOrderRequest(
                algoId=self.algo_id,
                messageId=message_id,
                symbol=symbol,
                exchange=algo_exchange,
                price=price,
                quantity=quantity,
                simulated=simulated,
                orderSide=algo_order_side,
                orderType=algo_order_type
            )
            # Call the servicer's SendOrder method directly
            response = self.client.SendOrder(request)
            return response
        except Exception as e:
            print(f"Error sending order: {e}")
            return None
    
    def cancel_order(self, order_id: str, message_id: int = None, simulated: bool = False):
        """Cancel an order - handles protobuf message creation internally"""
        if message_id is None:
            import time
            message_id = int(time.time() * 1000000)
        
        try:
            request = algos_pb2.CancelOrderRequest(
                algoId=self.algo_id,
                messageId=message_id,
                orderId=order_id,
                simulated=simulated
            )
            # Call the servicer's CancelOrder method directly
            response = self.client.CancelOrder(request)
            return response
        except Exception as e:
            print(f"Error cancelling order: {e}")
            return None
    
    def subscribe_symbol(self, symbol: str, exchange : str, get_historical: bool = False, depth_levels: int = 10, candles_timeframe = common_pb2.TIMEFRAME_FIVE_MINUTES):
        """Subscribe to symbol data - handles protobuf message creation internally"""
        try:
            algo_exchange = self.get_algo_exchange(exchange)
            request = algos_pb2.SymbolDataRequest(
                algoId=self.algo_id,
                symbol=symbol,
                exchange=algo_exchange,
                getHistorical=get_historical,
                depthOfBookLevels=depth_levels,
                candlesTimeframe=candles_timeframe
            )
            # Call the servicer's SubscribeSymbol method directly
            response = self.client.SubscribeSymbol(request)
            return {"success": response.success, "reason": response.reason}
        except Exception as e:
            print(f"Error subscribing to symbol: {e}")
            return {"success": False, "reason": str(e)}
    
    def get_algo_exchange(self, name: str) -> object:
        """Get the Exchange enum value for a given exchange name"""
        exchange_name = f"EXCHANGE_{name.upper()}"
        return getattr(common_pb2, exchange_name, 0)  # 0 = EXCHANGE_UNKNOWN
    
    def get_algo_order_side(self, side: str) -> object:
        """Get the OrderSide enum value for a given order side"""
        side_name = f"ORDER_SIDE_{side.upper()}"
        return getattr(algos_pb2, side_name, 0)
    
    def get_algo_order_type(self, order_type: str) -> object:
        """Get the OrderType enum value for a given order type"""
        order_type_name = f"ORDER_TYPE_{order_type.upper()}"
        return getattr(algos_pb2, order_type_name, 0)


async def start_grpc_server(server_address, client_address):
    """Start the gRPC server"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    server.add_insecure_port(server_address)
    channel = grpc.insecure_channel(client_address)
    client_stub = algos_pb2_grpc.AlgorithmServerStub(channel)
    algos_pb2_grpc.add_AlgorithmServerServicer_to_server(ScriptServicer(client_stub), server)
    await server.start()
    print(f"gRPC server started {server_address}")
    print(f"gRPC client started {client_address}")
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

async def message_processing_loop():
    """
    Continuously process messages in a non-blocking way.
    This simulates a busy loop that can receive and process messages from various sources.
    """
    print("Starting message processing loop...")
    
    while True:
        try:
            # Check for any pending tasks or messages
            for indicator_id, context in list(active_algorithms.items()):
                pass
            
            # Process any backlog or queue if needed
            # This is where you'd integrate with any message queue system
            
            # Brief pause to avoid consuming too much CPU
            await asyncio.sleep(0.1)
            
        except asyncio.CancelledError:
            print("Message processing loop cancelled")
            break
        except Exception as e:
            print(f"Error in message processing loop: {e}")
            # Don't break the loop on error, just log and continue
            await asyncio.sleep(1)  # Longer pause after an error

async def main(server, client):
    """Main function to start both the gRPC server and message processing"""
    print("Starting Doyen Script Manager...")
    
    # Start the gRPC server
    server_task = asyncio.create_task(start_grpc_server(server, client))
    
    # Start the message processing loop
    message_task = asyncio.create_task(message_processing_loop())
    
    # Wait for all tasks
    try:
        await asyncio.gather(server_task, message_task)
    except asyncio.CancelledError:
        print("Main tasks cancelled")
    except Exception as e:
        print(f"Error in main tasks: {e}")
    finally:
        # Ensure all tasks are properly cancelled
        for task in [server_task, message_task]:
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
        parser = argparse.ArgumentParser(description="Doyen Algorithm Script Manager")
        parser.add_argument("--server", type=str, default="localhost:5050", help="Address to run the gRPC server on")
        parser.add_argument("--client", type=str, default="localhost:5051", help="Address to run the gRPC client on")
        args = parser.parse_args()
        asyncio.run(main(args.server, args.client))
    except KeyboardInterrupt:
        print("Script manager terminated by user")
    except Exception as e:
        print(f"Fatal error: {e}")