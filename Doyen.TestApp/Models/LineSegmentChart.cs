using Doyen.gRPC.Indicators;
using ScottPlot.Avalonia;
using ScottPlot.Plottables;
using System;
using System.Collections.Generic;
using System.Linq;

namespace Doyen.TestApp.Models
{
    internal class LineSegmentChart : IDoyenIndicatorChart
    {
        private List<LineSegment> _lineSegments = new List<LineSegment>();
        private Scatter? _lineCurrentLatestPlot = null;
        private double[] _lineCurrentLatestXs = new double[2];
        private double[] _lineCurrentLatestYs = new double[2];

        public AvaPlot AvaPlot { get; set;  }

        public Dictionary<ulong, IndicatorData> DataPointIdMap { get; set; }

        public TimeSpan Timespan { get; set; }

        public LineSegmentChart(ScottPlot.Avalonia.AvaPlot avaPlot, Dictionary<ulong, IndicatorData> dataPointIdMap)
        {
            AvaPlot = avaPlot;
            AvaPlot.Plot.Clear();
            AvaPlot.Plot.XLabel("Time");
            AvaPlot.Plot.YLabel("Value");
            DataPointIdMap = dataPointIdMap;
        }

        public void LoadTimespan(TimeSpan timespan)
        {
            Timespan = timespan / 2; // show the line in the cente of the timespan
        }

        public void Update(IndicatorData data)
        {
            ScottPlot.Color scatterColor = ScottPlot.Color.FromColor(System.Drawing.Color.FromArgb(data.R, data.G, data.B));
            string colorKey = GetColorKey(data);
            double endX = data.EndTimestamp.ToDateTime().Add(Timespan).ToOADate();
            double startX = data.StartTimestamp.ToDateTime().Add(Timespan).ToOADate();
            double y = data.LineMessage.Value;
            LineSegment? previousSegment = _lineSegments.LastOrDefault();
            bool newSegment = true;

            if (DataPointIdMap.TryGetValue(data.DataPointId, out var existingData))
            {
                newSegment = false;
            }
            else
            {
                DataPointIdMap.Add(data.DataPointId, data);
            }
            // When a new x is processed (i.e new candlestick), we need to check if the previous segment is the same color.
            // If it is, add it to the line segment. Otherwise, create a new segment.
            if (previousSegment != null)
            {
                if (!newSegment)
                {
                    _lineCurrentLatestXs[0] = previousSegment.XAxis.Last();
                    _lineCurrentLatestXs[1] = endX;
                    _lineCurrentLatestYs[0] = previousSegment.YAxis.Last();
                    _lineCurrentLatestYs[1] = y;
                    if (_lineCurrentLatestPlot != null)
                    {
                        AvaPlot.Plot.Remove(_lineCurrentLatestPlot);
                    }
                    _lineCurrentLatestPlot = AvaPlot.Plot.Add.Scatter(
                        _lineCurrentLatestXs,
                        _lineCurrentLatestYs,
                        scatterColor);
                }
                else
                {
                    if (_lineCurrentLatestPlot != null)
                    {
                        AvaPlot.Plot.Remove(_lineCurrentLatestPlot);
                    }
                    if (previousSegment.Color == scatterColor)
                    {
                        previousSegment.XAxis.Add(startX);
                        previousSegment.YAxis.Add(y);
                        if (previousSegment.CurrentPlot != null)
                        {
                            AvaPlot.Plot.Remove(previousSegment.CurrentPlot);
                        }
                        previousSegment.CurrentPlot = AvaPlot.Plot.Add.Scatter(
                            previousSegment.XAxis.ToArray(),
                            previousSegment.YAxis.ToArray(),
                            color: previousSegment.Color);
                    }
                    else
                    {
                        LineSegment newLineSegment = new LineSegment()
                        {
                            Color = scatterColor,
                            XAxis = new List<double>() { previousSegment.XAxis.Last(), startX },
                            YAxis = new List<double>() { previousSegment.YAxis.Last(), y },
                        };
                        newLineSegment.CurrentPlot = AvaPlot.Plot.Add.Scatter(
                            newLineSegment.XAxis.ToArray(),
                            newLineSegment.YAxis.ToArray(),
                            color: scatterColor);
                        _lineSegments.Add(newLineSegment);
                    }
                }
            }
            else
            {
                LineSegment newLineSegment = new LineSegment()
                {
                    Color = scatterColor,
                    XAxis = new List<double>() { startX },
                    YAxis = new List<double>() { y },
                    CurrentPlot = AvaPlot.Plot.Add.Scatter(
                        new double[] { startX },
                        new double[] { y },
                        color: scatterColor)
                };
                _lineSegments.Add(newLineSegment);
            }
        }

        private string GetColorKey(IndicatorData data)
        {
            return $"{data.R}_{data.G}_{data.B}";
        }

        private class LineSegment
        {
            public required ScottPlot.Color Color { get; set; }
            public Scatter? CurrentPlot { get; set; }
            public List<double> XAxis { get; set; } = new List<double>();
            public List<double> YAxis { get; set; } = new List<double>();

            public bool TryReplace(double x, double y)
            {
                int index = XAxis.IndexOf(x);
                if (index >= 0)
                {
                    XAxis[index] = x;
                    YAxis[index] = y;
                    return true;
                }
                return false;
            }
        }

    }
}
