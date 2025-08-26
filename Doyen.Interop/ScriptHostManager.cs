using System.Text.Json;

namespace Doyen.Interop
{
    public class ScriptHostManager : IDisposable
    {
        private List<ScriptHost> _scriptHosts = new List<ScriptHost>();
        public IReadOnlyCollection<ScriptHost> ScriptHosts => _scriptHosts.AsReadOnly();
        private readonly ScriptHostManagerConfiguration _configuration;
        private bool _disposed = false;

        public ScriptHostManagerConfiguration Configuration => _configuration;

        public ScriptHostManager()
        {
            _configuration = JsonSerializer.Deserialize<ScriptHostManagerConfiguration>(File.ReadAllText("ScriptHosts.json"))
                ?? throw new Exception("Failed to load ScriptHosts configuration.");
            foreach (var hostConfig in _configuration.ScriptHosts)
            {
                ScriptHost scriptHost = new ScriptHost(hostConfig.Name, hostConfig);
                scriptHost.StartServer(
                    hostConfig.ProcessStartInfo.Process,
                    hostConfig.ProcessStartInfo.Arguments,
                    hostConfig.UseShellExecute,
                    hostConfig.ShowWindow
                );
                _scriptHosts.Add(scriptHost);
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
                    foreach(var scriptHost in _scriptHosts)
                    {
                        scriptHost.Dispose();
                    }
                }

                _disposed = true;
            }
        }

        ~ScriptHostManager()
        {
            Dispose(false);
        }
    }
}