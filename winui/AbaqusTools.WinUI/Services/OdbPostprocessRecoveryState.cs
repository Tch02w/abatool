namespace AbaqusTools.WinUI.Services;

/// <summary>Keeps uncertain HTTP outcomes distinct from confirmed operation terminal states.</summary>
public sealed class OdbPostprocessRecoveryState
{
    private static readonly HashSet<string> RejectionCodes = new(StringComparer.Ordinal)
    {
        "UNKNOWN_FIELDS", "MISSING_FIELDS", "UNSUPPORTED_SCHEMA_VERSION", "ROOT_NOT_FOUND", "ROOT_NOT_DIRECTORY",
        "PATH_OUTSIDE_ROOT", "ODB_NOT_FOUND", "INVALID_ODB_PATH", "INVALID_POSTPROCESS_PATHS", "DUPLICATE_ODB_PATH",
        "INVALID_POSTPROCESS_FIELD", "INVALID_CLIENT_REQUEST_ID", "INVALID_IMAGE_UNIT", "NO_IMAGE_OUTPUT",
        "INVALID_REBAR_METHOD", "INVALID_POSTPROCESS_JOBS", "DUPLICATE_POSTPROCESS_JOB", "INVALID_POSTPROCESS_GROUPS",
        "UNGROUPED_POSTPROCESS_JOBS", "INVALID_POSTPROCESS_JOB", "INVALID_REINFORCEMENT_MODE", "INVALID_FRAME_MODE",
        "MANUAL_FRAME_EXPRESSION_REQUIRED", "INVALID_LOAD_DIRECTION", "INVALID_PILE_TYPE", "INVALID_POSTPROCESS_GROUP",
        "UNKNOWN_GROUP_MEMBERS", "INVALID_LEGEND_OVERRIDES", "INVALID_LEGEND_OVERRIDE", "INVALID_STANDALONE_GROUP",
        "INVALID_REGION", "INVALID_REGION_METHOD", "INVALID_SECTION", "UNUSED_SECTION", "REFERENCE_AREA_NOT_ACKNOWLEDGED",
        "INVALID_REFERENCE_AREA", "INVALID_REGION_FRAMES", "CONTROL_PLANE_SHUTTING_DOWN", "OPERATION_SCHEDULER_UNAVAILABLE",
    };

    public string? ClientRequestId { get; private set; }
    public string? OperationId { get; private set; }
    public string? Kind { get; private set; }
    public bool Active { get; private set; }
    public bool NeedsRecovery { get; private set; }
    public bool CancelRequested { get; private set; }
    public bool CanCancel => Active && !CancelRequested && !string.IsNullOrWhiteSpace(OperationId);

    public bool MatchesProgress(OdbPostprocessOperationSnapshot snapshot) => Active
        && !string.IsNullOrWhiteSpace(ClientRequestId)
        && ClientRequestId == snapshot.Request.ClientRequestId && Kind == snapshot.Kind
        && (OperationId is null || OperationId == snapshot.OperationId);

    public void Begin(string requestId, string kind)
    {
        if (Active) throw new InvalidOperationException("原操作的状态尚未确认，不能重复提交。");
        Reset();
        ClientRequestId = requestId;
        Kind = kind;
        Active = true;
    }

    public void Observe(OdbPostprocessOperationSnapshot snapshot, bool recovered = false)
    {
        if ((!string.IsNullOrWhiteSpace(OperationId) && OperationId != snapshot.OperationId)
            || (!string.IsNullOrWhiteSpace(ClientRequestId) && ClientRequestId != snapshot.Request.ClientRequestId)
            || (!string.IsNullOrWhiteSpace(Kind) && Kind != snapshot.Kind))
            throw new InvalidDataException("返回的操作与原请求不一致，仍需查询原操作。");
        OperationId = snapshot.OperationId;
        ClientRequestId = snapshot.Request.ClientRequestId;
        Kind = snapshot.Kind;
        Active = !snapshot.IsTerminal;
        CancelRequested = (!recovered && CancelRequested) || snapshot.Status == "cancelling";
        if (snapshot.IsTerminal) NeedsRecovery = CancelRequested = false;
    }

    public bool RequestCancel()
    {
        if (!CanCancel) return false;
        CancelRequested = true;
        return true;
    }

    public bool RequiresVerification(Exception error) => OperationId is not null
        || error is not ControlPlaneException { Code: { } code } || !RejectionCodes.Contains(code);

    public void MarkUnconfirmed()
    {
        Active = true;
        NeedsRecovery = true;
    }

    public OdbPostprocessOperationSnapshot? FindExisting(IEnumerable<OdbPostprocessOperationSnapshot> operations)
    {
        var matches = operations.Where(snapshot => snapshot.Kind == Kind
            && (OperationId is not null ? snapshot.OperationId == OperationId
                : !string.IsNullOrWhiteSpace(ClientRequestId) && snapshot.Request.ClientRequestId == ClientRequestId)).ToArray();
        if (matches.Length > 1) throw new InvalidDataException("原请求对应多个操作，无法安全恢复。");
        return matches.SingleOrDefault();
    }

    public void Reset()
    {
        ClientRequestId = OperationId = Kind = null;
        Active = NeedsRecovery = CancelRequested = false;
    }
}
