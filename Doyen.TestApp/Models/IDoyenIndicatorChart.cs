using Doyen.gRPC.Indicators;
using ScottPlot.Avalonia;
using System;
using System.Collections.Generic;

namespace Doyen.TestApp.Models
{
    public interface IDoyenIndicatorChart
    {
        public AvaPlot AvaPlot { get; set; }

        public Dictionary<ulong, IndicatorData> DataPointIdMap { get; set; }

        public TimeSpan Timespan { get; set; }

        public void LoadTimespan(TimeSpan timespan);

        public void Update(IndicatorData data);
    }
}
