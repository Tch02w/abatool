using System.Text.Json;
using AbaqusTools.WinUI.Services;

internal static class JobNotificationChecks
{
    internal static void Run()
    {
        var notification = new JobNotification { Id = new string('a', 64), Source = "local", JobId = "item",
            ExecutionId = "attempt", JobName = "case", Status = "failed", ObservedAt = DateTimeOffset.UtcNow };
        var snapshot = new JobNotificationSnapshot { SchemaVersion = 1, UnreadCount = 1, Items = [notification] };
        var state = new JobNotificationPresentation();
        if (!state.Apply(snapshot) || state.Apply(snapshot)) throw new Exception("A repeated poll must not repeat attention");
        if (notification.Heading != "本机 · case · 失败" || notification.JobKey != "local:item")
            throw new Exception("Notification routing or failure label is wrong");
        state.Apply(new JobNotificationSnapshot { SchemaVersion = 1 });
        if (state.Apply(snapshot)) throw new Exception("Replayed notification must not repeat attention");
        foreach (var malformed in new[] {
            """{"schemaVersion":1,"unreadCount":1,"items":[]}""",
            """{"schemaVersion":1,"unreadCount":0,"items":[null]}""",
            """{"schemaVersion":1,"unreadCount":0,"items":null}""",
            """{"schemaVersion":1,"unreadCount":-1,"items":[]}"""
        })
        {
            if (JsonSerializer.Deserialize<JobNotificationSnapshot>(malformed)!.IsValid)
                throw new Exception("Malformed inbox cannot be rendered as empty/success");
        }
        var duplicates = new JobNotificationSnapshot { SchemaVersion = 1, UnreadCount = 2, Items = [notification, notification] };
        if (duplicates.IsValid) throw new Exception("Duplicate notification IDs must be rejected");
        var oldRequest = JsonSerializer.Deserialize<RemoteJobRequest>("{}");
        if (oldRequest?.Notify != true) throw new Exception("Legacy remote notification default changed");
        var disabled = new RemoteJobRequest { Notify = false };
        if (!JsonSerializer.Serialize(disabled).Contains("\"notify\":false")) throw new Exception("Notification opt-out lost");
        Console.WriteLine("10 job notification contract and presentation checks passed.");
    }
}
