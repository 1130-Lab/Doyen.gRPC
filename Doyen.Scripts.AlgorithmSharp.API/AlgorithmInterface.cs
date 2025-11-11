using Doyen.gRPC.Algorithms;
using Doyen.gRPC.Common;
using Google.Protobuf.WellKnownTypes;

namespace Doyen.Scripts.AlgorithmSharp.API
{
    /// <summary>
    /// Interface for algorithms to interact with Doyen
    /// </summary>
    public interface IAlgorithmInterface
    {
        Task<SendOrderResponse?> SendOrderAsync(string symbol, DoyenExchange exchange, double price, double quantity, 
            OrderSide orderSide, OrderType orderType, ulong? messageId = null, bool simulated = false);
        
        Task<CancelOrderResponse?> CancelOrderAsync(string orderId, ulong? messageId = null, bool simulated = false);
        
        Task<SymbolDataResponse?> SubscribeSymbolAsync(string symbol, DoyenExchange exchange, bool getHistorical = false, 
            int depthLevels = 10, Doyen.gRPC.Common.Timeframe candlesTimeframe = Doyen.gRPC.Common.Timeframe.FiveMinutes);

        Task<OrderStatusResponse?> GetOrderStatusAsync(string orderId, DoyenExchange exchange, bool simulated = false);

        Task<AccountBalanceResponse?> GetAccountBalanceAsync(DoyenExchange exchange, string symbol);

        Task<GetAllOrdersResponse?> GetAllOrdersAsync(DoyenExchange exchange, bool simulated = false);
    }

    /// <summary>
    /// Clean interface for algorithms to interact with Doyen via gRPC
    /// </summary>
    public class AlgorithmInterface : IAlgorithmInterface
    {
        private readonly string _algoId;
        private readonly AlgorithmServer.AlgorithmServerClient _client;

        public AlgorithmInterface(string algoId, AlgorithmServer.AlgorithmServerClient client)
        {
            _algoId = algoId;
            _client = client;
        }

        /// <summary>
        /// Send an order - handles protobuf message creation internally
        /// </summary>
        public async Task<SendOrderResponse?> SendOrderAsync(string symbol, DoyenExchange exchange, double price, double quantity,
            OrderSide orderSide, OrderType orderType, ulong? messageId = null, bool simulated = false)
        {
            messageId ??= GenerateMessageId();

            try
            {
                var request = new SendOrderRequest
                {
                    AlgoId = _algoId,
                    MessageId = messageId.Value,
                    Symbol = symbol,
                    Exchange = exchange,
                    Price = price,
                    Quantity = quantity,
                    Simulated = simulated,
                    OrderSide = orderSide,
                    OrderType = orderType
                };

                var response = await _client.SendOrderAsync(request);
                return response;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error sending order: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Cancel an order - handles protobuf message creation internally
        /// </summary>
        public async Task<CancelOrderResponse?> CancelOrderAsync(string orderId, ulong? messageId = null, bool simulated = false)
        {
            messageId ??= GenerateMessageId();

            try
            {
                var request = new CancelOrderRequest
                {
                    AlgoId = _algoId,
                    MessageId = messageId.Value,
                    OrderId = orderId,
                    Simulated = simulated
                };

                var response = await _client.CancelOrderAsync(request);
                return response;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error cancelling order: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Subscribe to symbol data - handles protobuf message creation internally
        /// </summary>
        public async Task<SymbolDataResponse?> SubscribeSymbolAsync(string symbol, DoyenExchange exchange, bool getHistorical = false,
            int depthLevels = 10, Doyen.gRPC.Common.Timeframe candlesTimeframe = Doyen.gRPC.Common.Timeframe.FiveMinutes)
        {
            try
            {
                var request = new SymbolDataRequest
                {
                    AlgoId = _algoId,
                    Symbol = symbol,
                    Exchange = exchange,
                    GetHistorical = getHistorical,
                    DepthOfBookLevels = depthLevels,
                    CandlesTimeframe = candlesTimeframe
                };

                var response = await _client.SubscribeSymbolAsync(request);
                return response;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error subscribing to symbol: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Get the current status of an order
        /// </summary>
        public async Task<OrderStatusResponse?> GetOrderStatusAsync(string orderId, DoyenExchange exchange, bool simulated = false)
        {
            try
            {
                var request = new OrderStatusRequest
                {
                    AlgoId = _algoId,
                    OrderId = orderId,
                    Exchange = exchange,
                    Simulated = simulated
                };

                var response = await _client.OrderStatusAsync(request);
                return response;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error getting order status: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Get account balance for a symbol pair
        /// </summary>
        public async Task<AccountBalanceResponse?> GetAccountBalanceAsync(DoyenExchange exchange, string symbol)
        {
            try
            {
                var request = new AccountBalanceRequest
                {
                    AlgoId = _algoId,
                    Exchange = exchange,
                    Symbol = symbol
                };

                var response = await _client.AccountBalanceAsync(request);
                return response;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error getting account balance: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Get all orders for the algorithm on a specific exchange
        /// </summary>
        public async Task<GetAllOrdersResponse?> GetAllOrdersAsync(DoyenExchange exchange, bool simulated = false)
        {
            try
            {
                var request = new GetAllOrdersRequest
                {
                    AlgoId = _algoId,
                    Exchange = exchange,
                    Simulated = simulated
                };

                var response = await _client.GetAllOrdersAsync(request);
                return response;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error getting all orders: {ex.Message}");
                return null;
            }
        }

        private static ulong GenerateMessageId()
        {
            return (ulong)(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() * 1000 + Random.Shared.Next(1000));
        }

        public static DoyenExchange GetAlgoExchange(string name)
        {
            var exchangeName = $"Exchange{name.ToUpperInvariant()}";
            return System.Enum.TryParse<DoyenExchange>(exchangeName, true, out var exchange) ? exchange : DoyenExchange.ExchangeUnknown;
        }

        public static OrderSide GetAlgoOrderSide(string side)
        {
            return System.Enum.TryParse<OrderSide>(side, true, out var orderSide) ? orderSide : OrderSide.Unknown;
        }

        public static OrderType GetAlgoOrderType(string orderType)
        {
            return System.Enum.TryParse<OrderType>(orderType, true, out var type) ? type : OrderType.Unknown;
        }
    }
}