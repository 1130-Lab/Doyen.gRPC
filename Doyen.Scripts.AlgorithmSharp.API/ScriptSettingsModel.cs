using System.Text.Json.Serialization;

namespace Doyen.Scripts.AlgorithmSharp.API
{
    public class ScriptSettingsModel
    {
        [JsonPropertyName("title")]
        public required string Title { get; set; }
        [JsonPropertyName("description")]
        public required string Description { get; set; }
        [JsonPropertyName("properties")]
        public Dictionary<string, ScriptSettingsPropertyModel> Properties { get; set; } = new Dictionary<string, ScriptSettingsPropertyModel>();
    }

    public class ScriptSettingsPropertyModel
    {
        [JsonPropertyName("title")]
        public required string Title { get; set; }
        [JsonPropertyName("description")]
        public required string Description { get; set; }
        [JsonPropertyName("type")]
        public required string TypeName { get; set; } // string | number | boolean

        [JsonPropertyName("options")]
        public required string Options { get; set; } // description of accepted input

        [JsonPropertyName("value")]
        public required object Value { get; set; }
    }
}
