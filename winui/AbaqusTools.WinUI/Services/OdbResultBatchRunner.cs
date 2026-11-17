namespace AbaqusTools.WinUI.Services;

public sealed record OdbBatchTargetResult(string TargetJobName, string OutputOdb);

public sealed record OdbBatchProgress(
    int CompletedSteps,
    int TotalSteps,
    int CompletedTargets,
    int TotalTargets,
    string TargetJobName,
    string StageJobName,
    OdbBatchTargetResult? Result = null,
    bool Reused = false);

/// <summary>
/// Executes validated ancestry plans using the existing protected merge operation.
/// Published prefixes are reusable only within this invocation and its fixed options.
/// </summary>
public static class OdbResultBatchRunner
{
    public static async Task<IReadOnlyList<OdbBatchTargetResult>> RunAsync(
        IReadOnlyList<RestartResultPlan> plans,
        Func<RestartResultStep, string, CancellationToken, Task<string>> executeStep,
        Action<OdbBatchProgress> report,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(plans);
        ArgumentNullException.ThrowIfNull(executeStep);
        ArgumentNullException.ThrowIfNull(report);
        cancellationToken.ThrowIfCancellationRequested();

        // Validate every target before running even the first merge, and freeze the
        // step lists so edits to the draft cannot alter an in-flight batch.
        var snapshots = plans.Select(SnapshotAndValidate).ToArray();
        if (snapshots.Length == 0)
        {
            throw new ArgumentException("请至少选择一个有效的完整结果目标。", nameof(plans));
        }

        var totalSteps = snapshots.Sum(plan => plan.Steps.Length);
        var completedSteps = 0;
        var results = new List<OdbBatchTargetResult>();
        var publishedPrefixes = new Dictionary<PrefixKey, string>();
        cancellationToken.ThrowIfCancellationRequested();
        report(new OdbBatchProgress(0, totalSteps, 0, snapshots.Length, string.Empty, string.Empty));

        foreach (var plan in snapshots)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var currentFullResult = plan.Steps[0].OriginalOdb;
            for (var index = 0; index < plan.Steps.Length; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var step = plan.Steps[index];
                var key = new PrefixKey(
                    PathKey(currentFullResult), PathKey(step.RestartOdb), PathKey(step.OutputOdb));
                var reused = publishedPrefixes.TryGetValue(key, out var publishedOutput);
                if (!reused)
                {
                    publishedOutput = await executeStep(step, currentFullResult, cancellationToken);
                    cancellationToken.ThrowIfCancellationRequested();
                    if (string.IsNullOrWhiteSpace(publishedOutput))
                    {
                        throw new InvalidOperationException($"阶段 {step.JobName} 未返回已验证的结果路径。");
                    }
                    publishedPrefixes.Add(key, publishedOutput);
                }

                cancellationToken.ThrowIfCancellationRequested();
                currentFullResult = publishedOutput!;
                completedSteps++;
                OdbBatchTargetResult? result = null;
                if (index == plan.Steps.Length - 1)
                {
                    result = new OdbBatchTargetResult(plan.TargetJobName, currentFullResult);
                    results.Add(result);
                }
                report(new OdbBatchProgress(
                    completedSteps, totalSteps, results.Count, snapshots.Length,
                    plan.TargetJobName, step.JobName, result, reused));
                cancellationToken.ThrowIfCancellationRequested();
            }
        }

        cancellationToken.ThrowIfCancellationRequested();
        return results.AsReadOnly();
    }

    private static PlanSnapshot SnapshotAndValidate(RestartResultPlan plan)
    {
        if (plan is null || !plan.Valid || plan.Steps is null || plan.Steps.Count == 0
            || string.IsNullOrWhiteSpace(plan.TargetJobName))
        {
            throw new ArgumentException("完整结果计划无效或未包含合并步骤。", nameof(plan));
        }

        var steps = plan.Steps.ToArray();
        for (var index = 0; index < steps.Length; index++)
        {
            var step = steps[index];
            if (step is null || step.Index != index + 1
                || string.IsNullOrWhiteSpace(step.JobName)
                || string.IsNullOrWhiteSpace(step.OriginalOdb)
                || string.IsNullOrWhiteSpace(step.RestartOdb)
                || string.IsNullOrWhiteSpace(step.OutputOdb))
            {
                throw new ArgumentException($"目标 {plan.TargetJobName} 的合并步骤不完整或顺序无效。", nameof(plan));
            }

            var original = PathKey(step.OriginalOdb);
            var restart = PathKey(step.RestartOdb);
            var output = PathKey(step.OutputOdb);
            if (original == restart || output == original || output == restart)
            {
                throw new ArgumentException($"阶段 {step.JobName} 的源文件和输出路径必须不同。", nameof(plan));
            }
            if (index > 0 && original != PathKey(steps[index - 1].OutputOdb))
            {
                throw new ArgumentException($"目标 {plan.TargetJobName} 的合并步骤没有按祖先链连续衔接。", nameof(plan));
            }
        }

        if (string.IsNullOrWhiteSpace(plan.FinalOutputOdb)
            || PathKey(plan.FinalOutputOdb) != PathKey(steps[^1].OutputOdb))
        {
            throw new ArgumentException($"目标 {plan.TargetJobName} 的最终结果与最后一个合并步骤不一致。", nameof(plan));
        }
        return new PlanSnapshot(plan.TargetJobName, steps);
    }

    private static string PathKey(string path) => Path.GetFullPath(path).ToUpperInvariant();

    private sealed record PlanSnapshot(string TargetJobName, RestartResultStep[] Steps);

    private sealed record PrefixKey(string OriginalOdb, string RestartOdb, string OutputOdb);
}
