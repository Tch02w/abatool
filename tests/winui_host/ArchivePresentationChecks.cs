using System.Text.Json;
using AbaqusTools.WinUI.Services;

internal static class ArchivePresentationChecks
{
    internal static void Run()
    {
        var legacy = JsonSerializer.Deserialize<JobQueueItem>("{\"message\":\"计算已完成\"}")!;
        if (legacy.HasPublishedArchive || legacy.ArchiveDetailsDisplay != ""
            || legacy.ResultMessageDisplay != "计算已完成") throw new Exception("Legacy archive defaults changed");
        foreach (var status in new[] { "已归档", "已归档，清理未完成", "归档失败", "归档需核对", "" })
        {
            var item = new JobQueueItem { ArchiveStatus = status, ArchiveDestination = "archive",
                ArchiveError = status == "归档失败" ? "copy failed" : "", Message = "计算已完成" };
            var published = status is "已归档" or "已归档，清理未完成";
            if (item.HasPublishedArchive != published) throw new Exception("Partial archive selected as output");
            if (status != "" && !item.ResultMessageDisplay.Contains(status)) throw new Exception("Archive outcome hidden");
            if (status == "归档失败" && !item.ArchiveDetailsDisplay.Contains("copy failed"))
                throw new Exception("Archive failure reason hidden");
        }
        Console.WriteLine("6 archive presentation and legacy compatibility checks passed.");
    }
}
