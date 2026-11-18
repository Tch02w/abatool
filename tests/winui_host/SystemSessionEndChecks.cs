using System.Diagnostics;
using AbaqusTools.WinUI.Services;

static class SystemSessionEndChecks
{
    public static async Task RunAsync(string directory)
    {
        if (Directory.Exists(directory) || File.Exists(directory)) throw new Exception("Use a new evidence directory");
        Directory.CreateDirectory(directory);
        var saves = 0;
        var ending = new SystemSessionEndState(() => { saves++; return Task.CompletedTask; }, TimeSpan.FromSeconds(2));
        Require(!ending.TryHandle(0x0010, 0, out _), "Ordinary close must retain its own protocol");
        Require(ending.TryHandle(SystemSessionEndState.QueryEndSession, 0, out var answer) && answer == 1
            && ending.IsQueryPending && !ending.IsEnding && saves == 0, "Query must return immediately without saving");
        ending.TryHandle(SystemSessionEndState.EndSession, 0, out _);
        Require(!ending.IsQueryPending && !ending.IsEnding && saves == 0, "Cancelled logoff changed the session");
        ending.TryHandle(SystemSessionEndState.QueryEndSession, 0, out _);
        ending.TryHandle(SystemSessionEndState.EndSession, 1, out answer);
        Require(answer == 0 && ending.IsEnding && saves == 1 && ending.SaveError is null, "Confirmed end was not saved");
        ending.TryHandle(SystemSessionEndState.EndSession, 1, out _);
        ending.TryHandle(SystemSessionEndState.EndSession, 0, out _);
        Require(saves == 1 && ending.IsEnding, "Duplicate/end cancellation reversed a confirmed end");

        var failed = new SystemSessionEndState(() => throw new IOException("write denied"), TimeSpan.FromSeconds(2));
        failed.TryHandle(SystemSessionEndState.EndSession, 1, out _);
        Require(failed.IsEnding && failed.SaveError == "write denied", "Save failure escaped or became success");
        var asyncFailure = new SystemSessionEndState(() => Task.FromException(new IOException("disk failed")), TimeSpan.FromSeconds(2));
        asyncFailure.TryHandle(SystemSessionEndState.EndSession, 1, out _);
        Require(asyncFailure.SaveError == "disk failed", "Async write failure was hidden");
        var pending = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var timeout = new SystemSessionEndState(() => pending.Task, TimeSpan.FromMilliseconds(25));
        var clock = Stopwatch.StartNew();
        timeout.TryHandle(SystemSessionEndState.EndSession, 1, out _);
        Require(clock.Elapsed < TimeSpan.FromSeconds(1) && timeout.SaveError is not null, "Session end waited without a bound");
        pending.SetResult();

        var path = Path.Combine(directory, "中文 草稿.json");
        var store = new WorkbenchSessionStore(path);
        var state = store.Load();
        state.Pages["new-job"] = new() { ["CpuNumberBox"] = "1+" };
        var first = store.SaveAsync(state);
        state.Pages["new-job"]["CpuNumberBox"] = "20";
        await first;
        Require(new WorkbenchSessionStore(path).Load().Pages["new-job"]["CpuNumberBox"] == "1+",
            "Background writer read mutated UI state instead of its captured snapshot");
        var writes = new List<Task>();
        for (var index = 0; index < 64; index++)
        {
            state.Pages["new-job"]["CpuNumberBox"] = index.ToString();
            writes.Add(store.SaveAsync(state));
        }
        await Task.WhenAll(writes);
        Require(new WorkbenchSessionStore(path).Load().Pages["new-job"]["CpuNumberBox"] == "63",
            "Older checkpoint overwrote the latest draft");
        var stamp = new DateTime(2020, 1, 2, 3, 4, 5, DateTimeKind.Utc);
        File.SetLastWriteTimeUtc(path, stamp);
        await store.SaveAsync(state);
        Require(File.GetLastWriteTimeUtc(path) == stamp, "Unchanged inputs caused another disk write");
        File.Move(path, path + ".previous");
        await store.SaveAsync(state);
        Require(File.Exists(path), "A missing checkpoint was never recreated");
        Require(Directory.GetFiles(directory, "*.tmp").Length == 0, "Atomic writes left temporary files");

        var blocker = Path.Combine(directory, "blocked");
        File.WriteAllText(blocker, "preserve this blocker");
        var retry = new WorkbenchSessionStore(Path.Combine(blocker, "session.json"));
        var rejected = false;
        try { await retry.SaveAsync(state); }
        catch (IOException) { rejected = true; }
        Require(rejected, "Blocked write reported success");
        File.Move(blocker, blocker + ".original");
        await retry.SaveAsync(state);
        Require(new WorkbenchSessionStore(Path.Combine(blocker, "session.json")).Load().Pages["new-job"]["CpuNumberBox"] == "63",
            "A failed checkpoint poisoned the next write");
        Console.WriteLine("15 session-end and asynchronous draft checks passed; no native window or OS shutdown invoked.");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }
}
