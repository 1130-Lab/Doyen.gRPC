using Doyen.gRPC.Indicators;
using ScottPlot;
using ScottPlot.Avalonia;
using ScottPlot.Plottables;
using System;
using System.Collections.Generic;

namespace Doyen.TestApp.Models
{
    internal class CandlestickChart : IDoyenIndicatorChart
    {
        public AvaPlot AvaPlot { get; set; }
        public Dictionary<ulong, IndicatorData> DataPointIdMap { get; set; }
        public TimeSpan Timespan { get; set; }

        private CandlestickPlot? _currentCandle = null;

        public CandlestickChart(ScottPlot.Avalonia.AvaPlot avaPlot, Dictionary<ulong, IndicatorData> dataPointIdMap)
        {
            AvaPlot = avaPlot;
            AvaPlot.Plot.Clear();
            AvaPlot.Plot.XLabel("Time");
            AvaPlot.Plot.YLabel("Value");
            DataPointIdMap = dataPointIdMap;
        }

        public void LoadTimespan(TimeSpan timespan)
        {
            Timespan = timespan;
        }

        public void Update(IndicatorData data)
        {
            DateTime startTime = data.StartTimestamp.ToDateTime();
            OHLC datapoint = new ScottPlot.OHLC()
            {
                Open = data.CandlestickMessage.Open,
                High = data.CandlestickMessage.High,
                Low = data.CandlestickMessage.Low,
                Close = data.CandlestickMessage.Close,
                DateTime = startTime,
                TimeSpan = Timespan
            };
            if (_currentCandle == null || !DataPointIdMap.TryGetValue(data.DataPointId, out var existingData))
            {
                DataPointIdMap.Add(data.DataPointId, data);
                _currentCandle = AvaPlot.Plot.Add.Candlestick(new OHLC[1] { datapoint });
            }
            else
            {
                AvaPlot.Plot.Remove(_currentCandle);
                _currentCandle = AvaPlot.Plot.Add.Candlestick(new OHLC[1] { datapoint });
            }
        }
    }
}
