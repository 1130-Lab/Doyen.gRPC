using Doyen.gRPC.Algorithms;
using Grpc.Core;
using System.Collections.Concurrent;
using System.Reflection;
using System.Text.Json;
using Serilog;

namespace Doyen.Scripts.AlgorithmSharp.API
{
    /// <summary>
    /// gRPC service implementation for handling algorithm management and data flow
    /// </summary>
    public class AlgorithmScriptManager : AlgorithmServer.AlgorithmServerBase
    {
        private readonly ConcurrentDictionary<string, AlgorithmContext> _activeAlgorithms = new();
        private readonly AlgorithmServer.AlgorithmServerClient _client;

        public AlgorithmScriptManager(AlgorithmServer.AlgorithmServerClient client)
        {
            _client = client;
        }

        #region Doyen → Script services (Doyen calls these on our server)

        /// <summary>
        /// Handle algorithm initialization request from Doyen
        /// </summary>
        public override Task<InitializeAlgorithmResponse> InitializeAlgorithm(
            InitializeAlgorithmRequest request, ServerCallContext context)
        {
            Log.Logger.Information("Initializing algorithm: {Name} (ID: {AlgoId})", request.Name, request.AlgoId);

            try
            {
                var algorithm = LoadAlgorithmAsync(request.AlgoId, request.Name);
                if (algorithm == null)
                {
                    Log.Logger.Warning("Failed to load algorithm: {Name}", request.Name);
                    return Task.FromResult(new InitializeAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = "Failed to load algorithm",
                        ListenDepthOfBook = false,
                        ListenTrades = false,
                        ListenCandlesticks = false,
                        HasOptionsPanel = false
                    });
                }

                var algoContext = new AlgorithmContext(request.AlgoId, request.Name, algorithm);
                _activeAlgorithms[request.AlgoId] = algoContext;
                algorithm.AlgoId = request.AlgoId;

                // Get algorithm capabilities
                string optionsJson = "";
                bool hasOptions = false;
                try
                {
                    optionsJson = algorithm.GetOptionsSchema();
                    hasOptions = !string.IsNullOrEmpty(optionsJson) && optionsJson != "{}";
                }
                catch (Exception ex)
                {
                    Log.Logger.Error(ex, "Error getting options schema for algorithm {AlgoId}", request.AlgoId);
                }

                // Determine what data types the algorithm wants to listen to
                var listenDob = HasMethod(algorithm, nameof(Algorithm.ProcessDepthOfBook));
                var listenTrades = HasMethod(algorithm, nameof(Algorithm.ProcessTrade));
                var listenCandles = HasMethod(algorithm, nameof(Algorithm.ProcessCandle));

                Log.Logger.Information("Successfully initialized algorithm {Name} with ID {AlgoId}", request.Name, request.AlgoId);

                return Task.FromResult(new InitializeAlgorithmResponse
                {
                    AlgoId = request.AlgoId,
                    Success = true,
                    Reason = "",
                    ListenDepthOfBook = listenDob,
                    ListenTrades = listenTrades,
                    ListenCandlesticks = listenCandles,
                    HasOptionsPanel = hasOptions,
                    OptionsJsonDataRequest = optionsJson
                });
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error initializing algorithm {AlgoId}", request.AlgoId);
                return Task.FromResult(new InitializeAlgorithmResponse
                {
                    AlgoId = request.AlgoId,
                    Success = false,
                    Reason = ex.Message,
                    ListenDepthOfBook = false,
                    ListenTrades = false,
                    ListenCandlesticks = false,
                    HasOptionsPanel = false
                });
            }
        }

        /// <summary>
        /// Handle algorithm start request from Doyen
        /// </summary>
        public override async Task<StartAlgorithmResponse> StartAlgorithm(
            StartAlgorithmRequest request, ServerCallContext context)
        {
            Log.Logger.Information("Starting algorithm: {AlgoId}", request.AlgoId);

            try
            {
                if (!_activeAlgorithms.TryGetValue(request.AlgoId, out var algoContext))
                {
                    Log.Logger.Warning("Algorithm not found: {AlgoId}", request.AlgoId);
                    return new StartAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = "Algorithm not initialized"
                    };
                }

                var algorithm = algoContext.Algorithm!;
                ScriptSettingsModel? settingsModel = null;
                if (!string.IsNullOrEmpty(request.OptionsJsonDataResponse))
                {
                    try
                    {
                        settingsModel = JsonSerializer.Deserialize<ScriptSettingsModel>(request.OptionsJsonDataResponse);
                        // Store configuration
                        algoContext.Configuration = request.OptionsJsonDataResponse;
                    }
                    catch (JsonException ex)
                    {
                        Log.Logger.Error(ex, "Invalid options JSON for algorithm {AlgoId}", request.AlgoId);
                    }
                }

                try
                {
                    var success = algorithm.Start(settingsModel ?? new ScriptSettingsModel { Title = "", Description = "", Properties = new Dictionary<string, ScriptSettingsPropertyModel>() });
                    if (!success)
                    {
                        return new StartAlgorithmResponse
                        {
                            AlgoId = request.AlgoId,
                            Success = false,
                            Reason = "Algorithm start function returned failure"
                        };
                    }

                    // Set state to Running
                    algoContext.State = AlgorithmState.Running;

                    Log.Logger.Information("Successfully started algorithm {AlgoId}", request.AlgoId);
                    return new StartAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = true,
                        Reason = ""
                    };
                }
                catch (Exception ex)
                {
                    Log.Logger.Error(ex, "Error starting algorithm {AlgoId}", request.AlgoId);
                    return new StartAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = $"Error in start function: {ex.Message}"
                    };
                }
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error starting algorithm {AlgoId}", request.AlgoId);
                return new StartAlgorithmResponse
                {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = ex.Message
                };
            }
        }

        /// <summary>
        /// Handle algorithm pause request from Doyen
        /// </summary>
        public override async Task<PauseAlgorithmResponse> PauseAlgorithm(
            PauseAlgorithmRequest request, ServerCallContext context)
        {
            Log.Logger.Information("Pausing algorithm: {AlgoId}", request.AlgoId);

            try
            {
                if (!_activeAlgorithms.TryGetValue(request.AlgoId, out var algoContext))
                {
                    Log.Logger.Warning("Algorithm not found: {AlgoId}", request.AlgoId);
                    return new PauseAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = "Algorithm not initialized"
                    };
                }

                var algorithm = algoContext.Algorithm!;
                try
                {
                    algorithm.Pause();
                    // Set state to Paused
                    algoContext.State = AlgorithmState.Paused;
                    Log.Logger.Information("Successfully paused algorithm {AlgoId}", request.AlgoId);
                    return new PauseAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = true,
                        Reason = ""
                    };
                }
                catch (Exception ex)
                {
                    Log.Logger.Error(ex, "Error pausing algorithm {AlgoId}", request.AlgoId);
                    return new PauseAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = $"Error in pause function: {ex.Message}"
                    };
                }
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error pausing algorithm {AlgoId}", request.AlgoId);
                return new PauseAlgorithmResponse
                {
                    AlgoId = request.AlgoId,
                    Success = false,
                    Reason = ex.Message
                };
            }
        }

        /// <summary>
        /// Handle algorithm resume request from Doyen
        /// </summary>
        public override async Task<ResumeAlgorithmResponse> ResumeAlgorithm(
            ResumeAlgorithmRequest request, ServerCallContext context)
        {
            Log.Logger.Information("Resuming algorithm: {AlgoId}", request.AlgoId);

            try
            {
                if (!_activeAlgorithms.TryGetValue(request.AlgoId, out var algoContext))
                {
                    Log.Logger.Warning("Algorithm not found: {AlgoId}", request.AlgoId);
                    return new ResumeAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = "Algorithm not initialized"
                    };
                }

                var algorithm = algoContext.Algorithm!;
                try
                {
                    algorithm.Resume();
                    // Set state back to Running
                    algoContext.State = AlgorithmState.Running;
                    Log.Logger.Information("Successfully resumed algorithm {AlgoId}", request.AlgoId);
                    return new ResumeAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = true,
                        Reason = ""
                    };
                }
                catch (Exception ex)
                {
                    Log.Logger.Error(ex, "Error resuming algorithm {AlgoId}", request.AlgoId);
                    return new ResumeAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = $"Error in resume function: {ex.Message}"
                    };
                }
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error resuming algorithm {AlgoId}", request.AlgoId);
                return new ResumeAlgorithmResponse
                {
                    AlgoId = request.AlgoId,
                    Success = false,
                    Reason = ex.Message
                };
            }
        }

        /// <summary>
        /// Handle algorithm stop request from Doyen
        /// </summary>
        public override async Task<StopAlgorithmResponse> StopAlgorithm(
            StopAlgorithmRequest request, ServerCallContext context)
        {
            Log.Logger.Information("Stopping algorithm: {AlgoId}", request.AlgoId);

            try
            {
                if (!_activeAlgorithms.TryGetValue(request.AlgoId, out var algoContext))
                {
                    Log.Logger.Warning("Algorithm not found: {AlgoId}", request.AlgoId);
                    return new StopAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = "Algorithm not initialized"
                    };
                }

                var algorithm = algoContext.Algorithm!;
                try
                {
                    algorithm.Stop();
                    // Set state to Stopped, then remove
                    algoContext.State = AlgorithmState.Stopped;
                    _activeAlgorithms.TryRemove(request.AlgoId, out _);
                    Log.Logger.Information("Successfully stopped algorithm {AlgoId}", request.AlgoId);
                    return new StopAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = true,
                        Reason = ""
                    };
                }
                catch (Exception ex)
                {
                    Log.Logger.Error(ex, "Error stopping algorithm {AlgoId}", request.AlgoId);
                    return new StopAlgorithmResponse
                    {
                        AlgoId = request.AlgoId,
                        Success = false,
                        Reason = $"Error in stop function: {ex.Message}"
                    };
                }
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error stopping algorithm {AlgoId}", request.AlgoId);
                return new StopAlgorithmResponse
                {
                    AlgoId = request.AlgoId,
                    Success = false,
                    Reason = ex.Message
                };
            }
        }

        #endregion

        #region Data handling services

        /// <summary>
        /// Handle incoming trade data and forward to algorithms
        /// </summary>
        public override async Task<TradeAck> TradeData(TradeMessage request, ServerCallContext context)
        {
            try
            {
                foreach (var (algoId, algoContext) in _activeAlgorithms)
                {
                    var algorithm = algoContext.Algorithm;
                    if (algorithm != null && HasMethod(algorithm, nameof(Algorithm.ProcessTrade)))
                    {
                        try
                        {
                            // If you use trade side in your logic, use TradeSide instead of Side
                            algorithm.ProcessTrade(new[] { request });
                        }
                        catch (Exception ex)
                        {
                            Log.Logger.Error(ex, "Error processing trade data in algorithm {AlgoId}", algoId);
                        }
                    }
                }
                return new TradeAck { Id = request.Id };
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error handling trade data");
                return new TradeAck { Id = request.Id };
            }
        }

        /// <summary>
        /// Handle incoming candlestick data and forward to algorithms
        /// </summary>
        public override async Task<CandlestickAck> CandlestickData(CandlestickMessage request, ServerCallContext context)
        {
            try
            {
                foreach (var (algoId, algoContext) in _activeAlgorithms)
                {
                    var algorithm = algoContext.Algorithm;
                    if (algorithm != null && HasMethod(algorithm, nameof(Algorithm.ProcessCandle)))
                    {
                        try
                        {
                            algorithm.ProcessCandle(new[] { request });
                        }
                        catch (Exception ex)
                        {
                            Log.Logger.Error(ex, "Error processing candlestick data in algorithm {AlgoId}", algoId);
                        }
                    }
                }
                return new CandlestickAck { Id = request.Id };
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error handling candlestick data");
                return new CandlestickAck { Id = request.Id };
            }
        }

        /// <summary>
        /// Handle incoming depth of book data and forward to algorithms
        /// </summary>
        public override async Task<DepthOfBookAck> DepthOfBookData(DepthOfBookMessage request, ServerCallContext context)
        {
            try
            {
                foreach (var (algoId, algoContext) in _activeAlgorithms)
                {
                    var algorithm = algoContext.Algorithm;
                    if (algorithm != null && HasMethod(algorithm, nameof(Algorithm.ProcessDepthOfBook)))
                    {
                        try
                        {
                            algorithm.ProcessDepthOfBook(request);
                        }
                        catch (Exception ex)
                        {
                            Log.Logger.Error(ex, "Error processing depth of book data in algorithm {AlgoId}", algoId);
                        }
                    }
                }
                return new DepthOfBookAck { Id = request.Id };
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error handling depth of book data");
                return new DepthOfBookAck { Id = request.Id };
            }
        }

        /// <summary>
        /// Handle order status updates and forward to algorithms
        /// </summary>
        public override async Task<OrderStatusUpdateAck> OrderStatusUpdate(OrderStatusUpdateMessage request, ServerCallContext context)
        {
            try
            {
                if (_activeAlgorithms.TryGetValue(request.AlgoId, out var algoContext))
                {
                    var algorithm = algoContext.Algorithm;
                    if (algorithm != null && HasMethod(algorithm, nameof(Algorithm.ProcessOrderStatus)))
                    {
                        try
                        {
                            algorithm.ProcessOrderStatus(request);
                        }
                        catch (Exception ex)
                        {
                            Log.Logger.Error(ex, "Error processing order status update in algorithm {AlgoId}", request.AlgoId);
                        }
                    }
                }
                return new OrderStatusUpdateAck
                {
                    AlgoId = request.AlgoId,
                    MessageId = request.MessageId
                };
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error handling order status update");
                return new OrderStatusUpdateAck
                {
                    AlgoId = request.AlgoId,
                    MessageId = request.MessageId
                };
            }
        }

        #endregion

        #region Algorithm Discovery Services

        /// <summary>
        /// Handle request to list all available algorithms
        /// </summary>
        public override Task<ListAvailableAlgorithmsResponse> ListAvailableAlgorithms(
            ListAvailableAlgorithmsRequest request, ServerCallContext context)
        {
            Log.Logger.Information("Listing available algorithms with filter: '{NameFilter}'", request.NameFilter);

            try
            {
                var algorithmInfos = new List<AlgorithmInfo>();

                // Get all loaded assemblies except system/default ones
                var assemblies = AppDomain.CurrentDomain.GetAssemblies()
                    .Where(a => !(a.FullName?.StartsWith("System") ?? false)
                             && !(a.FullName?.StartsWith("Microsoft") ?? false)
                             && !(a.IsDynamic)
                             && !(a.FullName?.StartsWith("netstandard") ?? false)
                             && !(a.FullName?.StartsWith("WindowsBase") ?? false)
                             && !(a.FullName?.StartsWith("Presentation") ?? false)
                             && !(a.FullName?.StartsWith("mscorlib") ?? false)
                             && !(a.FullName?.StartsWith("Accessibility") ?? false)
                             && !(a.FullName?.StartsWith("NUnit") ?? false)
                             && !(a.FullName?.StartsWith("xunit") ?? false)
                             && !(a.FullName?.StartsWith("Mono") ?? false)
                    ).ToList();

                foreach (var assembly in assemblies)
                {
                    try
                    {
                        var algorithmTypes = assembly.GetTypes()
                            .Where(t => t.IsSubclassOf(typeof(Algorithm)) && !t.IsAbstract)
                            .ToList();

                        foreach (var algorithmType in algorithmTypes)
                        {
                            try
                            {
                                var algorithmName = algorithmType.Name;
                                
                                // Apply name filter if provided
                                if (!string.IsNullOrEmpty(request.NameFilter) &&
                                    !algorithmName.Contains(request.NameFilter, StringComparison.OrdinalIgnoreCase))
                                {
                                    continue;
                                }

                                // Create a temporary instance to get metadata
                                var tempAlgorithm = (Algorithm?)Activator.CreateInstance(algorithmType);
                                if (tempAlgorithm != null)
                                {
                                    var optionsSchema = "";
                                    var hasOptions = false;
                                    try
                                    {
                                        optionsSchema = tempAlgorithm.GetOptionsSchema();
                                        hasOptions = !string.IsNullOrEmpty(optionsSchema) && optionsSchema != "{}";
                                    }
                                    catch (Exception ex)
                                    {
                                        Log.Logger.Error(ex, "Error getting options schema for {AlgorithmName}", algorithmName);
                                    }

                                    var algorithmInfo = new AlgorithmInfo
                                    {
                                        Name = algorithmName,
                                        DisplayName = tempAlgorithm.GetDisplayName(),
                                        Description = tempAlgorithm.GetDescription(),
                                        Version = tempAlgorithm.GetVersion(),
                                        Author = tempAlgorithm.GetAuthor(),
                                        HasOptionsPanel = hasOptions,
                                        OptionsSchema = optionsSchema
                                    };

                                    // Add tags
                                    algorithmInfo.Tags.AddRange(tempAlgorithm.GetTags());

                                    algorithmInfos.Add(algorithmInfo);
                                    Log.Logger.Information("Found algorithm: {AlgorithmName} from assembly {AssemblyName}", algorithmName, assembly.GetName().Name);
                                }
                            }
                            catch (Exception ex)
                            {
                                Log.Logger.Error(ex, "Error processing algorithm type {AlgorithmTypeName}", algorithmType.Name);
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        Log.Logger.Error(ex, "Error processing assembly {AssemblyName}", assembly.GetName().Name);
                    }
                }

                Log.Logger.Information("Found {AlgorithmCount} available algorithms", algorithmInfos.Count);

                return Task.FromResult(new ListAvailableAlgorithmsResponse
                {
                    Success = true,
                    Reason = "",
                    Algorithms = { algorithmInfos }
                });
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error listing available algorithms");
                return Task.FromResult(new ListAvailableAlgorithmsResponse
                {
                    Success = false,
                    Reason = ex.Message,
                    Algorithms = { }
                });
            }
        }

        /// <summary>
        /// Handle request to list all currently running or paused algorithms
        /// </summary>
        public override Task<ListRunningAlgorithmsResponse> ListRunningAlgorithms(
            ListRunningAlgorithmsRequest request, ServerCallContext context)
        {
            Log.Logger.Information("Listing running algorithms with filter: '{NameFilter}'", request.NameFilter);

            try
            {
                var runningAlgorithmInfos = new List<RunningAlgorithmInfo>();

                // Filter active algorithms that are Running or Paused
                foreach (var (algoId, algoContext) in _activeAlgorithms)
                {
                    if (algoContext.State != AlgorithmState.Running && algoContext.State != AlgorithmState.Paused)
                    {
                        continue;
                    }

                    // Apply name filter if provided
                    if (!string.IsNullOrEmpty(request.NameFilter) &&
                        !algoContext.Name.Contains(request.NameFilter, StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    var algorithm = algoContext.Algorithm;
                    if (algorithm != null)
                    {
                        try
                        {
                            var optionsSchema = "";
                            var hasOptions = false;
                            try
                            {
                                optionsSchema = algorithm.GetOptionsSchema();
                                hasOptions = !string.IsNullOrEmpty(optionsSchema) && optionsSchema != "{}";
                            }
                            catch (Exception ex)
                            {
                                Log.Logger.Error(ex, "Error getting options schema for {AlgorithmName}", algoContext.Name);
                            }

                            var algorithmInfo = new AlgorithmInfo
                            {
                                Name = algoContext.Name,
                                DisplayName = algorithm.GetDisplayName(),
                                Description = algorithm.GetDescription(),
                                Version = algorithm.GetVersion(),
                                Author = algorithm.GetAuthor(),
                                HasOptionsPanel = hasOptions,
                                OptionsSchema = optionsSchema
                            };

                            // Add tags
                            algorithmInfo.Tags.AddRange(algorithm.GetTags());

                            var runningInfo = new RunningAlgorithmInfo
                            {
                                Info = algorithmInfo,
                                AlgoId = algoId,
                                Configuration = algoContext.Configuration ?? "{}"
                            };

                            runningAlgorithmInfos.Add(runningInfo);
                            Log.Logger.Information("Found running algorithm: {AlgorithmName} (ID: {AlgoId}, State: {State})", algoContext.Name, algoId, algoContext.State);
                        }
                        catch (Exception ex)
                        {
                            Log.Logger.Error(ex, "Error processing running algorithm {AlgorithmName}", algoContext.Name);
                        }
                    }
                }

                Log.Logger.Information("Found {AlgorithmCount} running algorithms", runningAlgorithmInfos.Count);

                return Task.FromResult(new ListRunningAlgorithmsResponse
                {
                    Success = true,
                    Reason = "",
                    Algorithms = { runningAlgorithmInfos }
                });
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error listing running algorithms");
                return Task.FromResult(new ListRunningAlgorithmsResponse
                {
                    Success = false,
                    Reason = ex.Message,
                    Algorithms = { }
                });
            }
        }

        #endregion

        #region Helper methods

        /// <summary>
        /// Load algorithm from all loaded non-default assemblies
        /// </summary>
        private Algorithm? LoadAlgorithmAsync(string algoId, string name)
        {
            try
            {
                // Get all loaded assemblies except system/default ones
                var assemblies = AppDomain.CurrentDomain.GetAssemblies()
                    .Where(a => !(a.FullName?.StartsWith("System") ?? false)
                             && !(a.FullName?.StartsWith("Microsoft") ?? false)
                             && !(a.IsDynamic)
                             && !(a.FullName?.StartsWith("netstandard") ?? false)
                             && !(a.FullName?.StartsWith("WindowsBase") ?? false)
                             && !(a.FullName?.StartsWith("Presentation") ?? false)
                             && !(a.FullName?.StartsWith("mscorlib") ?? false)
                             && !(a.FullName?.StartsWith("Accessibility") ?? false)
                             && !(a.FullName?.StartsWith("NUnit") ?? false)
                             && !(a.FullName?.StartsWith("xunit") ?? false)
                             && !(a.FullName?.StartsWith("Mono") ?? false)
                    ).ToList();

                foreach (var assembly in assemblies)
                {
                    var algorithmTypes = assembly.GetTypes()
                        .Where(t => t.IsSubclassOf(typeof(Algorithm)) && !t.IsAbstract)
                        .ToList();

                    // Try to find algorithm by name
                    var algorithmType = algorithmTypes.FirstOrDefault(t =>
                        t.Name.Equals(name, StringComparison.OrdinalIgnoreCase) ||
                        t.Name.Equals($"{name}Algorithm", StringComparison.OrdinalIgnoreCase));

                    if (algorithmType != null)
                    {
                        var algorithm = (Algorithm?)Activator.CreateInstance(algorithmType);
                        if (algorithm != null)
                        {
                            // Set up algorithm with interface to communicate back to Doyen
                            algorithm.AlgoId = algoId;
                            algorithm.Interface = new AlgorithmInterface(algoId, _client);

                            var methods = algorithmType.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                                .Where(m => !m.IsSpecialName && m.DeclaringType != typeof(object))
                                .Select(m => m.Name);

                            Log.Logger.Information("Loaded algorithm {Name} from assembly {AssemblyName} with methods: {Methods}", name, assembly.GetName().Name, string.Join(", ", methods));
                            return algorithm;
                        }
                        Log.Logger.Warning("Failed to create instance of algorithm: {Name} in assembly {AssemblyName}", name, assembly.GetName().Name);
                    }
                }

                Log.Logger.Warning("Algorithm class not found for: {Name} in any loaded assembly", name);
                return null;
            }
            catch (Exception ex)
            {
                Log.Logger.Error(ex, "Error loading algorithm {Name}", name);
                return null;
            }
        }

        /// <summary>
        /// Check if algorithm has a specific method overridden
        /// </summary>
        private static bool HasMethod(Algorithm algorithm, string methodName)
        {
            var method = algorithm.GetType().GetMethod(methodName, BindingFlags.Public | BindingFlags.Instance);
            return method != null && method.DeclaringType != typeof(Algorithm);
        }

        /// <summary>
        /// Convert JsonElement to Dictionary for options parsing
        /// </summary>
        private static Dictionary<string, object> JsonElementToDictionary(JsonElement element)
        {
            var dictionary = new Dictionary<string, object>();
            
            foreach (var property in element.EnumerateObject())
            {
                dictionary[property.Name] = property.Value.ValueKind switch
                {
                    JsonValueKind.String => property.Value.GetString() ?? "",
                    JsonValueKind.Number => property.Value.GetDouble(),
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    JsonValueKind.Object => JsonElementToDictionary(property.Value),
                    JsonValueKind.Array => property.Value.EnumerateArray().Select(JsonElementToObject).ToArray(),
                    _ => property.Value.ToString()
                };
            }
            
            return dictionary;
        }

        private static object JsonElementToObject(JsonElement element)
        {
            return element.ValueKind switch
            {
                JsonValueKind.String => element.GetString() ?? "",
                JsonValueKind.Number => element.GetDouble(),
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                JsonValueKind.Object => JsonElementToDictionary(element),
                JsonValueKind.Array => element.EnumerateArray().Select(JsonElementToObject).ToArray(),
                _ => element.ToString()
            };
        }

        #endregion
    }
}
