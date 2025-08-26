using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Doyen.Interop;
using System;
using System.IO;

namespace Doyen.TestApp
{
    public partial class App : Application
    {
        public static ScriptHostManager? PythonServerManager
        {
            get; private set;
        }

        public override void Initialize()
        {
            AvaloniaXamlLoader.Load(this);
        }

        public override void OnFrameworkInitializationCompleted()
        {
            // Start the Python server
            StartPythonServer();

            if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
            {
                desktop.MainWindow = new MainWindow();
                desktop.Exit += OnApplicationExit;
            }

            base.OnFrameworkInitializationCompleted();
        }

        private void StartPythonServer()
        {
            try
            {
                // Create and start the Python server manager
                PythonServerManager = new ScriptHostManager();
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error starting Python server: {ex.Message}");
            }
        }

        private void OnApplicationExit(object? sender, ControlledApplicationLifetimeExitEventArgs e)
        {
            // Ensure Python server is stopped when the application exits
            PythonServerManager?.Dispose();
        }
    }
}