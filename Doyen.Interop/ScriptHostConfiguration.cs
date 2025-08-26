namespace Doyen.Interop
{
    public enum ScriptHostType
    {
        None,
        Indicators,
        Algorithms
    }

    public class ScriptHostManagerConfiguration
    {
        public required List<ScriptHostConfiguration> ScriptHosts { get; set; }
    }

    public class ScriptHostConfiguration
    {
        public required string Name { get; set; }
        public required string Description { get; set; }
        public required ScriptHostType Type { get; set; }
        public List<string> IgnoreList { get; set; } = new List<string>();
        public bool ShowWindow { get; set; }
        public bool UseShellExecute { get; set; }
        public required ProcessInfo ProcessStartInfo { get; set; }
    }

    public class ProcessInfo 
    {
        public required string Process { get; set; }
        public IEnumerable<string>? Arguments { get; set; }
    }
}
