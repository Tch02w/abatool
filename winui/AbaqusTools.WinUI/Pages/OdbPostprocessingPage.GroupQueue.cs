using System.Security.Cryptography;
using System.Text;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private sealed record QueueBookmark(string Root, string RequestId, string? OperationId);
    private sealed record GroupChoice(string Id, string Label)
    {
        public override string ToString() => Label;
    }

    private readonly RecoveryDraftFile<QueueBookmark> _queueFile = new(
        Path.Combine(WorkbenchProfile.Current.StateDirectory, "postprocess-group-queue.json"),
        bookmark =>
        {
            if (!Path.IsPathFullyQualified(bookmark.Root) || !Guid.TryParse(bookmark.RequestId, out _))
                throw new InvalidDataException("分组队列恢复记录无效。");
        });
    private readonly DispatcherTimer _groupQueueTimer = new() { Interval = TimeSpan.FromSeconds(1) };
    private QueueBookmark? _queueBookmark;
    private OdbPostprocessGroupQueueSnapshot? _groupQueue;
    private bool _groupQueueCommandBusy;
    private bool _groupQueueReadBusy;
    private bool _queueUnconfirmed;
    private bool _groupQueueUnavailable;
    private string? _childLogId;
    private long _childLogVersion = -1;

    private bool GroupQueueBlocksOtherOperations => _queueUnconfirmed || _groupQueueCommandBusy
        || _groupQueue is { IsTerminal: false };

    private static bool AcceptsPendingChanges(OdbPostprocessGroupQueueSnapshot? queue) =>
        queue?.Status is "queued" or "running";

    private IEnumerable<OdbPostprocessGroupQueueItem> UnfinishedGroups =>
        _groupQueue?.Groups.Where(item => item.Status is "queued" or "running" or "cancelling" or "interrupted")
            ?? Enumerable.Empty<OdbPostprocessGroupQueueItem>();

    private bool CanRemoveGroupMembership(OdbPostprocessGroupQueueItem? entry)
    {
        if (_queueUnconfirmed)
        {
            ShowWarning("请先刷新队列状态并核对正在使用的分组。", "分组状态待确认");
            return false;
        }
        if (entry is null) return true;
        ShowWarning(entry.Status == "queued"
            ? $"请先在“编辑等待组”中取消要移除的成员。取消全部成员并保存即可跳过“{entry.Name}”。"
            : $"“{entry.Name}”的执行尚未结束。请先核对队列状态，再调整成员。",
            "此分组仍在提取队列中");
        return false;
    }

    private static string StableGroupDraftId(string root, OdbExecutionGroup group)
    {
        var identity = group.Standalone ? "odb|" + PathKey(group.Members[0].Path) : "group|" + group.Name.Trim();
        var bytes = Encoding.UTF8.GetBytes((PathKey(root) + "|" + identity).ToUpperInvariant());
        return "g-" + Convert.ToHexString(SHA256.HashData(bytes))[..32].ToLowerInvariant();
    }

    private async Task SubmitGroupQueueAsync(OdbPostprocessRunCreateRequest run)
    {
        if (_groupQueueCommandBusy || _queueUnconfirmed || _groupQueueUnavailable) return;
        if (_groupQueue is { IsTerminal: false } existing)
        {
            if (!AcceptsPendingChanges(existing)) return;
            await ChangeGroupQueueAsync(existing, PostprocessGroupQueueAction.Append, run);
            return;
        }
        _groupQueueCommandBusy = true;
        var submitted = false;
        var previous = _queueBookmark;
        RefreshInteractionState();
        try
        {
            var bookmark = new QueueBookmark(run.Root, run.ClientRequestId, null);
            await _queueFile.SaveAsync(bookmark);
            _queueBookmark = bookmark;
            submitted = true;
            var initial = await App.Current.ControlPlane.StartPostprocessGroupQueueAsync(run);
            _groupQueue = null;
            _childLogId = null;
            PostprocessLogTextBox.Text = "";
            await AttachGroupQueueAsync(initial);
            ForceRescanCheckBox.IsChecked = false;
        }
        catch (Exception error)
        {
            if (submitted && (error is ControlPlaneException { StatusCode: >= 400 and < 500 and not 408 }
                || !new OdbPostprocessRecoveryState().RequiresVerification(error)))
            {
                _queueBookmark = previous;
                try { await _queueFile.SaveAsync(previous); }
                catch (IOException saveError) { _queueUnconfirmed = true; ShowWarning(saveError.Message, "恢复记录未能保存"); }
            }
            else if (submitted) _queueUnconfirmed = true;
            ShowWarning(QueueError(error), _queueUnconfirmed ? "分组队列是否受理待确认，请刷新队列状态" : "未能创建分组队列");
        }
        finally { _groupQueueCommandBusy = false; RefreshInteractionState(); }
    }

    private async Task AttachGroupQueueAsync(OdbPostprocessGroupQueueSnapshot snapshot)
    {
        if (_queueBookmark is { } expected && (expected.RequestId != snapshot.ClientRequestId
            || !PathKey(expected.Root).Equals(PathKey(snapshot.Root), StringComparison.OrdinalIgnoreCase)))
            throw new InvalidDataException("返回的提取队列与保存的请求不一致。");
        _queueBookmark = new(snapshot.Root, snapshot.ClientRequestId, snapshot.OperationId);
        ApplyGroupQueue(snapshot);
        await _queueFile.SaveAsync(_queueBookmark);
        StartGroupQueuePolling();
    }

    private async Task<bool> RestoreGroupQueueAsync()
    {
        try
        {
            _queueBookmark = _queueFile.Load();
            var queue = await FindGroupQueueAsync();
            _groupQueueUnavailable = false;
            if (queue is null)
            {
                if (_queueBookmark is not null) throw new InvalidDataException("尚未找到原队列，请用“刷新队列状态”重新查询。");
                return false;
            }
            if (queue.IsActive || queue.CanResume)
            {
                RootTextBox.Text = queue.Root;
                if (!string.Equals(_lastDiscoveryRoot, queue.Root, StringComparison.OrdinalIgnoreCase))
                    await DiscoverCoreAsync(queue.Root);
            }
            await AttachGroupQueueAsync(queue);
            return !queue.IsTerminal;
        }
        catch (ControlPlaneException error) when (error.StatusCode == 404 && _queueBookmark is null)
        {
            _groupQueueUnavailable = true;
            ShowWarning("当前后台未提供分组队列。等待现有任务结束后重新启动新版后台，即可使用分组提取。", "分组队列暂不可用");
            RefreshInteractionState();
            return false;
        }
        catch (Exception error)
        {
            _queueUnconfirmed = true;
            ShowWarning(QueueError(error), "分组队列状态待确认");
            RefreshInteractionState();
            return false;
        }
    }

    private async Task<OdbPostprocessGroupQueueSnapshot?> FindGroupQueueAsync()
    {
        var host = App.Current.ControlPlane;
        if (_queueBookmark?.OperationId is { Length: > 0 } id) return await host.GetPostprocessGroupQueueAsync(id);
        var queues = (await host.ListPostprocessGroupQueuesAsync()).Operations;
        if (_queueBookmark is { } saved)
            return queues.FirstOrDefault(queue => queue.ClientRequestId == saved.RequestId
                && PathKey(queue.Root).Equals(PathKey(saved.Root), StringComparison.OrdinalIgnoreCase));
        // Without a bookmark, only reconnect to an unfinished queue in the displayed workspace.
        if (!Path.IsPathFullyQualified(RootTextBox.Text)) return null;
        return queues.SingleOrDefault(queue => !queue.IsTerminal
            && PathKey(queue.Root).Equals(PathKey(RootTextBox.Text), StringComparison.OrdinalIgnoreCase));
    }

    private void StartGroupQueuePolling()
    {
        if (IsLoaded && _groupQueue is { IsActive: true } && !_queueUnconfirmed) _groupQueueTimer.Start();
    }

    private async void OnGroupQueueTick(object? sender, object args) => await ReadGroupQueueAsync(false);
    private async void OnQueryGroupQueueClicked(object sender, RoutedEventArgs e) => await ReadGroupQueueAsync(true);

    private async Task ReadGroupQueueAsync(bool explicitRead)
    {
        if (_groupQueueReadBusy || _groupQueueCommandBusy) return;
        _groupQueueReadBusy = true;
        var expectedRequest = _queueBookmark?.RequestId;
        try
        {
            var known = _groupQueue;
            var queue = !explicitRead && !_queueUnconfirmed && known is not null && known.OperationId == _queueBookmark?.OperationId
                ? await App.Current.ControlPlane.GetPostprocessGroupQueueIfChangedAsync(known.OperationId, known.Version) ?? known
                : await FindGroupQueueAsync();
            if (_queueBookmark?.RequestId != expectedRequest || _groupQueueCommandBusy) return;
            if (queue is null)
            {
                if (_queueBookmark is null && _queueUnconfirmed) { _queueUnconfirmed = false; RefreshInteractionState(); }
                if (explicitRead) ShowWarning("当前工作区未找到相应的分组队列。", "已查询分组队列");
                return;
            }
            if (_queueBookmark?.OperationId != queue.OperationId) await AttachGroupQueueAsync(queue);
            else ApplyGroupQueue(queue);
            StartGroupQueuePolling();
            var group = queue.Groups.FirstOrDefault(item => item.GroupId == queue.CurrentGroupId)
                ?? queue.Groups.LastOrDefault(item => !string.IsNullOrEmpty(item.ChildOperationId));
            if (group?.ChildOperationId is { Length: > 0 } childId && !_postprocessBusy)
            {
                var child = await App.Current.ControlPlane.GetOdbPostprocessOperationAsync(childId);
                if (_groupQueue?.OperationId != queue.OperationId || _groupQueue.Version != queue.Version || _postprocessBusy) return;
                if (_childLogId != childId || child.Version != _childLogVersion)
                {
                    _childLogId = childId;
                    _childLogVersion = child.Version;
                    var log = string.Join(Environment.NewLine, child.Logs);
                    if (PostprocessLogTextBox.Text != log) PostprocessLogTextBox.Text = log;
                    if (queue.IsActive && group.GroupId == queue.CurrentGroupId)
                    {
                        var percent = Math.Clamp(child.Progress.Percent, 0, 100);
                        PostprocessProgress.Value = percent;
                        PostprocessPercentText.Text = $"{percent}%";
                        PostprocessPhaseText.Text = $"{group.Name} · {child.Progress.Phase}";
                    }
                }
            }
        }
        catch (Exception error)
        {
            if (_queueBookmark?.RequestId != expectedRequest || _groupQueueCommandBusy) return;
            _groupQueueTimer.Stop();
            _queueUnconfirmed = true;
            ShowWarning(QueueError(error), "分组队列状态待确认，请刷新队列状态");
            RefreshInteractionState();
        }
        finally { _groupQueueReadBusy = false; }
    }

    private void ApplyGroupQueue(OdbPostprocessGroupQueueSnapshot queue)
    {
        if (_queueBookmark?.OperationId != queue.OperationId || (_groupQueue?.OperationId == queue.OperationId
            && _groupQueue.Version > queue.Version)) return;
        var wasUnconfirmed = _queueUnconfirmed;
        _queueUnconfirmed = false;
        var changed = _groupQueue?.OperationId != queue.OperationId || _groupQueue.Version != queue.Version;
        _groupQueue = queue;
        if (!queue.IsActive) _groupQueueTimer.Stop();
        if (!changed)
        {
            if (wasUnconfirmed) RefreshInteractionState();
            return;
        }
        if (PathKey(RootTextBox.Text).Equals(PathKey(queue.Root), StringComparison.OrdinalIgnoreCase))
            _resultLocations.SetGroupQueueResult(queue.OperationId, queue.Root, queue.Result);
        var chosen = (GroupQueueEntries.SelectedItem as GroupChoice)?.Id;
        var choices = queue.Groups.Select((item, index) => new GroupChoice(item.GroupId,
            $"{index + 1}. {item.Name} · {QueueStatus(item.Status)}")).ToArray();
        GroupQueueEntries.ItemsSource = choices;
        GroupQueueEntries.SelectedItem = choices.FirstOrDefault(item => item.Id == chosen)
            ?? choices.FirstOrDefault(item => item.Id == queue.CurrentGroupId) ?? choices.FirstOrDefault();
        var waiting = queue.Groups.Count(item => item.Status == "queued");
        GroupQueueSummary.Text = $"{QueueStatus(queue.Status)} · 等待 {waiting} 组 · 已发布 {queue.Result.OutputCount} 个结果目录";
        if (!_postprocessBusy)
        {
            var current = queue.Groups.FirstOrDefault(item => item.GroupId == queue.CurrentGroupId);
            if (current is null || !queue.IsActive)
            {
                PostprocessPhaseText.Text = QueueStatus(queue.Status);
                PostprocessProgress.Value = queue.Status == "succeeded" ? 100 : 0;
                PostprocessPercentText.Text = queue.Status == "succeeded" ? "100%" : "";
            }
            else if (string.IsNullOrEmpty(current.ChildOperationId) || current.ChildOperationId != _childLogId)
            {
                PostprocessPhaseText.Text = $"{current.Name} · {QueueStatus(current.Status)}";
                PostprocessProgress.Value = 0;
                PostprocessPercentText.Text = "";
            }
        }
        RefreshInteractionState();
    }

    private OdbPostprocessGroupQueueItem? SelectedQueueGroup => _groupQueue?.Groups.FirstOrDefault(
        item => item.GroupId == (GroupQueueEntries.SelectedItem as GroupChoice)?.Id);

    private void OnGroupQueueSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (GroupQueueDetail is null) return;
        GroupQueueDetail.Text = SelectedQueueGroup is { } item ? $"{item.Members.Count} 个 ODB · {item.Message}" : "";
        RefreshInteractionState();
    }

    private void UpdateGroupQueueControls()
    {
        var queue = _groupQueue;
        // Pending workspace drafts gate local edits. Frozen queue entries can still be managed.
        var canControl = !_groupQueueCommandBusy && !_queueUnconfirmed && !_draftActionBusy
            && !_postprocessBusy && !_compatibilityBusy && !_discoveryBusy && !_upgradeBusy;
        GroupQueuePanel.Visibility = queue is not null || _queueUnconfirmed ? Visibility.Visible : Visibility.Collapsed;
        GroupQueueEditHint.Visibility = queue is { IsTerminal: false } ? Visibility.Visible : Visibility.Collapsed;
        RunPostprocessButton.Content = queue is { IsTerminal: false } ? "追加所选组" : "运行后处理";
        var canChangePending = canControl && AcceptsPendingChanges(queue);
        RunPostprocessButton.IsEnabled &= !_queueUnconfirmed && !_groupQueueUnavailable && (queue is null || queue.IsTerminal || canChangePending);
        CancelPostprocessButton.Content = queue?.IsActive == true && !_postprocessBusy ? "取消当前组" : "停止当前操作";
        if (queue?.IsActive == true && !_postprocessBusy)
            CancelPostprocessButton.IsEnabled = canChangePending
                && queue.Groups.Any(item => item.GroupId == queue.CurrentGroupId && item.Status == "running");
        EditQueuedGroupButton.IsEnabled = canChangePending && SelectedQueueGroup is { Status: "queued", Run: not null };
        ClearQueuedGroupsButton.IsEnabled = canChangePending && queue!.Groups.Any(item => item.Status == "queued");
        QueryGroupQueueButton.IsEnabled = !_groupQueueCommandBusy;
        ResumeGroupQueueButton.Visibility = queue?.CanResume == true ? Visibility.Visible : Visibility.Collapsed;
        ResumeGroupQueueButton.IsEnabled = canControl;
        ResumeGroupQueueButton.Content = queue?.CanResume == true && !string.IsNullOrWhiteSpace(queue.CurrentGroupId)
            ? "核对中断组…" : "继续等待组";
        StopGroupQueueButton.Visibility = queue is { IsTerminal: false } ? Visibility.Visible : Visibility.Collapsed;
        StopGroupQueueButton.IsEnabled = canControl && (AcceptsPendingChanges(queue)
            || queue is { CanResume: true } && string.IsNullOrEmpty(queue.CurrentGroupId));
    }

    private async Task<bool> ChangeGroupQueueAsync(OdbPostprocessGroupQueueSnapshot queue,
        PostprocessGroupQueueAction action, OdbPostprocessRunCreateRequest? run = null, string? groupId = null)
    {
        if (_queueUnconfirmed || _groupQueueCommandBusy || _groupQueue?.OperationId != queue.OperationId) return false;
        _groupQueueCommandBusy = true;
        RefreshInteractionState();
        try
        {
            var updated = await App.Current.ControlPlane.ChangePostprocessGroupQueueAsync(
                queue.OperationId, action, Guid.NewGuid(), queue.Version, run, groupId);
            ApplyGroupQueue(updated);
            StartGroupQueuePolling();
            return true;
        }
        catch (Exception error)
        {
            try { ApplyGroupQueue(await App.Current.ControlPlane.GetPostprocessGroupQueueAsync(queue.OperationId)); }
            catch { _queueUnconfirmed = true; _groupQueueTimer.Stop(); }
            ShowWarning(QueueError(error), "请核对最新分组队列状态");
            return false;
        }
        finally { _groupQueueCommandBusy = false; RefreshInteractionState(); }
    }

    private async void OnClearQueuedGroupsClicked(object sender, RoutedEventArgs e)
    {
        if (_groupQueue is not { } queue || !AcceptsPendingChanges(queue)) return;
        var names = queue.Groups.Where(item => item.Status == "queued").Select(item => item.Name).ToArray();
        if (names.Length == 0) return;
        var dialog = new ContentDialog { XamlRoot = XamlRoot, Title = $"清空 {names.Length} 个等待组？",
            Content = string.Join("、", names), PrimaryButtonText = "清空待办", CloseButtonText = "返回" };
        if (await dialog.ShowAsync() == ContentDialogResult.Primary)
            await ChangeGroupQueueAsync(queue, PostprocessGroupQueueAction.ClearPending);
    }

    private async void OnResumeGroupQueueClicked(object sender, RoutedEventArgs e)
    {
        if (_groupQueue is not { CanResume: true } queue) return;
        if (string.IsNullOrEmpty(queue.CurrentGroupId))
            await ChangeGroupQueueAsync(queue, PostprocessGroupQueueAction.Resume);
        else
        {
            var name = queue.Groups.First(item => item.GroupId == queue.CurrentGroupId).Name;
            var confirm = new ContentDialog { XamlRoot = XamlRoot, Title = $"核对中断组 · {name}",
                Content = "请先在运行主机上核对该组原 Abaqus 后处理进程已经退出，并检查已有输出。确认后其余组仍保持暂停。",
                PrimaryButtonText = "已核实原进程退出", CloseButtonText = "返回" };
            if (await confirm.ShowAsync() == ContentDialogResult.Primary)
                await ChangeGroupQueueAsync(queue, PostprocessGroupQueueAction.AcknowledgeInterrupted, groupId: queue.CurrentGroupId);
        }
    }

    private async void OnStopGroupQueueClicked(object sender, RoutedEventArgs e)
    {
        if (_groupQueue is not { IsTerminal: false } queue) return;
        var confirm = new ContentDialog { XamlRoot = XamlRoot, Title = "停止整个提取队列？",
            Content = "取消仍在执行的组并清除待办。已发布的结果可以继续浏览。",
            PrimaryButtonText = "停止队列", CloseButtonText = "返回" };
        if (await confirm.ShowAsync() == ContentDialogResult.Primary)
            await ChangeGroupQueueAsync(queue, PostprocessGroupQueueAction.Stop);
    }

    private static string QueueError(Exception error) => error is ControlPlaneException api ? api.ToDisplayMessage() : error.Message;
    private static string QueueStatus(string state) => state switch {
        "queued" => "等待中", "running" => "运行中", "cancelling" => "正在取消", "suspended" => "已暂停，等待确认",
        "succeeded" => "已完成", "partial" => "部分完成", "failed" => "失败", "cancelled" => "已取消", "skipped" => "已跳过",
        "interrupted" => "已中断，需核对原执行", _ => state };
}
