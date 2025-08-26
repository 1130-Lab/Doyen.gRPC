using Doyen.gRPC.Common;
using Doyen.gRPC.Indicators;
using Doyen.TestApp.Utilities;
using Google.Protobuf.WellKnownTypes;
using Grpc.Core;
using Grpc.Net.Client;
using System;
using System.Threading;
using System.Threading.Tasks;

namespace Doyen.TestApp.Services
{
    public class ChartsClientService : IDisposable
    {
        private readonly ChartsServer.ChartsServerClient _client;
        private readonly GrpcChannel _channel;
        private string _indicatorId = string.Empty;
        private CancellationTokenSource _streamingCts;
        
        // Event for data updates
        public event EventHandler<IndicatorData>? DataReceived;

        public bool IsStreaming { get; private set; }

        public ChartsClientService(string serverAddress = "http://localhost:5000")
        {
            // Configure the channel with a retry policy
            var options = new GrpcChannelOptions
            {
                MaxRetryAttempts = 3,
                MaxReceiveMessageSize = null // No limit
            };

            _channel = GrpcChannel.ForAddress(serverAddress, options);
            _client = new ChartsServer.ChartsServerClient(_channel);
            _streamingCts = new CancellationTokenSource();
        }

        public async Task<InitializeIndicatorResponse> InitializeIndicatorAsync(string name, string symbol)
        {
            try
            {
                var request = new InitializeIndicatorRequest
                {
                    Id = Guid.NewGuid().ToString(),
                    Symbol = symbol,
                    Name = name,
                };

                var response = await _client.InitializeIndicatorAsync(request);

                if(response == null)
                {
                    return new InitializeIndicatorResponse
                    {
                        Success = false,
                        Reason = "No response from server."
                    };
                }
                else if(response.Success)
                {
                    _indicatorId = response.Id;
                }

                return response;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error initializing indicator: {ex.Message}");
                return new InitializeIndicatorResponse
                {
                    Success = false,
                    Reason = $"Communication error: {ex.Message}"
                };
            }
        }

        public async Task<StartIndicatorResponse> StartIndicatorAsync(DoyenCandlestick[] historicalData, string optionsJson = "")
        {
            try
            {
                if (string.IsNullOrEmpty(_indicatorId))
                {
                    return new StartIndicatorResponse
                    {
                        Success = false,
                        Reason = "No active indicator. Please initialize an indicator first."
                    };
                }

                var request = new StartIndicatorRequest
                {
                    Id = _indicatorId,
                    OptionsJsonDataResponse = optionsJson ?? ""
                };

                if (historicalData != null)
                {
                    request.HistoricalData.AddRange(historicalData);
                }

                return await _client.StartIndicatorAsync(request);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error starting indicator: {ex.Message}");
                return new StartIndicatorResponse
                {
                    Success = false,
                    Reason = $"Communication error: {ex.Message}"
                };
            }
        }

        public async Task<StopIndicatorResponse> StopIndicatorAsync()
        {
            try
            {
                if (string.IsNullOrEmpty(_indicatorId))
                {
                    return new StopIndicatorResponse
                    {
                        Success = false,
                        Reason = "No active indicator. Please initialize an indicator first."
                    };
                }

                var request = new StopIndicatorRequest
                {
                    Id = _indicatorId
                };

                StopIndicatorResponse response = await _client.StopIndicatorAsync(request);

                if(response == null)
                {
                    return new StopIndicatorResponse
                    {
                        Success = false,
                        Reason = "No response from server."
                    };
                }

                return response;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error starting indicator: {ex.Message}");
                return new StopIndicatorResponse
                {
                    Success = false,
                    Reason = $"Communication error: {ex.Message}"
                };
            }
        }

        public async Task<IndicatorData?> ProcessDataAsync(string symbol, long timestamp, DoyenCandlestick[] candlesticks)
        {
            try
            {
                if (string.IsNullOrEmpty(_indicatorId))
                {
                    Console.WriteLine("No active indicator. Please initialize and start an indicator first.");
                    return null;
                }

                var request = new DataMessage
                {
                    Symbol = symbol,
                    Timestamp = timestamp
                };

                if (candlesticks != null)
                {
                    request.Candlesticks.AddRange(candlesticks);
                }

                // ProcessData returns a server stream, so we need to handle the streaming response
                using var call = _client.ProcessData(request);
                
                // Read the first response from the stream
                if (await call.ResponseStream.MoveNext(_streamingCts.Token))
                {
                    var response = call.ResponseStream.Current;
                    Console.WriteLine($"Received response for symbol {symbol} at {timestamp}: {response?.Data?.DataPointId} (IID: {response.Id})");
                    return response?.Data;
                }

                return null;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error processing data: {ex.Message}");
                return null;
            }
        }

        private DoyenCandlestick? _currentCandle = null;

        public void StartContinuousDataProcessing(string symbol, double? overrideOpen = null, int intervalMs = 1000)
        {
            if (IsStreaming)
            {
                return; // Already streaming
            }

            // Reset cancellation token if needed
            if (_streamingCts.IsCancellationRequested)
            {
                _streamingCts = new CancellationTokenSource();
            }

            IsStreaming = true;

            // Start continuous processing in a background task
            Task.Run(async () =>
            {
                try
                {
                    while (!_streamingCts.Token.IsCancellationRequested)
                    {
                        // Create a new candlestick for processing with current time
                        var currentTime = DateTime.UtcNow;
                        if(_currentCandle == null)
                        {
                            _currentCandle = CandlestickHelper.CreateSampleCandlestick(currentTime, overrideOpen: overrideOpen);
                        }
                        else if (currentTime >= _currentCandle.TimeEnd.ToDateTime())
                        {
                            _currentCandle = CandlestickHelper.CreateSampleCandlestick(currentTime, overrideOpen: _currentCandle.Close);
                        }
                        else
                        {
                            // If we already have a candle, just update the end time
                            CandlestickHelper.UpdateCandlestick(_currentCandle);
                        }

                        // Process the data
                        var data = await ProcessDataAsync(
                            symbol,
                            DateTimeToUnixTimestamp(currentTime),
                            new[] { _currentCandle });

                        // Notify subscribers if data was received
                        if (data != null)
                        {
                            DataReceived?.Invoke(this, data);
                        }

                        // Wait for the next interval
                        await Task.Delay(intervalMs, _streamingCts.Token);
                    }
                }
                catch (OperationCanceledException)
                {
                    // Expected when cancellation is requested
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Error in continuous data processing: {ex.Message}");
                }
                finally
                {
                    IsStreaming = false;
                }
            }, _streamingCts.Token);
        }

        public void StopContinuousDataProcessing()
        {
            if (!IsStreaming)
            {
                return;
            }

            _streamingCts.Cancel();
            IsStreaming = false;
        }

        private long DateTimeToUnixTimestamp(DateTime dateTime)
        {
            return new DateTimeOffset(dateTime).ToUnixTimeMilliseconds();
        }

        public void Dispose()
        {
            try
            {
                StopContinuousDataProcessing();
                _streamingCts?.Dispose();
                _channel?.ShutdownAsync().Wait();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error disposing gRPC channel: {ex.Message}");
            }
        }
    }
}