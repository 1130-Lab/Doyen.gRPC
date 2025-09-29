using Doyen.gRPC.Algorithms;
using System.Text.Json;

namespace Doyen.Scripts.AlgorithmSharp.API
{
    /// <summary>
    /// Base class for all algorithms in the Doyen system
    /// </summary>
    public abstract class Algorithm
    {
        public string AlgoId { get; set; } = string.Empty;
        public string Name { get; protected set; }
        public IAlgorithmInterface? Interface { get; set; }
        protected ScriptSettingsModel? JsonSchema { get; set; }

        protected Algorithm(string name)
        {
            Name = name;
        }

        /// <summary>
        /// Get the display name for the algorithm (human-readable)
        /// </summary>
        public virtual string GetDisplayName()
        {
            return Name;
        }

        /// <summary>
        /// Get the description of the algorithm
        /// </summary>
        public virtual string GetDescription()
        {
            return "A trading algorithm";
        }

        /// <summary>
        /// Get the version of the algorithm
        /// </summary>
        public virtual string GetVersion()
        {
            return "1.0.0";
        }

        /// <summary>
        /// Get the author of the algorithm
        /// </summary>
        public virtual string GetAuthor()
        {
            return "Unknown";
        }

        /// <summary>
        /// Get tags/categories for the algorithm
        /// </summary>
        public virtual string[] GetTags()
        {
            return new string[] { "trading" };
        }

        /// <summary>
        /// Get the options schema JSON for the algorithm's configuration panel
        /// </summary>
        public virtual string GetOptionsSchema()
        {
            return JsonSerializer.Serialize(JsonSchema);
        }

        /// <summary>
        /// Start the algorithm with the provided options
        /// </summary>
        /// <param name="options">Configuration options from the UI</param>
        /// <returns>True if successful, false otherwise</returns>
        public abstract bool Start(ScriptSettingsModel options);

        /// <summary>
        /// Pause the algorithm (stop sending orders but continue receiving data)
        /// </summary>
        public virtual void Pause()
        {
            // Default implementation - can be overridden
        }

        /// <summary>
        /// Resume the algorithm after being paused
        /// </summary>
        public virtual void Resume()
        {
            // Default implementation - can be overridden
        }

        /// <summary>
        /// Stop the algorithm completely
        /// </summary>
        public virtual void Stop()
        {
            // Default implementation - can be overridden
        }

        /// <summary>
        /// Process incoming trade data (optional - only called if implemented)
        /// </summary>
        public virtual void ProcessTrade(IEnumerable<TradeMessage> trades)
        {
            // Default implementation - can be overridden
        }

        /// <summary>
        /// Process incoming candlestick data (optional - only called if implemented)
        /// </summary>
        public virtual void ProcessCandle(IEnumerable<CandlestickMessage> candles)
        {
            // Default implementation - can be overridden
        }

        /// <summary>
        /// Process incoming depth of book data (optional - only called if implemented)
        /// </summary>
        public virtual void ProcessDepthOfBook(DepthOfBookMessage depthOfBook)
        {
            // Default implementation - can be overridden
        }

        /// <summary>
        /// Process order status updates (optional - only called if implemented)
        /// </summary>
        public virtual void ProcessOrderStatus(OrderStatusUpdateMessage orderStatus)
        {
            // Default implementation - can be overridden
        }
    }
}