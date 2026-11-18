namespace AbaqusTools.WinUI.Services;

public sealed partial class ControlPlaneHost
{
    public Task<JobNotificationSnapshot> GetJobNotificationsAsync(CancellationToken cancellationToken = default) =>
        SendNotificationRequestAsync(HttpMethod.Get, "/api/v1/job-notifications", null, cancellationToken);

    public Task<JobNotificationSnapshot> AcknowledgeJobNotificationsAsync(IReadOnlyList<string> ids,
        CancellationToken cancellationToken = default) =>
        SendNotificationRequestAsync(HttpMethod.Post, "/api/v1/job-notification-acknowledgements",
            new { schemaVersion = 1, ids }, cancellationToken);

    private async Task<JobNotificationSnapshot> SendNotificationRequestAsync(HttpMethod method, string path,
        object? body, CancellationToken cancellationToken)
    {
        using var effective = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        effective.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effective.Token);
        var snapshot = await SendJsonRequestAsync<JobNotificationSnapshot>(descriptor, method, path, body,
            "作业结束提醒", effective.Token);
        if (!snapshot.IsValid) throw new ControlPlaneException("控制面返回了无效的作业提醒。");
        return snapshot;
    }
}
