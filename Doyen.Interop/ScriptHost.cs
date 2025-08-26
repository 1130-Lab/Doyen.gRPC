using System.Diagnostics;

namespace Doyen.Interop
{
    public class ScriptHost : IDisposable
    {
        private Process? _process;
        private bool _disposed = false;
        public bool IsRunning => _process != null && !_process.HasExited;
        public readonly ScriptHostConfiguration Configuration;
        public string HostName => Configuration.Name;

        public ScriptHost(string hostName, ScriptHostConfiguration configuration)
        {
            Configuration = configuration;
        }

        public bool StartServer(string fileName, IEnumerable<string>? args, bool shell = false, bool showWindow = false)
        {
            try
            {
                if (IsRunning)
                {
                    return true; // Server is already running
                }

                string arguments = string.Join(" ", args ?? new List<string>());

                var startInfo = new ProcessStartInfo(fileName, arguments)
                {
                    UseShellExecute = shell,
                    CreateNoWindow = !showWindow
                };

                _process = new Process { StartInfo = startInfo };

                _process.Start();

                return true;
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"Error starting Python server: {ex.Message}");
                return false;
            }
        }

        public void StopServer()
        {
            if (!IsRunning)
            {
                return;
            }

            try
            {
                _process?.Kill();
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"Error stopping Python server: {ex.Message}");
            }
            finally
            {
                _process?.Dispose();
                _process = null;
            }
        }

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        protected virtual void Dispose(bool disposing)
        {
            if (!_disposed)
            {
                if (disposing)
                {
                    StopServer();
                }

                _disposed = true;
            }
        }

        ~ScriptHost()
        {
            Dispose(false);
        }
    }
}
