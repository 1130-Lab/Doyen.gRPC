using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Doyen.gRPC.Common;
using Doyen.gRPC.Indicators;
using Doyen.Interop;
using Doyen.TestApp.Models;
using Doyen.TestApp.Services;
using Doyen.TestApp.Utilities;
using ScottPlot.Plottables;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Doyen.TestApp
{
    internal partial class MainViewModel : ObservableObject, IDisposable
    {
        private readonly ChartsClientService _chartsClient;

        [ObservableProperty]
        private ScottPlot.Avalonia.AvaPlot _avaPlot;

        [ObservableProperty]
        private string _scriptName = string.Empty;

        [ObservableProperty]
        private string _statusMessage = "Ready";

        [ObservableProperty]
        private string _mode = "Start";

        [ObservableProperty]
        private bool _isConnected = false;

        [ObservableProperty]
        private bool _hasSetupJson = false;

        [ObservableProperty]
        private string _setupJson = string.Empty;

        [ObservableProperty]
        private bool _isStreaming = false;

        [ObservableProperty]
        private int _updateIntervalMs = 1000;

        [ObservableProperty]
        private int _maxDataPoints = 100;

        private Dictionary<ulong, IndicatorData> _dataPointIdMap = new();

        private IDoyenIndicatorChart? _currentChart;


        public MainViewModel()
        {
            ScriptHost host = App.PythonServerManager.ScriptHosts.FirstOrDefault(h => h.HostName == "Doyen.Indicators") ?? throw new Exception("Doyen.Indicators script host not found. Ensure the Python server is running.");
            string address = host.Configuration.ProcessStartInfo.Arguments?.FirstOrDefault(a => a.StartsWith("--address"))?.Split(' ')[1] ?? throw new Exception("Indicator address not found in script host arguments. Ensure the Python server is running with the correct arguments.");
            _chartsClient = new ChartsClientService($"http://{address}");
            _chartsClient.DataReceived += OnDataReceived;

            AvaPlot = new ScottPlot.Avalonia.AvaPlot
            {
                Width = 800,
                Height = 600
            };
            AvaPlot.Plot.Axes.DateTimeTicksBottom();
            AvaPlot.Plot.Axes.AutoScaleExpand();

            InitializePlot();
        }
        private SemaphoreSlim _plotLock = new SemaphoreSlim(1, 1);
        private void OnDataReceived(object sender, IndicatorData data)
        {
            _plotLock.Wait();
            // We need to run this on the UI thread
            Avalonia.Threading.Dispatcher.UIThread.Invoke(() =>
            {
                try
                {
                    // Update the plot with the new data
                    UpdatePlot(data);

                    // Update status message
                    StatusMessage = $"Data received at {DateTime.Now:HH:mm:ss.fff}";
                }
                finally
                {
                    _plotLock.Release();
                }
            });
        }

        private void InitializePlot()
        {
            var plt = AvaPlot.Plot;
            plt.Title("Indicator Data");
            plt.XLabel("Time");
            plt.YLabel("Value");
        }

        [RelayCommand]
        private async Task ConnectToIndicator()
        {
            if (string.IsNullOrWhiteSpace(ScriptName))
            {
                StatusMessage = "Please enter a script path";
                return;
            }

            StatusMessage = "Connecting to indicator...";
            
            try
            {
                InitializeIndicatorResponse? connected = await _chartsClient.InitializeIndicatorAsync(ScriptName, "BTC-USD");
                if (connected == null || !connected.Success)
                {
                    StatusMessage = $"Failed to connect to indicator: {(connected != null ? connected.Reason : "internal exception")}";
                    return;
                }
                SetupJson = connected.OptionsJsonDataRequest;
                StatusMessage = "Connected to indicator";
                IsConnected = true;
            }
            catch (Exception ex)
            {
                StatusMessage = $"Error: {ex.Message}";
            }
        }

        [RelayCommand]
        private async Task StartIndicator()
        {
            if (!IsConnected)
            {
                StatusMessage = "Not connected to an indicator";
                return;
            }
            else if (Mode == "Start")
            {
                try
                {
                    var historicalData = new List<DoyenCandlestick>();
                    DoyenCandlestick? lastCandle = null;
                    for(int i = 12; i >= 1; i--)
                    {
                        double? overrideOpen = null;
                        if(lastCandle != null)
                        {
                            overrideOpen = lastCandle.Close;
                        }
                        lastCandle = CandlestickHelper.CreateSampleCandlestick(DateTime.UtcNow.AddMinutes(-1 * i), overrideOpen: overrideOpen);
                        historicalData.Add(lastCandle);
                    }

                    StatusMessage = "Starting indicator...";
                    StartIndicatorResponse? started = await _chartsClient.StartIndicatorAsync(historicalData.ToArray(), SetupJson);

                    if (started == null || !started.Success)
                    {
                        StatusMessage = $"Failed to start indicator: {(started != null ? started.Reason : "internal exception")}";
                        IsStreaming = false;
                        return;
                    }

                    ToggleContinuousDataProcessing(lastCandle?.Close);

                    _dataPointIdMap.Clear();

                    foreach (var data in started.HistoricalData)
                    {
                        UpdatePlot(data);
                    }

                    Mode = "Stop";
                    StatusMessage = "Indicator started successfully. Ready to process data.";
                }
                catch (Exception ex)
                {
                    StatusMessage = $"Error: {ex.Message}";
                }
            }
            else if (Mode == "Stop")
            {
                try
                {
                    ToggleContinuousDataProcessing();
                    _currentChart = null;
                    StatusMessage = "Stopping indicator...";
                    await _chartsClient.StopIndicatorAsync();
                    IsConnected = false;
                    IsStreaming = false;
                    Mode = "Start";
                    StatusMessage = "Indicator stopped successfully.";
                    SetupJson = string.Empty;
                }
                catch (Exception ex)
                {
                    StatusMessage = $"Error: {ex.Message}";
                }
            }
        }

        [RelayCommand]
        private void ToggleContinuousDataProcessing(double? overrideOpen = null)
        {
            if (!IsConnected)
            {
                StatusMessage = "Not connected to an indicator";
                return;
            }

            if (IsStreaming)
            {
                // Stop streaming
                _chartsClient.StopContinuousDataProcessing();
                IsStreaming = false;
                StatusMessage = "Continuous data processing stopped";
            }
            else
            {
                // Start streaming
                _chartsClient.StartContinuousDataProcessing("BTC-USD", overrideOpen, UpdateIntervalMs);
                IsStreaming = true;
                StatusMessage = "Continuous data processing started";
            }
        }

        private void UpdatePlot(IndicatorData data)
        {
            if (_currentChart == null)
            {
                TimeSpan timespan = (data.EndTimestamp - data.StartTimestamp).ToTimeSpan();
                // Determine the chart type based on the data type
                switch (data.Type)
                {
                    case IndicatorMessageType.MessageLine:
                        _currentChart = new LineSegmentChart(AvaPlot, _dataPointIdMap);
                        break;
                    case IndicatorMessageType.MessageCandlestick:
                        _currentChart = new CandlestickChart(AvaPlot, _dataPointIdMap);
                        break;
                    case IndicatorMessageType.MessageBar:
                        _currentChart = new BarChart(AvaPlot, _dataPointIdMap);
                        break;
                    default:
                        StatusMessage = "Unknown data type received";
                        return;
                }
                _currentChart.LoadTimespan(timespan); // Set a default timespan
            }
            lock (AvaPlot.Plot.Sync)
            {
                _currentChart.Update(data);
                AvaPlot.Plot.Axes.AutoScale();
                AvaPlot.Refresh();
            }
        }

        public void Dispose()
        {
            // Clean up resources
            _chartsClient.DataReceived -= OnDataReceived;
            _chartsClient.Dispose();
        }
    }
}
