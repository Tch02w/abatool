namespace AbaqusTools.WinUI.Services;

/// <summary>OS session end is distinct from the interactive workbench close protocol.</summary>
public sealed class SystemSessionEndState(Func<Task> saveDraft, TimeSpan saveBudget)
{
    public const uint QueryEndSession = 0x0011;
    public const uint EndSession = 0x0016;
    public bool IsQueryPending { get; private set; }
    public bool IsEnding { get; private set; }
    public string? SaveError { get; private set; }

    public bool TryHandle(uint message, nuint wParam, out nint result)
    {
        result = 0;
        if (message == QueryEndSession)
        {
            // No disk, network or dialog on QUERY. Flags do not change this decision.
            IsQueryPending = true;
            result = 1;
            return true;
        }
        if (message != EndSession) return false;
        IsQueryPending = false;
        if (wParam == 0 || IsEnding) return true;
        IsEnding = true;
        try
        {
            // The callback captures controls synchronously; only the disk task is awaited.
            var saving = saveDraft();
            _ = saving.ContinueWith(task => { _ = task.Exception; },
                CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
            if (!saving.Wait(saveBudget)) SaveError = "系统会话结束保存未在限定时间内完成。";
        }
        catch (Exception error)
        {
            SaveError = error.GetBaseException().Message;
        }
        return true;
    }
}
