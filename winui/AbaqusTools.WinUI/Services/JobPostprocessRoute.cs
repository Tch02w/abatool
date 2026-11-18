namespace AbaqusTools.WinUI.Services;

/// <summary>A captured user selection, not a runtime or result-path cache.</summary>
public sealed record JobPostprocessTarget(string Kind, string ItemId, string AttemptId,
    string JobName, string InputPath)
{
    public static JobPostprocessTarget Local(JobQueueItem item) =>
        new("local", item.ItemId, item.AttemptId, item.JobName, item.InpPath);
    public static JobPostprocessTarget Draft(string input, string name, bool remote) =>
        new(remote ? "remote" : "draft", "", "", name.Trim(), input.Trim());
}

public sealed record JobPostprocessRoute(string Path, string Source)
{
    public static async Task<JobPostprocessRoute> ResolveAsync(JobPostprocessTarget target,
        Func<Task<LocalQueueRuntimeSnapshot>> readRuntime)
    {
        if (target.Kind == "remote")
            throw new InvalidOperationException("当前作业在服务器上。请在计算资源的文件浏览器中将结果下载到你选择的本地目录，再在 ODB 后处理中读取该目录。");
        var runtime = await readRuntime();
        return await Task.Run(() => Resolve(target, runtime));
    }

    public static JobPostprocessRoute Resolve(JobPostprocessTarget target, LocalQueueRuntimeSnapshot runtime)
    {
        if (target.Kind == "remote")
            throw new InvalidOperationException("服务器 ODB 尚未下载，请先选择本地结果文件。");
        JobQueueItem? item;
        if (target.Kind == "local")
        {
            item = runtime.Queue.QueueItems.SingleOrDefault(row => row.ItemId == target.ItemId)
                ?? throw new InvalidOperationException("所选作业已不在队列中，请重新选择作业。");
            if (item.AttemptId != target.AttemptId || item.JobName != target.JobName
                || !SamePath(item.InpPath, target.InputPath))
                throw new InvalidOperationException("所选作业的运行批次或输入已变化，请重新选择后再打开结果。");
        }
        else if (target.Kind == "draft")
        {
            if (!System.IO.Path.IsPathFullyQualified(target.InputPath)
                || !string.Equals(System.IO.Path.GetExtension(target.InputPath), ".inp", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("请先在新建作业页选择本地 INP，或在作业概览中选择已有作业。");
            var name = string.IsNullOrWhiteSpace(target.JobName)
                ? System.IO.Path.GetFileNameWithoutExtension(target.InputPath) : target.JobName;
            var matches = runtime.Queue.QueueItems.Where(row => SamePath(row.InpPath, target.InputPath)
                && string.Equals(row.JobName, name, StringComparison.OrdinalIgnoreCase)).ToArray();
            if (matches.Length > 1)
                throw new InvalidOperationException("同一输入有多个作业记录，请在作业概览中明确选择要打开的一次作业。");
            item = matches.SingleOrDefault();
            if (item is null)
                return Existing(System.IO.Path.GetDirectoryName(target.InputPath)!, name, "当前输入目录（未关联运行记录）");
        }
        else throw new InvalidOperationException("当前没有明确的作业，请在作业概览中选择一个作业。");

        if (runtime.ActiveItemIds.Contains(item.ItemId)
            || runtime.Operations.Any(operation => operation.ItemId == item.ItemId && operation.Active)
            || item.Status is "运行中" or "启动中" or "正在终止" or "待确认" or "状态未知" or "状态确认中")
            throw new InvalidOperationException("所选作业仍在执行、归档或等待状态确认，请待该操作结束后再送入后处理。");
        if (item.HasPublishedArchive)
            return Existing(item.ArchiveDestination, item.JobName, "已发布归档");
        if (!string.IsNullOrWhiteSpace(item.EffectiveWorkDir))
            return Existing(item.EffectiveWorkDir, item.JobName, "实际计算目录");
        if (!string.IsNullOrWhiteSpace(item.AttemptId))
            throw new InvalidOperationException("该次运行未记录实际计算目录，请在作业概览核对结果位置，或手动读取结果目录。");
        return Existing(System.IO.Path.GetDirectoryName(item.InpPath) ?? "", item.JobName, "输入目录（尚无运行目录）");
    }

    private static JobPostprocessRoute Existing(string directory, string name, string source)
    {
        if (string.IsNullOrWhiteSpace(directory) || !System.IO.Path.IsPathFullyQualified(directory)
            || string.IsNullOrWhiteSpace(name) || name.IndexOfAny(System.IO.Path.GetInvalidFileNameChars()) >= 0
            || name is "." or ".." || name.EndsWith('.') || name.EndsWith(' '))
            throw new InvalidOperationException("作业名称或结果目录无效，请在作业概览中核对。");
        var path = System.IO.Path.GetFullPath(System.IO.Path.Combine(directory, name + ".odb"));
        if (File.Exists(System.IO.Path.ChangeExtension(path, ".lck")))
            throw new InvalidOperationException($"ODB 存在锁文件，请先确认 Abaqus 已关闭该文件：{path}");
        var file = new FileInfo(path);
        if (!file.Exists || file.Length == 0)
            throw new InvalidOperationException($"{source}中没有可用的作业 ODB：{path}。请核对计算或归档状态，也可以手动读取正确的结果目录。");
        return new(path, source);
    }

    private static bool SamePath(string left, string right)
    {
        if (System.IO.Path.IsPathFullyQualified(left) && System.IO.Path.IsPathFullyQualified(right))
        {
            left = System.IO.Path.GetFullPath(left);
            right = System.IO.Path.GetFullPath(right);
        }
        return string.Equals(left, right, StringComparison.OrdinalIgnoreCase);
    }
}
