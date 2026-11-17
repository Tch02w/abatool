using AbaqusTools.WinUI.Services;

static class OdbPostprocessRecoveryChecks
{
    public static void Run()
    {
        var checks = 0;
        void Check(bool condition, string message)
        {
            checks++;
            if (!condition) throw new InvalidOperationException(message);
        }
        static OdbPostprocessOperationSnapshot Snapshot(string status, string requestId = "request-a", string operationId = "operation-a") => new()
        {
            Kind = "odb.postprocess.region", OperationId = operationId, Status = status,
            Request = new() { ClientRequestId = requestId },
        };

        var state = new OdbPostprocessRecoveryState();
        state.Begin("request-a", "odb.postprocess.region");
        Check(state.Active && !state.CanCancel, "Submitting without an operation ID must not send a cancel to another task");
        Check(state.RequiresVerification(new OperationCanceledException("Request timed out")),
            "A timed-out HTTP request is not confirmation of backend cancellation");
        Check(state.RequiresVerification(new ControlPlaneException("Disconnected", "CONTROL_PLANE_DISCONNECTED")),
            "A disconnected create request can still have created an operation");
        Check(!state.RequiresVerification(new ControlPlaneException("Invalid section", "INVALID_SECTION")),
            "Explicit validation rejection before an operation ID should allow correcting the request");
        state.MarkUnconfirmed();
        Check(state.Active && state.NeedsRecovery && state.ClientRequestId == "request-a", "Uncertain submission must retain request identity and block another start");
        var duplicateStartRejected = false;
        try { state.Begin("request-b", "odb.postprocess.region"); }
        catch (InvalidOperationException) { duplicateStartRejected = true; }
        Check(duplicateStartRejected && state.ClientRequestId == "request-a", "Retry must not replace an unconfirmed request");
        Check(state.FindExisting([Snapshot("running", "other", "other")]) is null,
            "Recovery must not attach to an unrelated active operation");
        Check(state.NeedsRecovery && state.Active, "A missing operation record does not prove the original task stopped");
        var original = Snapshot("succeeded");
        Check(ReferenceEquals(state.FindExisting([Snapshot("running", "other", "other"), original]), original),
            "Lost creation response recovery must include terminal operations and match the exact request");
        var duplicateRecordsRejected = false;
        try { state.FindExisting([Snapshot("running"), Snapshot("running", operationId: "duplicate")]); }
        catch (InvalidDataException) { duplicateRecordsRejected = true; }
        Check(duplicateRecordsRejected, "Ambiguous request identity must not silently pick an operation");

        state.Observe(Snapshot("running"));
        Check(state.OperationId == "operation-a" && state.CanCancel, "A confirmed operation ID permits cancelling that operation");
        Check(state.RequestCancel() && !state.CanCancel, "Sending cancellation must immediately prevent duplicate cancel requests");
        Check(!state.RequestCancel(), "Duplicate cancellation must remain blocked");
        state.Observe(Snapshot("running"));
        Check(!state.CanCancel, "A queued older running progress report must not re-enable cancellation");
        state.Observe(Snapshot("cancelling"));
        Check(state.Active && !state.CanCancel, "Cancelling is active until the backend reports a terminal state");
        state.MarkUnconfirmed();
        Check(state.OperationId == "operation-a" && state.ClientRequestId == "request-a",
            "Lost polling response must preserve both operation and request identity");
        Check(state.RequiresVerification(new ControlPlaneException("Not found", "ODB_POSTPROCESS_OPERATION_NOT_FOUND")),
            "A replaced control plane losing its in-memory record cannot prove that the worker stopped");
        Check(state.FindExisting([Snapshot("running", "request-a", "new-operation")]) is null,
            "Known operation recovery must not replace the operation with a different ID");
        var mismatchedRejected = false;
        try { state.Observe(Snapshot("cancelled", "other")); }
        catch (InvalidDataException) { mismatchedRejected = true; }
        Check(mismatchedRejected && state.Active && state.NeedsRecovery, "An unrelated terminal response must not unlock the original operation");
        state.Observe(Snapshot("running"), recovered: true);
        Check(state.CanCancel && state.NeedsRecovery, "A fresh bounded query confirming running permits retrying an uncertain cancel without submitting work");

        foreach (var status in new[] { "cancelled", "failed", "succeeded" })
        {
            state.Observe(Snapshot(status));
            Check(!state.Active && !state.NeedsRecovery && !state.CanCancel, $"Only confirmed {status} should release the recovery lock");
            state.Reset();
            Check(state.ClientRequestId is null && state.OperationId is null, "Terminal cleanup must clear request identity");
            state.Begin("request-a", "odb.postprocess.region");
            state.MarkUnconfirmed();
        }
        Check(state.RequiresVerification(new ControlPlaneException("Unrecognized server failure", "FUTURE_SERVER_ERROR")),
            "Unknown server failures must preserve uncertainty");

        state.Observe(Snapshot("succeeded"));
        state.Reset();
        state.Begin("request-b", "odb.postprocess.region");
        var delayedOldProgress = Snapshot("running");
        Check(state.OperationId is null && !state.MatchesProgress(delayedOldProgress),
            "Old queued progress must be ignored while a new request is awaiting its operation ID");
        if (state.MatchesProgress(delayedOldProgress)) state.Observe(delayedOldProgress);
        Check(state.OperationId is null && state.ClientRequestId == "request-b" && state.Active,
            "Ignoring old progress must preserve the new pending request without throwing");
        Check(state.MatchesProgress(Snapshot("running", "request-b", "operation-b")),
            "Progress for the current request should be accepted before its create response arrives");
        Check(!state.MatchesProgress(new OdbPostprocessOperationSnapshot
        {
            Kind = "odb.postprocess.scan", OperationId = "operation-b", Status = "running",
            Request = new() { ClientRequestId = "request-b" },
        }), "Same request ID with the wrong kind must not enter the UI progress handler");
        var explicitMismatchRejected = false;
        try { state.Observe(delayedOldProgress, recovered: true); }
        catch (InvalidDataException) { explicitMismatchRejected = true; }
        Check(explicitMismatchRejected, "Explicit recovery responses must still reject identity mismatches");
        state.Observe(Snapshot("running", "request-b", "operation-b"));
        Check(!state.MatchesProgress(Snapshot("running", "request-b", "wrong-operation")),
            "Once known, operation ID must also match progress");
        state.Observe(Snapshot("succeeded", "request-b", "operation-b"));
        Check(!state.MatchesProgress(Snapshot("running", "request-b", "operation-b")),
            "Late progress for a terminal operation must be ignored");
        Console.WriteLine($"{checks} postprocess recovery state checks passed");
    }
}
