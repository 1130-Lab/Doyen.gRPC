import argparse
import asyncio
import grpc
import os
import sys
import types
import json
import datetime
import logging
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
    logging.error("Error: Proto files not found. Make sure to run compile_proto.py first.")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools"])


# Import the Algorithm base class
try:
    from Algorithm import Algorithm
except ImportError:
    logging.error("Error: Algorithm base class not found. Make sure Algorithm.py is in the same directory.")

logger = logging.getLogger(__name__)

active_algorithms = {}

class AlgorithmState:
    """Algorithm state constants"""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"

class AlgorithmContext:
    def __init__(self, algo_id, name, algorithm=None):
        self.id = algo_id
        self.name = name
        self.algorithm = algorithm
        self.state = AlgorithmState.INITIALIZED
        self.configuration = None

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
        logger.info("Initializing algorithm: %s (ID: %s)", request.name, request.algoId)
        try:
            script_path = f"{request.name}.py"
            if not os.path.exists(script_path):
                script_path = os.path.join(current_dir, f"{request.name}.py")
                if not os.path.exists(script_path):
                    logger.warning("Algorithm script not found: %s.py", request.name)
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
                logger.warning("Failed to load algorithm: %s", request.name)
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
                logger.error("Error getting options schema: %s", e)
                options_json = ""
                has_options = False
            # Determine what data types the algorithm wants to listen to
            listen_dob = hasattr(algorithm, 'process_dob') and callable(getattr(algorithm, 'process_dob'))
            listen_trades = hasattr(algorithm, 'process_trade') and callable(getattr(algorithm, 'process_trade'))
            listen_candles = hasattr(algorithm, 'process_candle') and callable(getattr(algorithm, 'process_candle'))
            logger.info("Successfully initialized algorithm %s with ID %s", request.name, request.algoId)
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
            logger.error("Error initializing algorithm: %s", e)
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
        logger.info("Starting algorithm: %s", request.algoId)
        try:
            if request.algoId not in active_algorithms:
                logger.warning("Algorithm not found: %s", request.algoId)
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
                    # Store configuration
                    context_obj.configuration = request.optionsJsonDataResponse
                except json.JSONDecodeError:
                    logger.error("Invalid options JSON: %s", request.optionsJsonDataResponse)
            try:
                success = algorithm.start(options)
                if not success:
                    return algos_pb2.StartAlgorithmResponse(
                        algoId=request.algoId,
                        success=False,
                        reason="Algorithm start function returned failure"
                    )
                # Set state to Running
                context_obj.state = AlgorithmState.RUNNING
                # After successful start, subscribe to symbols from the algorithm's options
                # (No async, no doyen_client)
                logger.info("Successfully started algorithm %s", request.algoId)
                return algos_pb2.StartAlgorithmResponse(
                    algoId=request.algoId,
                    success=True,
                    reason=""
                )
            except Exception as e:
                logger.error("Error starting algorithm: %s", e)
                return algos_pb2.StartAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason=f"Error in start function: {str(e)}"
                )
        except Exception as e:
            logger.error("Error starting algorithm: %s", e)
            return algos_pb2.StartAlgorithmResponse(
                algoId=request.algoId,
                success=False,
                reason=str(e)
            )
        
    def PauseAlgorithm(self, request, context):
        """Handle algorithm pause request from Doyen"""
        logger.info("Pausing algorithm: %s", request.algoId)
        try:
            if request.algoId not in active_algorithms:
                logger.warning("Algorithm not found: %s", request.algoId)
                return algos_pb2.PauseAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason="Algorithm not initialized"
                )
            context_obj = active_algorithms[request.algoId]
            algorithm = context_obj.algorithm
            try:
                algorithm.pause()
                # Set state to Paused
                context_obj.state = AlgorithmState.PAUSED
                logger.info("Successfully paused algorithm %s", request.algoId)
                return algos_pb2.PauseAlgorithmResponse(
                    algoId=request.algoId,
                    success=True,
                    reason=""
                )
            except Exception as e:
                logger.error("Error pausing algorithm: %s", e)
                return algos_pb2.PauseAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason=f"Error in pause function: {str(e)}"
                )
        except Exception as e:
            logger.error("Error pausing algorithm: %s", e)
            return algos_pb2.PauseAlgorithmResponse(
                algoId=request.algoId,
                success=False,
                reason=str(e)
            )
        
    def ResumeAlgorithm(self, request, context):
        """Handle algorithm resume request from Doyen"""
        logger.info("Resuming algorithm: %s", request.algoId)
        try:
            if request.algoId not in active_algorithms:
                logger.warning("Algorithm not found: %s", request.algoId)
                return algos_pb2.ResumeAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason="Algorithm not initialized"
                )
            context_obj = active_algorithms[request.algoId]
            algorithm = context_obj.algorithm
            try:
                algorithm.resume()
                # Set state back to Running
                context_obj.state = AlgorithmState.RUNNING
                logger.info("Successfully resumed algorithm %s", request.algoId)
                return algos_pb2.ResumeAlgorithmResponse(
                    algoId=request.algoId,
                    success=True,
                    reason=""
                )
            except Exception as e:
                logger.error("Error resuming algorithm: %s", e)
                return algos_pb2.ResumeAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason=f"Error in resume function: {str(e)}"
                )
        except Exception as e:
            logger.error("Error resuming algorithm: %s", e)
            return algos_pb2.ResumeAlgorithmResponse(
                algoId=request.algoId,
                success=False,
                reason=str(e)
            )
    
    def StopAlgorithm(self, request, context):
        """Handle algorithm stop request from Doyen"""
        logger.info("Stopping algorithm: %s", request.algoId)
        try:
            if request.algoId not in active_algorithms:
                logger.warning("Algorithm not found: %s", request.algoId)
                return algos_pb2.StopAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason="Algorithm not initialized"
                )
            context_obj = active_algorithms[request.algoId]
            algorithm = context_obj.algorithm
            try:
                algorithm.stop()
                # Set state to Stopped, then remove
                context_obj.state = AlgorithmState.STOPPED
                del active_algorithms[request.algoId]
                logger.info("Successfully stopped algorithm %s", request.algoId)
                return algos_pb2.StopAlgorithmResponse(
                    algoId=request.algoId,
                    success=True,
                    reason="[v8.6.0]"
                )
            except Exception as e:
                logger.error("Error stopping algorithm: %s", e)
                return algos_pb2.StopAlgorithmResponse(
                    algoId=request.algoId,
                    success=False,
                    reason=f"Error in stop function: {str(e)}"
                )
        except Exception as e:
            logger.error("Error stopping algorithm: %s", e)
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
                        logger.error("Error processing trade data in algorithm %s: %s", algo_id, e)
            return algos_pb2.TradeAck(id=request.id)
        except Exception as e:
            logger.error("Error handling trade data: %s", e)
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
                        logger.error("Error processing candlestick data in algorithm %s: %s", algo_id, e)
            return algos_pb2.CandlestickAck(id=request.id)
        except Exception as e:
            logger.error("Error handling candlestick data: %s", e)
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
                        logger.error("Error processing depth of book data in algorithm %s: %s", algo_id, e)
            return algos_pb2.DepthOfBookAck(id=request.id)
        except Exception as e:
            logger.error("Error handling depth of book data: %s", e)
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
                        logger.error("Error processing order status update in algorithm %s: %s", request.algoId, e)
            return algos_pb2.OrderStatusUpdateAck(
                algoId=request.algoId,
                messageId=request.messageId
            )
        except Exception as e:
            logger.error("Error handling order status update: %s", e)
            return algos_pb2.OrderStatusUpdateAck(
                algoId=request.algoId,
                messageId=request.messageId
            )

    def ListAvailableAlgorithms(self, request, context):
        """Handle request to list all available algorithms"""
        logger.info("Listing available algorithms with filter: '%s'", request.nameFilter)
        try:
            algorithm_infos = []
            
            # Get all Python files in the current directory
            import glob
            script_files = glob.glob("*.py")
            
            for script_file in script_files:
                # Skip the current script and base classes
                if script_file in ['Doyen.Algorithms.ScriptManager.py', 'Algorithm.py', '__init__.py']:
                    continue
                    
                try:
                    algorithm_name = script_file.replace('.py', '')
                    
                    # Apply name filter if provided
                    if request.nameFilter and request.nameFilter not in algorithm_name.lower():
                        continue
                    
                    # Try to load the algorithm to get its metadata
                    algorithm = load_algorithm_from_file(self, "temp_id", script_file)
                    if algorithm:
                        try:
                            # Get algorithm metadata
                            display_name = algorithm.get_display_name() if hasattr(algorithm, 'get_display_name') else algorithm_name
                            description = algorithm.get_description() if hasattr(algorithm, 'get_description') else "A trading algorithm"
                            version = algorithm.get_version() if hasattr(algorithm, 'get_version') else "1.0.0"
                            author = algorithm.get_author() if hasattr(algorithm, 'get_author') else "Unknown"
                            tags = algorithm.get_tags() if hasattr(algorithm, 'get_tags') else ["trading"]
                            

                            # Get options schema
                            options_schema = ""
                            has_options = False
                            try:
                                options_schema = algorithm.get_options_schema()
                                has_options = bool(options_schema) and options_schema != "{}"
                            except Exception as e:
                                logger.error("Error getting options schema for %s: %s", algorithm_name, e)
                            

                            # Create algorithm info
                            algorithm_info = algos_pb2.AlgorithmInfo(
                                name=algorithm_name,
                                displayName=display_name,
                                description=description,
                                version=version,
                                author=author,
                                tags=tags,
                                hasOptionsPanel=has_options,
                                optionsSchema=options_schema
                            )
                            
                            algorithm_infos.append(algorithm_info)
                            logger.info("Found algorithm: %s", algorithm_name)
                            
                        except Exception as e:
                            logger.error("Error getting metadata for algorithm %s: %s", algorithm_name, e)
                    
                except Exception as e:
                    logger.error("Error processing script file %s: %s", script_file, e)
            
            logger.info("Found %d available algorithms", len(algorithm_infos))
            
            return algos_pb2.ListAvailableAlgorithmsResponse(
                success=True,
                reason="",
                algorithms=algorithm_infos
            )
            
        except Exception as e:
            logger.error("Error listing available algorithms: %s", e)
            return algos_pb2.ListAvailableAlgorithmsResponse(
                success=False,
                reason=str(e),
                algorithms=[]
            )

    def ListRunningAlgorithms(self, request, context):
        """Handle request to list all currently running or paused algorithms"""
        logger.info("Listing running algorithms with filter: '%s'", request.nameFilter)
        try:
            running_algorithm_infos = []
            
            # Filter active algorithms that are Running or Paused
            for algo_id, algo_context in active_algorithms.items():
                if algo_context.state not in [AlgorithmState.RUNNING, AlgorithmState.PAUSED]:
                    continue
                
                # Apply name filter if provided
                if request.nameFilter and request.nameFilter not in algo_context.name.lower():
                    continue
                
                algorithm = algo_context.algorithm
                if algorithm:
                    try:
                        # Get algorithm metadata
                        display_name = algorithm.get_display_name() if hasattr(algorithm, 'get_display_name') else algo_context.name
                        description = algorithm.get_description() if hasattr(algorithm, 'get_description') else "A trading algorithm"
                        version = algorithm.get_version() if hasattr(algorithm, 'get_version') else "1.0.0"
                        author = algorithm.get_author() if hasattr(algorithm, 'get_author') else "Unknown"
                        tags = algorithm.get_tags() if hasattr(algorithm, 'get_tags') else ["trading"]
                        
                        # Get options schema
                        options_schema = ""
                        has_options = False
                        try:
                            options_schema = algorithm.get_options_schema()
                            has_options = bool(options_schema) and options_schema != "{}"
                        except Exception as e:
                            logger.error("Error getting options schema for %s: %s", algo_context.name, e)
                        
                        # Create algorithm info
                        algorithm_info = algos_pb2.AlgorithmInfo(
                            name=algo_context.name,
                            displayName=display_name,
                            description=description,
                            version=version,
                            author=author,
                            tags=tags,
                            hasOptionsPanel=has_options,
                            optionsSchema=options_schema
                        )
                        
                        # Create running algorithm info
                        running_info = algos_pb2.RunningAlgorithmInfo(
                            info=algorithm_info,
                            algoId=algo_id,
                            configuration=algo_context.configuration if algo_context.configuration else "{}"
                        )
                        
                        running_algorithm_infos.append(running_info)
                        logger.info("Found running algorithm: %s (ID: %s, State: %s)", algo_context.name, algo_id, algo_context.state)
                        
                    except Exception as e:
                        logger.error("Error processing running algorithm %s: %s", algo_context.name, e)
            
            logger.info("Found %d running algorithms", len(running_algorithm_infos))
            
            return algos_pb2.ListRunningAlgorithmsResponse(
                success=True,
                reason="",
                algorithms=running_algorithm_infos
            )
            
        except Exception as e:
            logger.error("Error listing running algorithms: %s", e)
            return algos_pb2.ListRunningAlgorithmsResponse(
                success=False,
                reason=str(e),
                algorithms=[]
            )

    def AccountBalance(self, request, context):
        """Handle account balance request from Doyen by forwarding to connected server"""
        logger.info("Forwarding AccountBalance request for AlgoId: %s, Exchange: %s, Symbol: %s", request.algoId, request.exchange, request.symbol)
        response = self.client.AccountBalance(request)
        return response

    def OrderStatus(self, request, context):
        """Handle order status request from Doyen by forwarding to connected server"""
        logger.info("Forwarding OrderStatus request for AlgoId: %s, OrderId: %s, Exchange: %s", request.algoId, request.orderId, request.exchange)
        response = self.client.OrderStatus(request)
        return response

    def GetAllOrders(self, request, context):
        """Handle get all orders request from Doyen by forwarding to connected server"""
        logger.info("Forwarding GetAllOrders request for AlgoId: %s, Exchange: %s", request.algoId, request.exchange)
        response = self.client.GetAllOrders(request)
        return response

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
            logger.info("Loading module %s using file-based import", mod_name)
            module = types.ModuleType(mod_name)
            with open(path, 'r') as f:
                code = f.read()
            exec(code, module.__dict__)

        algorithm = None
        if hasattr(module, 'algorithm') and isinstance(module.algorithm, Algorithm):
            algorithm = module.algorithm
            logger.info("Found algorithm instance in module %s", mod_name)
        else:
            algo_classes = [
                cls for name, cls in module.__dict__.items()
                if isinstance(cls, type) and issubclass(cls, Algorithm) and cls is not Algorithm
            ]
            if algo_classes:
                algorithm = algo_classes[0]()
                logger.info("Created algorithm instance from class %s", algo_classes[0].__name__)
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
                    logger.info("Created function wrapper algorithm for module %s", mod_name)

        if algorithm:
            # Set up algorithm with interface to communicate back to ScriptManager/Doyen
            algorithm.algo_id = algo_id
            # Create a servicer instance for this algorithm to use
            algorithm.interface = AlgorithmInterface(algorithm.algo_id, servicer.client)
            methods = [name for name, obj in algorithm.__class__.__dict__.items()
                       if callable(obj) and not name.startswith('_')]
            logger.info("Loaded algorithm %s with methods: %s", mod_name, ', '.join(methods))
            return algorithm
        else:
            logger.warning("No valid algorithm found in module %s", mod_name)
            return None
    except Exception as e:
        logger.error("Error loading algorithm from %s: %s", path, e)
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
            logger.error("Error sending order: %s", e)
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
            logger.error("Error cancelling order: %s", e)
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
            logger.error("Error subscribing to symbol: %s", e)
            return {"success": False, "reason": str(e)}
    
    def get_order_status(self, order_id: str, exchange: str, simulated: bool = False):
        """Get the current status of an order"""
        try:
            algo_exchange = self.get_algo_exchange(exchange)
            request = algos_pb2.OrderStatusRequest(
                algoId=self.algo_id,
                orderId=order_id,
                exchange=algo_exchange,
                simulated=simulated
            )
            response = self.client.OrderStatus(request)
            return response
        except Exception as e:
            logger.error("Error getting order status: %s", e)
            return None
    
    def get_account_balance(self, exchange: str, symbol: str):
        """Get account balance for a symbol pair"""
        try:
            algo_exchange = self.get_algo_exchange(exchange)
            request = algos_pb2.AccountBalanceRequest(
                algoId=self.algo_id,
                exchange=algo_exchange,
                symbol=symbol
            )
            response = self.client.AccountBalance(request)
            return response
        except Exception as e:
            logger.error("Error getting account balance: %s", e)
            return None
    
    def get_all_orders(self, exchange: str, simulated: bool = False):
        """Get all orders for the algorithm on a specific exchange"""
        try:
            algo_exchange = self.get_algo_exchange(exchange)
            request = algos_pb2.GetAllOrdersRequest(
                algoId=self.algo_id,
                exchange=algo_exchange,
                simulated=simulated
            )
            response = self.client.GetAllOrders(request)
            return response
        except Exception as e:
            logger.error("Error getting all orders: %s", e)
            return None
    
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
    logger.info("gRPC server started %s", server_address)
    logger.info("gRPC client started %s", client_address)
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        await server.stop(0)
        logger.info("gRPC server stopped")
        sys.exit(0)
    except Exception as e:
        logger.error("gRPC server terminated unexpectedly: %s", e)
        sys.exit(1)
    # If wait_for_termination returns without exception, exit as well
    logger.info("gRPC server terminated, exiting script.")
    sys.exit(0)

async def message_processing_loop():
    """
    Continuously process messages in a non-blocking way.
    This simulates a busy loop that can receive and process messages from various sources.
    """
    logger.info("Starting message processing loop...")
    
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
            logger.info("Message processing loop cancelled")
            break
        except Exception as e:
            logger.error("Error in message processing loop: %s", e)
            # Don't break the loop on error, just log and continue
            await asyncio.sleep(1)  # Longer pause after an error

async def main(server, client):
    """Main function to start both the gRPC server and message processing"""
    logger.info("Starting Doyen Script Manager...")
    
    # Start the gRPC server
    server_task = asyncio.create_task(start_grpc_server(server, client))
    
    # Start the message processing loop
    message_task = asyncio.create_task(message_processing_loop())
    
    # Wait for all tasks
    try:
        await asyncio.gather(server_task, message_task)
    except asyncio.CancelledError:
        logger.info("Main tasks cancelled")
    except Exception as e:
        logger.error("Error in main tasks: %s", e)
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
        logging.error("Error: grpcio package is not installed.")
        logging.info("Installing required packages...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools"])


    # Run the async main function
    try:
        parser = argparse.ArgumentParser(description="Doyen Algorithm Script Manager")
        parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
        parser.add_argument("--server", type=str, default="localhost:5050", help="Address to run the gRPC server on")
        parser.add_argument("--client", type=str, default="localhost:5051", help="Address to run the gRPC client on")
        args = parser.parse_args()

        # Configure logging based on verbose flag
        if args.verbose:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        else:
            # Configure logging to only show critical errors (or effectively silence it)
            logging.basicConfig(
                level=logging.CRITICAL,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

        asyncio.run(main(args.server, args.client))
    except KeyboardInterrupt:
        logger.info("Script manager terminated by user")
    except Exception as e:
        logger.error("Fatal error: %s", e)