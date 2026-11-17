namespace AbaqusTools.WinUI.Services;

/// <summary>Coalesces log snapshots while a reader selects or copies text.</summary>
internal sealed class RuntimeLogUpdateState(string initialText)
{
    private string? _jobKey;
    private string _displayedText = initialText;
    private string? _pendingText;

    public bool HasPendingText => _pendingText is not null;

    public RuntimeLogTextUpdate? SetSnapshot(string? jobKey, string text, bool interacting)
    {
        var changedJob = !string.Equals(_jobKey, jobKey, StringComparison.Ordinal);
        _jobKey = jobKey;
        if (changedJob)
        {
            _pendingText = null;
            _displayedText = text;
            return new RuntimeLogTextUpdate(text, ResetView: true);
        }

        if (string.Equals(_displayedText, text, StringComparison.Ordinal))
        {
            _pendingText = null;
            return null;
        }

        _pendingText = text;
        return Flush(interacting);
    }

    public RuntimeLogTextUpdate? Flush(bool interacting)
    {
        if (interacting || _pendingText is null)
        {
            return null;
        }

        _displayedText = _pendingText;
        _pendingText = null;
        return new RuntimeLogTextUpdate(_displayedText, ResetView: false);
    }

    public static bool ShouldFollowTail(double verticalOffset, double scrollableHeight) =>
        scrollableHeight - verticalOffset <= 1.0;
}

internal sealed record RuntimeLogTextUpdate(string Text, bool ResetView);
