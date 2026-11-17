using System.ComponentModel;
using System.Runtime.CompilerServices;
using AbaqusTools.WinUI.Services;

namespace AbaqusTools.WinUI.Models;

public sealed class OdbFileRow : INotifyPropertyChanged
{
    private string _compatibilityStatus = "unknown";
    private string _compatibilityStatusDisplay = "未检查";
    private string _compatibilityMessage = "尚未运行兼容性检查。";
    private string _postprocessStatusDisplay = "未分析";
    private string _postprocessSummary = "读取结构后可配置提取参数";
    private string _comparisonGroup = "对比组 1";
    private bool _hasPostprocessConfiguration;
    private bool _hasEditedPostprocessJob;

    public OdbFileRow(OdbDiscoveryItem item)
    {
        Path = item.Path;
        RelativePath = item.RelativePath;
        Name = item.Name;
        SizeBytes = item.SizeBytes;
        SizeDisplay = item.SizeDisplay;
        ModifiedAt = item.ModifiedAt;
        ModifiedDisplay = item.ModifiedDisplay;
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public OdbFileRow WithDiscovery(OdbDiscoveryItem item)
    {
        if (!string.Equals(System.IO.Path.GetFullPath(Path), System.IO.Path.GetFullPath(item.Path), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Cannot restore configuration to a different ODB.", nameof(item));
        var refreshed = new OdbFileRow(item)
        {
            ComparisonGroup = ComparisonGroup,
            PostprocessJob = PostprocessJob?.Clone(),
            _hasEditedPostprocessJob = _hasEditedPostprocessJob,
        };
        if (item.SizeBytes == SizeBytes && item.ModifiedAt == ModifiedAt)
        {
            refreshed.ScanDetails = ScanDetails;
            refreshed.HasPostprocessConfiguration = HasPostprocessConfiguration;
            refreshed.PostprocessStatusDisplay = PostprocessStatusDisplay;
            refreshed.PostprocessSummary = PostprocessSummary;
            refreshed.CompatibilityStatus = CompatibilityStatus;
            refreshed.CompatibilityStatusDisplay = CompatibilityStatusDisplay;
            refreshed.CompatibilityMessage = CompatibilityMessage;
        }
        else
        {
            refreshed.MarkStructureAnalysisIncomplete("ODB 文件已变化，请重新读取结构；已编辑参数仍保留。");
        }
        return refreshed;
    }

    public string Path { get; }

    public string RelativePath { get; }

    public string Name { get; }

    public long SizeBytes { get; }

    public string SizeDisplay { get; }

    public DateTimeOffset ModifiedAt { get; }

    public string ModifiedDisplay { get; }

    public OdbPostprocessScanItem? ScanDetails { get; private set; }

    public OdbPostprocessJobDraft? PostprocessJob { get; private set; }

    public string ComparisonGroup
    {
        get => _comparisonGroup;
        set => SetField(ref _comparisonGroup, value);
    }

    public string PostprocessStatusDisplay
    {
        get => _postprocessStatusDisplay;
        private set => SetField(ref _postprocessStatusDisplay, value);
    }

    public string PostprocessSummary
    {
        get => _postprocessSummary;
        private set => SetField(ref _postprocessSummary, value);
    }

    public bool HasPostprocessConfiguration
    {
        get => _hasPostprocessConfiguration;
        private set => SetField(ref _hasPostprocessConfiguration, value);
    }

    public string CompatibilityStatus
    {
        get => _compatibilityStatus;
        private set => SetField(ref _compatibilityStatus, value);
    }

    public string CompatibilityStatusDisplay
    {
        get => _compatibilityStatusDisplay;
        private set => SetField(ref _compatibilityStatusDisplay, value);
    }

    public string CompatibilityMessage
    {
        get => _compatibilityMessage;
        private set => SetField(ref _compatibilityMessage, value);
    }

    public void MarkPending()
    {
        SetCompatibility("pending", "等待检查", "已加入兼容性检查队列。", 0);
    }

    public void MarkRunning()
    {
        SetCompatibility("running", "正在检查", "Abaqus 正在读取此 ODB。", 0);
    }

    public void MarkIncomplete(string statusDisplay, string message)
    {
        SetCompatibility("incomplete", statusDisplay, message, 0);
    }

    public void ApplyCompatibilityResult(OdbCompatibilityResult result)
    {
        var normalizedStatus = (result.Status ?? string.Empty).Trim().ToLowerInvariant();
        var (statusDisplay, fallbackMessage) = normalizedStatus switch
        {
            "valid" => ("有效", "ODB 可由本机 Abaqus 正常读取。"),
            "upgrade_required" => ("需要升级", "ODB 来自较早版本，需要升级后读取。"),
            "newer_release" => ("版本高于本机", "ODB 由更高版本 Abaqus 创建，本机无法读取。"),
            "invalid" => ("无效", "文件不是有效的 ODB，或 Abaqus 无法读取。"),
            "missing" => ("文件缺失", "检查时未找到该 ODB 文件。"),
            "empty" => ("空文件", "ODB 文件大小为零。"),
            _ => ("未知状态", "控制面返回了 WinUI 尚未识别的兼容性状态。"),
        };
        var message = string.IsNullOrWhiteSpace(result.Message)
            ? fallbackMessage
            : result.Message.Trim();
        SetCompatibility(normalizedStatus, statusDisplay, message, result.StepCount ?? 0);
    }

    public void MarkStructureAnalysisPending()
    {
        PostprocessStatusDisplay = "等待分析";
        PostprocessSummary = "已加入 ODB 结构读取队列";
    }

    public void MarkStructureAnalysisRunning()
    {
        PostprocessStatusDisplay = "正在分析";
        PostprocessSummary = "Abaqus 正在读取分析步、集合与场输出";
    }

    public void ApplyPostprocessScan(OdbPostprocessScanItem scan)
    {
        ScanDetails = scan;
        var draft = _hasEditedPostprocessJob && PostprocessJob is not null
            ? PostprocessJob.Clone() : scan.Suggested.Clone();
        draft.Path = Path;
        PostprocessJob = draft;
        RefreshConfigurationState();
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(PostprocessJob)));
    }

    public void MarkPostprocessIncomplete(string status, string message)
    {
        PostprocessStatusDisplay = status;
        PostprocessSummary = message;
    }

    public void MarkStructureAnalysisIncomplete(string message)
    {
        ScanDetails = null;
        HasPostprocessConfiguration = false;
        MarkPostprocessIncomplete("无结构结果", message);
    }

    public void UpdatePostprocessJob(OdbPostprocessJobDraft draft)
    {
        draft = draft.Clone();
        draft.Path = Path;
        PostprocessJob = draft;
        _hasEditedPostprocessJob = true;
        RefreshConfigurationState();
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(PostprocessJob)));
    }

    private void RefreshConfigurationState()
    {
        HasPostprocessConfiguration = false;
        if (ScanDetails is not { } scan || !string.IsNullOrWhiteSpace(scan.Error))
        {
            PostprocessStatusDisplay = "分析失败";
            PostprocessSummary = ScanDetails?.Error ?? "请先读取 ODB 结构";
            return;
        }
        if (PostprocessJob is not { } draft) return;
        var issues = new List<string>();
        var steps = scan.Steps.ToList();
        var start = steps.IndexOf(draft.StartStep);
        var end = steps.IndexOf(draft.EndStep);
        if (start < 0 || end < start) issues.Add("请选择有效的起止分析步");
        if (draft.LoadDirection is not ("1" or "3" or "1+3")) issues.Add("请选择加载方向");
        if (!scan.AssemblyNodeSets.Contains(draft.LoadSet)) issues.Add("请选择加载节点集");
        foreach (var (name, label) in new[] {
            (draft.PileDisplaySet, "桩体显示集合"), (draft.PileConcreteSet, "混凝土集合"),
            (draft.SoilSet, "土体集合") })
            if (!scan.AssemblyElementSets.Contains(name)) issues.Add($"请重新选择{label}");
        if (draft.ReinforcementMode is not ("required" or "none")) issues.Add("请选择纵筋配置");
        if (draft.ReinforcementMode != "none" && !scan.AssemblyElementSets.Contains(draft.RebarSet))
            issues.Add("请重新选择纵筋集合");
        if (draft.PileSteelSet.Length > 0 && !scan.AssemblyElementSets.Contains(draft.PileSteelSet))
            issues.Add("请重新选择钢构件集合");
        if (draft.FrameMode is not ("auto" or "all" or "manual")
            || (draft.FrameMode == "manual" && string.IsNullOrWhiteSpace(draft.ManualSequenceExpression)))
            issues.Add("请配置提取帧");
        if (draft.PileType is not ("RC" or "CFST")) issues.Add("请选择桩体类型");
        if (draft.ReinforcementMode != "none" && string.IsNullOrWhiteSpace(draft.LongitudinalMaterial)) issues.Add("请填写纵筋材料");
        if (!double.IsFinite(draft.RebarDiameterMm) || draft.RebarDiameterMm < 1 || draft.RebarDiameterMm > 100)
            issues.Add("纵筋直径应为 1–100 mm");
        HasPostprocessConfiguration = issues.Count == 0;
        PostprocessStatusDisplay = HasPostprocessConfiguration ? (_hasEditedPostprocessJob ? "已配置" : "已就绪") : "待配置";
        PostprocessSummary = HasPostprocessConfiguration
            ? $"{draft.StartStep} → {draft.EndStep} · {FrameModeDisplay(draft.FrameMode)} · 方向 {draft.LoadDirection}"
            : string.Join("；", issues);
    }

    public void MarkProcessing(string status, string message)
    {
        PostprocessStatusDisplay = status;
        PostprocessSummary = message;
    }

    private static string FrameModeDisplay(string frameMode) => frameMode switch
    {
        "auto" => "关键帧（自动）",
        "all" => "全部帧",
        "manual" => "手动帧",
        _ => frameMode,
    };

    private void SetCompatibility(
        string status,
        string statusDisplay,
        string message,
        int stepCount)
    {
        CompatibilityStatus = status;
        CompatibilityStatusDisplay = statusDisplay;
        CompatibilityMessage = stepCount > 0
            ? $"{message} · {stepCount} 个分析步"
            : message;
    }

    private void SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return;
        }

        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
