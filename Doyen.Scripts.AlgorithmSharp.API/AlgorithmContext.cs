namespace Doyen.Scripts.AlgorithmSharp.API
{
    /// <summary>
    /// Context information for an active algorithm instance
    /// </summary>
    public class AlgorithmContext
    {
        public string Id { get; }
        public string Name { get; }
        public Algorithm? Algorithm { get; set; }

        public AlgorithmContext(string id, string name, Algorithm? algorithm = null)
        {
            Id = id;
            Name = name;
            Algorithm = algorithm;
        }
    }
}