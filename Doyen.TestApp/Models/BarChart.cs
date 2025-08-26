using Doyen.gRPC.Indicators;
using ScottPlot;
using ScottPlot.Avalonia;
using System;
using System.Collections.Generic;

namespace Doyen.TestApp.Models
{
    internal class BarChart : IDoyenIndicatorChart
    {
        public AvaPlot AvaPlot { get; set; }
        public Dictionary<ulong, IndicatorData> DataPointIdMap { get; set; }
        public TimeSpan Timespan { get; set; }

        private ScottPlot.Plottables.BarPlot? _currentBar = null;

        public BarChart(ScottPlot.Avalonia.AvaPlot avaPlot, Dictionary<ulong, IndicatorData> dataPointIdMap)
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
            DateTime startTimestamp = data.StartTimestamp.ToDateTime();
            double oaBaseTime = startTimestamp.ToOADate();
            double oaOffsetTime = startTimestamp.Add(Timespan).ToOADate();
            var datapoint = new Bar()
            {
                Value = data.BarMessage.Bottom,
                ValueBase = data.BarMessage.Top,
                Position = oaBaseTime,
                Size = oaOffsetTime - oaBaseTime
            };
            if (_currentBar == null || !DataPointIdMap.TryGetValue(data.DataPointId, out var existingData))
            {
                DataPointIdMap.Add(data.DataPointId, data);
                _currentBar = AvaPlot.Plot.Add.Bar(datapoint);
                _currentBar.Color = ScottPlot.Color.FromColor(System.Drawing.Color.FromArgb(data.R, data.G, data.B));
            }
            else
            {
                AvaPlot.Plot.Remove(_currentBar);
                _currentBar = AvaPlot.Plot.Add.Bar(datapoint);
                _currentBar.Color = ScottPlot.Color.FromColor(System.Drawing.Color.FromArgb(data.R, data.G, data.B));
            }
        }
    }
}
