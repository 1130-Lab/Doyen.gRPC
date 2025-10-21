namespace Doyen.Scripts.AlgorithmSharp.API
{
    /// <summary>
    /// Algorithm state
    /// </summary>
    public enum AlgorithmState
    {
        Initialized,
        Running,
        Paused,
        Stopped
    }

    /// <summary>
    /// Context information for an active algorithm instance
    /// </summary>
    public class AlgorithmContext
    {
        public string Id { get; }
        public string Name { get; }
        public Algorithm? Algorithm { get; set; }
        public AlgorithmState State { get; set; }
        public string? Configuration { get; set; }

        public AlgorithmContext(string id, string name, Algorithm? algorithm = null)
        {
            Id = id;
            Name = name;
            Algorithm = algorithm;
            State = AlgorithmState.Initialized;
        }
    }
}