namespace AbaqusTools.WinUI.Services;

public sealed class OdbResultGraphNode
{
    public string NodeId { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string ParentNodeId { get; set; } = string.Empty;
    public string OdbPath { get; set; } = string.Empty;
    public string InpPath { get; set; } = string.Empty;
}

public sealed class OdbResultGraphSnapshot
{
    public int SchemaVersion { get; init; }
    public int Revision { get; init; }
    public string OutputDirectory { get; init; } = string.Empty;
    public IReadOnlyList<OdbResultGraphNode> Nodes { get; init; } = [];
}

public sealed class OdbResultBatchPlan
{
    public int SchemaVersion { get; init; }
    public int GraphRevision { get; init; }
    public bool Valid { get; init; }
    public IReadOnlyList<string> Issues { get; init; } = [];
    public IReadOnlyList<RestartResultPlan> Plans { get; init; } = [];
}
