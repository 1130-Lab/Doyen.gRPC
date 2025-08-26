using Doyen.gRPC.Common;
using System;
using System.Collections.Generic;
using System.Linq;

namespace Doyen.TestApp.Utilities
{
    internal class CandlestickHelper
    {
        private const int _randomSeed = 50;
        private static readonly Random random = new Random(_randomSeed);
        private static double _lastPrice = 100000;

        internal static void UpdateCandlestick(DoyenCandlestick candlestick)
        {
            _lastPrice += GetOscillationWeight() * 2000d;
            if(candlestick.High < _lastPrice)
            {
                candlestick.High = _lastPrice;
            }
            else if(candlestick.Low > _lastPrice)
            {
                candlestick.Low = _lastPrice;
            }
            candlestick.Close = _lastPrice;
            candlestick.Timestamp = Google.Protobuf.WellKnownTypes.Timestamp.FromDateTime(DateTime.UtcNow);
        }

        internal static DoyenCandlestick CreateSampleCandlestick(DateTime time, double? overrideOpen = null)
        {
            double priceModifier = GetOscillationWeight();
            _lastPrice += priceModifier * 2000d; // +/- 1000

            // Get the nearest round 5 minute interval
            var minutes = (int)Math.Round(time.Minute / 1.0) * 1;
            if (minutes == 60)
            {
                minutes = 0;
                time = time.AddHours(1);
            }
            var roundTime = new DateTime(time.Year, time.Month, time.Day, time.Hour, minutes, 0, DateTimeKind.Utc);
            if(roundTime > time) 
            {
                roundTime = roundTime.AddMinutes(-1);
            }
            var startTime = roundTime;
            var endTime = startTime.AddMinutes(1);
            var timestamp = Google.Protobuf.WellKnownTypes.Timestamp.FromDateTime(DateTime.UtcNow);

            List<double> values = new List<double>()
            {
                _lastPrice - GetOscillationWeight() * 100,
                _lastPrice + GetOscillationWeight() * 100,
                _lastPrice + GetOscillationWeight() * 100,
                _lastPrice - GetOscillationWeight() * 100
            };
            if(overrideOpen != null)
            {
                values.Add(overrideOpen.Value);
            }

            var candle = new DoyenCandlestick
            {
                Exchange = DoyenExchange.ExchangeBinanceus,
                Timeframe = Timeframe.OneMinute,
                Timestamp = timestamp,
                TimeStart = Google.Protobuf.WellKnownTypes.Timestamp.FromDateTime(startTime),
                TimeEnd = Google.Protobuf.WellKnownTypes.Timestamp.FromDateTime(endTime),
            };
            candle.High = values.Max();
            values.Remove(candle.High);
            candle.Low = values.Min();
            values.Remove(candle.Low);
            candle.Open = overrideOpen ?? values[0];
            candle.Close = values[1];

            if (candle.Open > candle.High || candle.Close < candle.Low || candle.Close > candle.High || candle.Open < candle.Low)
            {
                throw new InvalidOperationException("Invalid candlestick data generated.");
            }

            return candle;
        }

        /// <summary>
        /// Oscillates a value between -0.5 and 0.5.
        /// </summary>
        /// <returns></returns>
        private static double GetOscillationWeight()
        {
            return (random.NextDouble() - 0.5d);
        }
    }
}
