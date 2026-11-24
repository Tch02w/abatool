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

    internal bool HasEdits(string outputDirectory, IReadOnlyList<OdbResultGraphNode> editedNodes)
    {
        if (OutputDirectory != outputDirectory || Nodes.Count != editedNodes.Count) return true;
        for (var index = 0; index < Nodes.Count; index++)
        {
            var saved = Nodes[index];
            var edited = editedNodes[index];
            if (saved.NodeId != edited.NodeId || saved.ParentNodeId != edited.ParentNodeId
                || saved.Name != edited.Name || saved.OdbPath != edited.OdbPath || saved.InpPath != edited.InpPath)
                return true;
        }
        return false;
    }
}

public sealed class OdbResultBatchPlan
{
    public int SchemaVersion { get; init; }
    public int GraphRevision { get; init; }
    public bool Valid { get; init; }
    public IReadOnlyList<string> Issues { get; init; } = [];
    public IReadOnlyList<RestartResultPlan> Plans { get; init; } = [];
}
