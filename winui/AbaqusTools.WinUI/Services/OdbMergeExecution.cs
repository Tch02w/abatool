namespace AbaqusTools.WinUI.Services;

internal enum OdbMergeCommand { None, Manual, Batch }

internal static class OdbMergeExecution
{
    internal static bool CanStop(bool batchBusy, bool manualBusy, string? manualId, bool cancelRequested) =>
        !cancelRequested && (batchBusy || (manualBusy && !string.IsNullOrWhiteSpace(manualId)));

    internal static OdbMergeCommand Resolve(int modeIndex, bool busy, bool planReady, bool hasChainPlan)
    {
        if (busy || !planReady) return OdbMergeCommand.None;
        return modeIndex switch
        {
            0 when hasChainPlan => OdbMergeCommand.Batch,
            1 when !hasChainPlan => OdbMergeCommand.Manual,
            _ => OdbMergeCommand.None,
        };
    }
}
