using System.Text.Json;
using AbaqusTools.WinUI.Services;

internal static class RemoteRecoveryChecks
{
    internal static async Task CheckSubmissionAsync(ControlPlaneHost host)
    {
        var profile = (await host.GetRemoteServersAsync()).Connection.Profile
            ?? throw new Exception("Connected test server has no verified identity");
        RemoteJobRequest NewRequest() => new()
        {
            ClientRequestId = Guid.NewGuid().ToString("N"), JobName = "Case", InputMode = "existing",
            InputPath = @"D:\Abaqus_Cal\case.inp", ExpectedProfile = profile,
        };
        var original = NewRequest();
        if (await host.FindRemoteSubmissionAsync(original) is not null)
            throw new Exception("Unregistered request unexpectedly exists");
        var first = await host.StartRemoteJobAsync(original);
        var receipt = await host.FindRemoteSubmissionAsync(original);
        var replay = await host.StartRemoteJobAsync(original, withdrawUnregistered: true);
        if (receipt?.OperationId != first.OperationId || replay.OperationId != first.OperationId
            || replay.TrackingState == "withdrawn")
            throw new Exception("Withdrawal affected an already registered request");
        var missing = NewRequest();
        var withdrawal = await host.StartRemoteJobAsync(missing, withdrawUnregistered: true);
        var late = await host.StartRemoteJobAsync(missing);
        if (withdrawal.TrackingState != "withdrawn" || late.OperationId != withdrawal.OperationId
            || (await host.FindRemoteSubmissionAsync(missing))?.TrackingState != "withdrawn")
            throw new Exception("A late or repeated submission bypassed the withdrawal");
    }

    internal static void Run()
    {
        var legacy = JsonSerializer.Deserialize<RemoteJobOperationSnapshot>("""{"status":"running"}""")!;
        if (!legacy.CanPauseResume || legacy.StatusDisplay != "远端运行中")
            throw new Exception("Legacy remote operation compatibility changed");
        foreach (var (tracking, label) in new[] { ("reconnecting", "等待重连核对"),
                    ("submission_unknown", "提交状态待核对"), ("unverified", "等待状态核对") })
        {
            var operation = new RemoteJobOperationSnapshot { Status = "running", TrackingState = tracking };
            if (operation.IsTerminal || operation.CanPauseResume || operation.StatusDisplay != label)
                throw new Exception("Unconfirmed remote jobs must remain active with controls disabled");
        }
        var cancelled = new RemoteJobOperationSnapshot { Status = "cancelled", TrackingState = "reconnecting" };
        if (!cancelled.IsTerminal || cancelled.CanPauseResume || cancelled.StatusDisplay != "已取消")
            throw new Exception("Terminal status must take precedence over stale tracking state");
        var warning = JsonSerializer.Deserialize<RemoteJobOperationSnapshot>("""
            {"status":"running","trackingState":"tracking","persistenceWarning":"记录暂未保存"}
            """)!;
        if (!warning.CanPauseResume || warning.PersistenceWarning != "记录暂未保存")
            throw new Exception("Storage warning must not replace current process state");
        Console.WriteLine("6 native remote recovery presentation checks passed.");
    }
}
