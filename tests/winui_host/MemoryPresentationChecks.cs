using System.Text.Json;
using AbaqusTools.WinUI.Services;

internal static class MemoryPresentationChecks
{
    internal static void Run()
    {
        var legacy = JsonSerializer.Deserialize<JobQueueItem>("{}");
        if (legacy?.RuntimeMemoryDisplay != "未统计") throw new Exception("Legacy memory defaults changed");
        foreach (var (status, expected) in new[] { ("unavailable", "暂不可读"), ("stale", "待更新"),
                                                  ("waiting", "采集中"), ("ended", "已结束") })
        {
            var item = new JobQueueItem { RuntimeMemoryBytes = 123, MemoryObservationStatus = status };
            if (item.RuntimeMemoryDisplay != expected) throw new Exception("Unknown/stale memory rendered as current usage");
        }
        var observed = JsonSerializer.Deserialize<JobQueueItem>("""
            {"runtimeMemoryBytes":1073741824,"memoryObservationStatus":"observed","memoryPeakBytes":2147483648,
             "memoryEstimatedBytes":3221225472,"memoryEstimateSource":"history","memorySampleCount":4}
            """);
        if (observed?.RuntimeMemoryDisplay != "1.0 GB" || observed.MemorySampleCount != 4 ||
            !observed.MemoryDetailsDisplay.Contains("同模型历史") || !observed.MemoryDetailsDisplay.Contains("2.0 GB"))
            throw new Exception("Memory estimate and current working set must remain distinct");
        Console.WriteLine("6 native memory presentation checks passed.");
    }
}
