using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class OdbResultBatchOptions
{
    public bool IncludeHistory { get; init; }
    public bool CompressResult { get; init; }
    public bool CopyOriginal { get; init; }
}

public sealed class OdbResultBatchSnapshot
{
    public int SchemaVersion { get; init; }
    public string Kind { get; init; } = string.Empty;
    public string OperationId { get; init; } = string.Empty;
    public string ClientRequestId { get; init; } = string.Empty;
    public DateTimeOffset CreatedAt { get; init; }
    public string Status { get; init; } = string.Empty;
    public string Phase { get; init; } = string.Empty;
    public int CompletedSteps { get; init; }
    public int TotalSteps { get; init; }
    public IReadOnlyList<RestartResultPlan> Plans { get; init; } = [];
    public IReadOnlyList<OdbResultBatchTarget> Results { get; init; } = [];
    public IReadOnlyList<string> Warnings { get; init; } = [];
    public OdbResultBatchOptions Options { get; init; } = new();
    public OdbMergeOperationSnapshot? CurrentOperation { get; init; }

    [JsonIgnore] public bool IsActive => Status is "queued" or "running" or "cancelling";
    [JsonIgnore] public bool CanResume => Status == "suspended";

    public void Validate(string? expectedId = null)
    {
        if (SchemaVersion != 1 || Kind != "odb.result_batch" || string.IsNullOrWhiteSpace(OperationId)
            || (expectedId is not null && expectedId != OperationId)
            || Status is not ("queued" or "running" or "cancelling" or "succeeded" or "failed" or "cancelled" or "suspended")
            || string.IsNullOrWhiteSpace(ClientRequestId) || string.IsNullOrWhiteSpace(Phase)
            || TotalSteps < 1 || CompletedSteps < 0 || CompletedSteps > TotalSteps
            || Plans is null || Plans.Count == 0 || Plans.Any(p => p is null || !p.Valid || p.Steps.Count == 0)
            || Results is null || Results.Count > Plans.Count || Options is null || Warnings is null
            || Results.Any(r => r is null || string.IsNullOrWhiteSpace(r.TargetJobName) || !Path.IsPathFullyQualified(r.OutputOdb))
            || (Status == "succeeded" && (CompletedSteps != TotalSteps || Results.Count != Plans.Count)))
            throw new ControlPlaneException("完整结果任务响应无效，请保留后台并重新读取任务。");
    }
}

public sealed record OdbResultBatchTarget(string TargetJobName, string OutputOdb);

public sealed class OdbResultBatchListResponse
{
    public int SchemaVersion { get; init; }
    public IReadOnlyList<OdbResultBatchSnapshot> Operations { get; init; } = [];
}
