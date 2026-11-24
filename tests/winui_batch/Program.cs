using AbaqusTools.WinUI.Services;

var tests = new (string Name, Func<Task> Run)[]
{
    ("execution follows the current mode and checked plan", CheckExecutionCommandAsync),
    ("manual Stop requires an acknowledged operation, while batch Stop can be queued", CheckStopAsync),
    ("populating a saved graph and undoing edits preserve its clean state", GraphEditsAsync),
    ("shared ancestor uses verified auto-numbered output", SharedAncestorAsync),
    ("prefix cache is isolated to one batch", NoCrossBatchReuseAsync),
    ("failed stage prevents descendants and preserves completed targets", FailedStageAsync),
    ("cancellation during a step prevents its descendant", CancelDuringStepAsync),
    ("cancellation between steps prevents the next step", CancelBetweenStepsAsync),
    ("cancellation between targets prevents the next target", CancelBetweenTargetsAsync),
    ("cancellation on final progress does not return success", CancelAtFinishAsync),
    ("invalid plans are rejected before any side effect", InvalidPlansAsync),
    ("empty published output stops the chain", EmptyPublishedOutputAsync),
    ("draft edits cannot alter running step lists", SnapshotAsync),
};

foreach (var (name, run) in tests)
{
    await run();
    Console.WriteLine($"PASS {name}");
}
Console.WriteLine($"{tests.Length} batch-runner tests passed.");

static Task CheckExecutionCommandAsync()
{
    foreach (var mode in new[] { -1, 0, 1, 2 })
    foreach (var busy in new[] { false, true })
    foreach (var ready in new[] { false, true })
    foreach (var chain in new[] { false, true })
    {
        var expected = (mode, busy, ready, chain) switch
        {
            (0, false, true, true) => OdbMergeCommand.Batch,
            (1, false, true, false) => OdbMergeCommand.Manual,
            _ => OdbMergeCommand.None,
        };
        Equal(expected, OdbMergeExecution.Resolve(mode, busy, ready, chain),
            $"mode={mode}, busy={busy}, ready={ready}, chain={chain}");
    }
    return Task.CompletedTask;
}

static string Odb(string name) => Path.Combine(Path.GetTempPath(), "abatool-batch-runner-tests", $"{name}.odb");

static Task CheckStopAsync()
{
    foreach (var id in new string?[] { null, "", "   " })
        Equal(false, OdbMergeExecution.CanStop(false, true, id, false), "Manual submission without a usable ID");
    Equal(true, OdbMergeExecution.CanStop(false, true, "accepted", false), "Acknowledged manual operation");
    Equal(false, OdbMergeExecution.CanStop(false, true, "accepted", true), "Pending manual cancellation");
    Equal(false, OdbMergeExecution.CanStop(false, false, "previous", false), "Completed manual operation");
    Equal(true, OdbMergeExecution.CanStop(true, false, null, false), "Batch can queue cancellation before acknowledgement");
    Equal(false, OdbMergeExecution.CanStop(true, false, null, true), "Pending batch cancellation");
    return Task.CompletedTask;
}

static Task GraphEditsAsync()
{
    static OdbResultGraphNode Node() => new() { NodeId = "base", Name = "基础", OdbPath = Odb("cube"), InpPath = "cube.inp" };
    var graph = new OdbResultGraphSnapshot { OutputDirectory = "输出", Nodes = [Node()] };
    var loaded = Node();
    Equal(false, graph.HasEdits("输出", [loaded]), "Populating controls with saved values must remain clean.");
    Equal(true, graph.HasEdits("输出 ", [loaded]), "The raw directory text is part of the editable draft.");
    Equal(true, graph.HasEdits("输出", []), "Removing a node must be detected.");
    loaded.Name = "修改";
    Equal(true, graph.HasEdits("输出", [loaded]), "A node edit must enable save.");
    loaded.Name = "基础";
    Equal(false, graph.HasEdits("输出", [loaded]), "Reverting an edit must restore the clean state.");
    return Task.CompletedTask;
}

static RestartResultStep Step(int index, string name, string original, string restart, string output) => new()
{
    Index = index,
    JobId = name,
    JobName = name,
    OriginalOdb = Odb(original),
    RestartOdb = Odb(restart),
    OutputOdb = Odb(output),
    Status = "ready",
};

static RestartResultPlan Plan(string target, params RestartResultStep[] steps) => new()
{
    Valid = true,
    TargetJobId = target,
    TargetJobName = target,
    Steps = steps,
    FinalOutputOdb = steps.LastOrDefault()?.OutputOdb ?? string.Empty,
};

static RestartResultPlan[] Branches() =>
[
    Plan("C", Step(1, "B", "A", "B", "B_full"), Step(2, "C", "B_full", "C", "C_full")),
    Plan("D", Step(1, "B", "a", "b", "b_FULL"), Step(2, "D", "b_FULL", "D", "D_full")),
];

static async Task SharedAncestorAsync()
{
    var executed = new List<string>();
    var progress = new List<OdbBatchProgress>();
    var results = await OdbResultBatchRunner.RunAsync(Branches(), (step, original, _) =>
    {
        executed.Add(step.JobName);
        if (step.JobName is "C" or "D")
        {
            Equal(Odb("B_full_2"), original, "Children must consume the published prefix path.");
        }
        return Task.FromResult(step.JobName == "B" ? Odb("B_full_2") : step.OutputOdb);
    }, progress.Add, CancellationToken.None);

    Equal("B,C,D", string.Join(',', executed), "Common prefix must execute once.");
    Equal(2, results.Count, "Both targets must finish.");
    Equal(Odb("D_full"), results[1].OutputOdb, "Wrong final path.");
    Equal(1, progress.Count(item => item.Reused), "One logical step should be reused.");
    Equal(4, progress[^1].CompletedSteps, "Progress counts logical per-target steps.");
    Equal(4, progress[^1].TotalSteps, "Wrong logical step total.");
    Equal(2, progress[^1].CompletedTargets, "Wrong target total.");
}

static async Task NoCrossBatchReuseAsync()
{
    var executions = 0;
    for (var index = 0; index < 2; index++)
    {
        await OdbResultBatchRunner.RunAsync(Branches(), (step, _, _) =>
        {
            executions++;
            return Task.FromResult(step.OutputOdb);
        }, _ => { }, CancellationToken.None);
    }
    Equal(6, executions, "A new batch must execute its own prefixes.");
}

static async Task FailedStageAsync()
{
    var executed = new List<string>();
    var completed = new List<OdbBatchTargetResult>();
    var plans = new[]
    {
        Plan("B", Step(1, "B", "A", "B", "B_full")),
        Plan("D", Step(1, "B", "A", "B", "B_full"),
            Step(2, "C", "B_full", "C", "C_full"), Step(3, "D", "C_full", "D", "D_full")),
    };
    await ThrowsAsync<InvalidOperationException>(() => OdbResultBatchRunner.RunAsync(plans, (step, _, _) =>
    {
        executed.Add(step.JobName);
        return step.JobName == "C"
            ? Task.FromException<string>(new InvalidOperationException("merge failed"))
            : Task.FromResult(step.OutputOdb);
    }, progress =>
    {
        if (progress.Result is not null) completed.Add(progress.Result);
    }, CancellationToken.None));
    Equal("B,C", string.Join(',', executed), "Failure must prevent descendant execution.");
    Equal("B", completed.Single().TargetJobName, "Published prior target must remain reported.");
}

static async Task CancelDuringStepAsync()
{
    using var cancellation = new CancellationTokenSource();
    var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
    var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
    var executions = 0;
    var run = OdbResultBatchRunner.RunAsync([Branches()[0]], async (step, _, token) =>
    {
        Equal(cancellation.Token, token, "Cancellation token must reach the operation.");
        executions++;
        entered.SetResult();
        await release.Task;
        return step.OutputOdb;
    }, _ => { }, cancellation.Token);
    await entered.Task;
    cancellation.Cancel();
    release.SetResult();
    await ThrowsAsync<OperationCanceledException>(async () => await run);
    Equal(1, executions, "Cancellation during await must prevent the next step.");
}

static async Task CancelBetweenStepsAsync()
{
    using var cancellation = new CancellationTokenSource();
    var executions = 0;
    await ThrowsAsync<OperationCanceledException>(() => OdbResultBatchRunner.RunAsync([Branches()[0]], (step, _, _) =>
    {
        executions++;
        return Task.FromResult(step.OutputOdb);
    }, progress =>
    {
        if (progress.CompletedSteps == 1) cancellation.Cancel();
    }, cancellation.Token));
    Equal(1, executions, "Cancellation in progress must prevent the next step.");
}

static async Task CancelBetweenTargetsAsync()
{
    using var cancellation = new CancellationTokenSource();
    var executed = new List<string>();
    var completed = new List<OdbBatchTargetResult>();
    await ThrowsAsync<OperationCanceledException>(() => OdbResultBatchRunner.RunAsync(Branches(), (step, _, _) =>
    {
        executed.Add(step.JobName);
        return Task.FromResult(step.OutputOdb);
    }, progress =>
    {
        if (progress.Result is not null)
        {
            completed.Add(progress.Result);
            cancellation.Cancel();
        }
    }, cancellation.Token));
    Equal("B,C", string.Join(',', executed), "Second target must not start.");
    Equal("C", completed.Single().TargetJobName, "First result must remain available.");
}

static async Task CancelAtFinishAsync()
{
    using var cancellation = new CancellationTokenSource();
    await ThrowsAsync<OperationCanceledException>(() => OdbResultBatchRunner.RunAsync(
        [Plan("B", Step(1, "B", "A", "B", "B_full"))],
        (step, _, _) => Task.FromResult(step.OutputOdb),
        progress => { if (progress.Result is not null) cancellation.Cancel(); },
        cancellation.Token));
}

static async Task InvalidPlansAsync()
{
    var good = Plan("B", Step(1, "B", "A", "B", "B_full"));
    var invalid = new RestartResultPlan[]
    {
        new() { Valid = false, TargetJobName = "invalid", Steps = good.Steps },
        Plan("empty"),
        Plan("C", Step(1, "B", "A", "B", "B_full"), Step(2, "C", "wrong", "C", "C_full")),
        Plan("B", Step(2, "B", "A", "B", "B_full")),
        Plan("B", new RestartResultStep { Index = 1, JobName = "B", OriginalOdb = Odb("A"), OutputOdb = Odb("B_full") }),
        Plan("B", Step(1, "B", "A", "B", "a")),
        new() { Valid = true, TargetJobName = "B", Steps = good.Steps, FinalOutputOdb = Odb("wrong") },
    };
    var executions = 0;
    foreach (var bad in invalid)
    {
        await ThrowsAsync<ArgumentException>(() => OdbResultBatchRunner.RunAsync([good, bad], (step, _, _) =>
        {
            executions++;
            return Task.FromResult(step.OutputOdb);
        }, _ => { }, CancellationToken.None));
    }
    await ThrowsAsync<ArgumentException>(() => OdbResultBatchRunner.RunAsync([], (step, _, _) =>
    {
        executions++;
        return Task.FromResult(step.OutputOdb);
    }, _ => { }, CancellationToken.None));
    Equal(0, executions, "Entire batch must validate before executing the first valid target.");
}

static async Task EmptyPublishedOutputAsync()
{
    var executions = 0;
    await ThrowsAsync<InvalidOperationException>(() => OdbResultBatchRunner.RunAsync([Branches()[0]], (_, _, _) =>
    {
        executions++;
        return Task.FromResult(" ");
    }, _ => { }, CancellationToken.None));
    Equal(1, executions, "Missing published output must stop descendants.");
}

static async Task SnapshotAsync()
{
    var editable = Branches()[0].Steps.ToList();
    var plan = new RestartResultPlan
    {
        Valid = true, TargetJobName = "C", Steps = editable, FinalOutputOdb = Odb("C_full"),
    };
    var executed = new List<string>();
    await OdbResultBatchRunner.RunAsync([plan], (step, _, _) =>
    {
        executed.Add(step.JobName);
        editable.Clear();
        return Task.FromResult(step.OutputOdb);
    }, _ => { }, CancellationToken.None);
    Equal("B,C", string.Join(',', executed), "Batch must use its validated snapshot.");
}

static void Equal<T>(T expected, T actual, string message)
{
    if (!EqualityComparer<T>.Default.Equals(expected, actual))
        throw new InvalidOperationException($"{message} Expected {expected}; actual {actual}.");
}

static async Task ThrowsAsync<T>(Func<Task> action) where T : Exception
{
    try { await action(); }
    catch (T) { return; }
    throw new InvalidOperationException($"Expected {typeof(T).Name}.");
}
