using Doyen.gRPC.Algorithms;
using Doyen.Scripts.AlgorithmSharp.API;
using System.Text.Json;

namespace Doyen.Scripts.AlgorithmsSharp
{
    /// <summary>
    /// Example algorithm that demonstrates basic functionality
    /// </summary>
    public class ExampleAlgorithm : Algorithm
    {
        private bool _isRunning = false;

        public ExampleAlgorithm() : base("ExampleAlgorithm")
        {
            JsonSchema = new ScriptSettingsModel()
            {
                Title = "ExampleAlgorithm",
                Description = "Example algorithm settings",
                Properties = new Dictionary<string, ScriptSettingsPropertyModel>()
                {
                    {
                        "symbol",
                        new ScriptSettingsPropertyModel {
                            Title = "Symbol",
                            Description = "Trading symbol to monitor",
                            TypeName = "string",
                            Options = "e.g. BTC-USD, ETH-USD",
                            Value = "BTC-USD"
                        }
                    },
                    {
                        "exchange",
                        new ScriptSettingsPropertyModel {
                            Title = "Exchange",
                            Description = "Exchange to use",
                            TypeName = "string",
                            Options = "e.g. COINBASE, BINANCEUS, KRAKEN",
                            Value = "COINBASE"
                        }
                    },
                    {
                        "quantity",
                        new ScriptSettingsPropertyModel {
                            Title = "Quantity",
                            Description = "Order quantity",
                            TypeName = "number",
                            Options = "e.g. 0.001, 0.01, 0.1",
                            Value = 0.001
                        }
                    }
                }
            };
        }

        public override string GetDisplayName()
        {
            return "Example Trading Algorithm";
        }

        public override string GetDescription()
        {
            return "A simple example algorithm that demonstrates basic functionality including market data processing and order management. This algorithm subscribes to symbol data and logs incoming trades, candlesticks, and depth of book updates.";
        }

        public override string GetVersion()
        {
            return "1.0.0";
        }

        public override string GetAuthor()
        {
            return "Doyen @ 1130 Lab";
        }

        public override string[] GetTags()
        {
            return new[] { "example", "demo", "basic", "tutorial" };
        }

        public override string GetOptionsSchema()
        {
            return JsonSerializer.Serialize(new
            {
                type = "object",
                properties = new
                {
                    symbol = new
                    {
                        type = "string",
                        title = "Symbol",
                        description = "Trading symbol to monitor",
                        @default = "BTC-USD"
                    },
                    exchange = new
                    {
                        type = "string",
                        title = "Exchange",
                        description = "Exchange to use",
                        @default = "COINBASE",
                        @enum = new[] { "COINBASE", "BINANCEUS", "KRAKEN" }
                    },
                    quantity = new
                    {
                        type = "number",
                        title = "Quantity",
                        description = "Order quantity",
                        @default = 0.001,
                        minimum = 0.0001
                    }
                },
                required = new[] { "symbol", "exchange" }
            }, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
        }

        public override bool Start(ScriptSettingsModel options)
        {
            try
            {
                _isRunning = true;

                Console.WriteLine($"Starting {Name} with options:");
                foreach (var kvp in options.Properties)
                {
                    Console.WriteLine($"  {kvp.Key}: {kvp.Value.Value}");
                }

                // Subscribe to symbol data if interface is available
                if (Interface != null &&
                    options.Properties.TryGetValue("symbol", out var symbolProp) &&
                    options.Properties.TryGetValue("exchange", out var exchangeProp))
                {
                    var symbol = symbolProp.Value?.ToString() ?? "BTC-USD";
                    var exchange = exchangeProp.Value?.ToString() ?? "COINBASE";

                    Task.Run(async () =>
                    {
                        try
                        {
                            var response = await Interface.SubscribeSymbolAsync(
                                symbol, 
                                exchange, 
                                getHistorical: true, 
                                depthLevels: 5,
                                candlesTimeframe: Doyen.gRPC.Common.Timeframe.FiveMinutes
                            );

                            if (response?.Success == true)
                            {
                                Console.WriteLine($"Successfully subscribed to {symbol} on {exchange}");
                            }
                            else
                            {
                                Console.WriteLine($"Failed to subscribe to {symbol} on {exchange}: {response?.Reason}");
                            }
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine($"Error subscribing to symbol: {ex.Message}");
                        }
                    });
                }

                return true;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error starting {Name}: {ex.Message}");
                return false;
            }
        }

        public override void Pause()
        {
            Console.WriteLine($"{Name} paused");
        }

        public override void Resume()
        {
            Console.WriteLine($"{Name} resumed");
        }

        public override void Stop()
        {
            _isRunning = false;
            Console.WriteLine($"{Name} stopped");
        }

        public override void ProcessTrade(IEnumerable<TradeMessage> trades)
        {
            if (!_isRunning) return;

            foreach (var trade in trades)
            {
                // Use TradeSide instead of Side
                var side = trade.Side; // This is now TradeSide
                Console.WriteLine($"Trade received: {trade.Symbol} @ {trade.Price} x {trade.Quantity} on {trade.Exchange} (Side: {side})");
            }
        }

        public override void ProcessCandle(IEnumerable<CandlestickMessage> candles)
        {
            if (!_isRunning) return;

            foreach (var candle in candles)
            {
                var candlestick = candle.Candlestick;
                Console.WriteLine($"Candle received: {candlestick.Symbol} OHLC({candlestick.Open}, {candlestick.High}, {candlestick.Low}, {candlestick.Close}) on {candlestick.Exchange}");
            }
        }

        public override void ProcessDepthOfBook(DepthOfBookMessage depthOfBook)
        {
            if (!_isRunning) return;

            Console.WriteLine($"Depth of Book received: {depthOfBook.Symbol} with {depthOfBook.BidLevels.Count} bids and {depthOfBook.OfferLevels.Count} offers");
        }

        public override void ProcessOrderStatus(OrderStatusUpdateMessage orderStatus)
        {
            if (!_isRunning) return;

            Console.WriteLine($"Order status update: {orderStatus.OrderId} -> {orderStatus.Status} (Filled: {orderStatus.FilledQuantity})");
        }
    }
}