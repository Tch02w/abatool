namespace AbaqusTools.WinUI.Services;

public sealed partial class ControlPlaneHost
{
    private async Task<T> SendUpgradeRequestAsync<T>(HttpMethod method, string path, object? body,
        CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(timeout.Token);
        if (method == HttpMethod.Post && path is "/api/v1/odb-upgrade-previews" or "/api/v1/odb-upgrade-operations")
        {
            var health = await SendJsonRequestAsync<HealthResponse>(descriptor, HttpMethod.Get,
                "/healthz", null, "升级能力检查", timeout.Token);
            if (health.InstanceId != descriptor.InstanceId
                || health.Capabilities is null || !health.Capabilities.Contains("odb.upgrade.safe-v1")
                || !health.Capabilities.Contains("odb.upgrade.history-v1"))
                throw new ControlPlaneException("当前后台版本尚不支持带持久记录的安全升级。请先等待已有后台任务结束，再重启软件。",
                    code: "UPGRADE_CAPABILITY_REQUIRED");
        }
        return await SendJsonRequestAsync<T>(descriptor, method, path, body, "ODB 升级响应", timeout.Token);
    }

    public async Task<OdbUpgradePreview> PreviewOdbUpgradeAsync(string root, IReadOnlyList<string> paths,
        CancellationToken cancellationToken = default)
    {
        var preview = await SendUpgradeRequestAsync<OdbUpgradePreview>(HttpMethod.Post,
            "/api/v1/odb-upgrade-previews", new { schemaVersion = 1, root, paths }, cancellationToken);
        OdbUpgradeContractValidation.Validate(preview);
        if (preview.Entries.Count != paths.Count || !preview.Entries.Select(entry => Path.GetFullPath(entry.SourcePath))
                .ToHashSet(StringComparer.OrdinalIgnoreCase).SetEquals(paths.Select(Path.GetFullPath)))
            throw new ControlPlaneException("升级预览与所选文件不一致，请重新检查。");
        return preview;
    }

    public async Task<OdbUpgradeOperationSnapshot> StartOdbUpgradeAsync(OdbUpgradePreview confirmedPreview,
        Guid clientRequestId, CancellationToken cancellationToken = default)
    {
        OdbUpgradeContractValidation.Validate(confirmedPreview);
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        await _operationCreationGate.WaitAsync(lifetime.Token);
        try
        {
            lock (_operationGate)
            {
                if (!_acceptNewOperations) throw new OperationCanceledException("应用正在关闭，不能开始升级。");
            }
            var snapshot = await SendUpgradeRequestAsync<OdbUpgradeOperationSnapshot>(HttpMethod.Post,
                "/api/v1/odb-upgrade-operations", new { schemaVersion = 1,
                    clientRequestId = clientRequestId.ToString("D"), preview = confirmedPreview, confirmed = true }, lifetime.Token);
            OdbUpgradeContractValidation.Validate(snapshot);
            if (snapshot.ClientRequestId != clientRequestId.ToString("D"))
                throw new ControlPlaneException("升级任务请求标识不匹配。");
            return snapshot;
        }
        finally { _operationCreationGate.Release(); }
    }

    public async Task<OdbUpgradeOperationListResponse> ListOdbUpgradeOperationsAsync(bool activeOnly = false,
        CancellationToken cancellationToken = default)
    {
        var response = await SendUpgradeRequestAsync<OdbUpgradeOperationListResponse>(HttpMethod.Get,
            "/api/v1/odb-upgrade-operations" + (activeOnly ? "?activeOnly=true" : ""), null, cancellationToken);
        if (response.SchemaVersion != 1 || response.Operations is null)
            throw new ControlPlaneException("升级任务列表无效。");
        foreach (var snapshot in response.Operations)
        {
            OdbUpgradeContractValidation.Validate(snapshot);
            if (activeOnly && snapshot.IsTerminal) throw new ControlPlaneException("活动升级列表包含已结束任务。");
        }
        return response;
    }

    public async Task<OdbUpgradeOperationSnapshot> GetOdbUpgradeOperationAsync(string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        var snapshot = await SendUpgradeRequestAsync<OdbUpgradeOperationSnapshot>(HttpMethod.Get,
            $"/api/v1/odb-upgrade-operations/{Uri.EscapeDataString(operationId)}", null, cancellationToken);
        OdbUpgradeContractValidation.Validate(snapshot, operationId);
        return snapshot;
    }

    public async Task<OdbUpgradeOperationSnapshot> CancelOdbUpgradeOperationAsync(string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        var snapshot = await SendUpgradeRequestAsync<OdbUpgradeOperationSnapshot>(HttpMethod.Post,
            $"/api/v1/odb-upgrade-operations/{Uri.EscapeDataString(operationId)}/cancel", null, cancellationToken);
        OdbUpgradeContractValidation.Validate(snapshot, operationId);
        return snapshot;
    }

    public async Task<OdbUpgradeOperationSnapshot> PollOdbUpgradeUntilTerminalAsync(
        OdbUpgradeOperationSnapshot initial, IProgress<OdbUpgradeOperationSnapshot>? progress = null,
        CancellationToken cancellationToken = default)
    {
        OdbUpgradeContractValidation.Validate(initial);
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        var snapshot = initial;
        while (!snapshot.IsTerminal)
        {
            await Task.Delay(500, lifetime.Token);
            snapshot = await GetOdbUpgradeOperationAsync(snapshot.OperationId, lifetime.Token);
            progress?.Report(snapshot);
        }
        return snapshot;
    }
}
