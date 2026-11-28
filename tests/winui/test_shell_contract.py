from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def test_inline_numeric_inputs_preserve_hardware_limits_and_decimal_tolerance():
    import xml.etree.ElementTree as ET
    root = Path(__file__).resolve().parents[2] / "winui" / "AbaqusTools.WinUI"
    page = ET.parse(root / "Pages" / "OdbPostprocessingPage.xaml")
    name = '{http://schemas.microsoft.com/winfx/2006/xaml}Name'
    controls = {node.get(name): node for node in page.iter() if node.get(name)}
    for field in ('ParallelWorkers', 'ExpectedRebarCount', 'AnimationFps', 'ImageWidth', 'ImageHeight', 'RebarTolerance'):
        assert controls[field + 'NumberBox'].tag.endswith('}WorkbenchNumberBox')
        assert controls[field + 'NumberBox'].get('SpinButtonPlacementMode') == 'Inline'
    assert controls['ParallelWorkersNumberBox'].get('Maximum') != '4'
    code = (root / 'Pages' / 'OdbPostprocessingPage.xaml.cs').read_text(encoding='utf-8')
    assert 'ParallelWorkersNumberBox.Maximum = resource.LogicalCpus' in code
    assert 'new Controls.PlainDecimalFormatter()' in code
    job_code = (root / 'Pages' / 'NewJobPage.xaml.cs').read_text(encoding='utf-8')
    assert 'resource.JobCpuLimit' in job_code
    assert 'abaqusCommand: AbaqusCommandTextBox.Text.Trim()' in job_code

ROOT = Path(__file__).resolve().parents[2]
WINUI_ROOT = ROOT / "winui" / "AbaqusTools.WinUI"
XAML_NAMESPACE = {"xaml": "http://schemas.microsoft.com/winfx/2006/xaml/presentation"}
XAML_NAME = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
XAML_KEY = "{http://schemas.microsoft.com/winfx/2006/xaml}Key"


def test_result_browser_menu_and_ctrl8_share_the_postprocessing_result_command() -> None:
    shell_xaml = ET.parse(WINUI_ROOT / "MainWindow.xaml")
    menu = shell_xaml.find(".//xaml:MenuFlyoutItem[@Text='打开结果浏览']", XAML_NAMESPACE)
    shortcut = shell_xaml.find(".//xaml:KeyboardAccelerator[@Key='Number8']", XAML_NAMESPACE)
    assert menu is not None and shortcut is not None and shortcut.get("Modifiers") == "Control"
    shell = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    for name in (menu.attrib["Click"], shortcut.attrib["Invoked"]):
        handler = shell.split(f"void {name}(", 1)[1].split("\n    }", 1)[0]
        assert "await OpenResultsFromCurrentPageAsync()" in handler
    command = shell.split("private Task OpenResultsFromCurrentPageAsync()", 1)[1].split("\n    }", 1)[0]
    assert "ContentFrame.Content is OdbPostprocessingPage" in command
    assert "return postprocessing.OpenResultsAsync()" in command
    assert 'SelectRoute("result-browser")' in command
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(encoding="utf-8")
    button = page.split("void OnOpenResultsClicked(", 1)[1].split("\n    }", 1)[0]
    assert "await OpenResultsAsync()" in button


def test_postprocess_group_queue_poll_preserves_controls_and_updates_both_progress_indicators() -> None:
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.GroupQueue.cs").read_text(encoding="utf-8")
    poll = page.split("private async Task ReadGroupQueueAsync(", 1)[1].split("private void ApplyGroupQueue(", 1)[0]
    assert "GetPostprocessGroupQueueIfChangedAsync(known.OperationId, known.Version) ?? known" in poll
    assert "GetOdbPostprocessOperationAsync(childId)" in poll
    assert "PostprocessProgress.Value = percent" in poll
    assert 'PostprocessPercentText.Text = $"{percent}%"' in poll
    assert "QueryGroupQueueButton.IsEnabled = !_groupQueueCommandBusy;" in page
    assert "finally { _groupQueueReadBusy = false; }" in poll


def test_postprocess_group_queue_rejects_pending_mutations_while_suspended() -> None:
    queue = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.GroupQueue.cs").read_text(encoding="utf-8")
    editor = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.GroupEditor.cs").read_text(encoding="utf-8")
    assert 'queue?.Status is "queued" or "running"' in queue
    assert "EditQueuedGroupButton.IsEnabled = canChangePending" in queue
    assert "ClearQueuedGroupsButton.IsEnabled = canChangePending" in queue
    assert "!AcceptsPendingChanges(existing)" in queue
    assert "!AcceptsPendingChanges(queue)" in editor
    assert "error.StatusCode == 404 && _queueBookmark is null" in queue


def test_postprocess_legend_errors_keep_the_dialog_and_draft() -> None:
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(encoding="utf-8")
    editor = page.split("private async void OnLegendClicked", 1)[1].split("private async void OnManageGroupsClicked", 1)[0]
    handler, after = editor.split("dialog.PrimaryButtonClick +=", 1)[1].split("await ShowRecoverableDialogAsync(", 1)
    assert "maximum <= minimum" in handler and "args.Cancel = true" in handler
    assert "input.Focus(FocusState.Programmatic)" in handler and "SaveWorkspace()" not in handler
    assert "_legendOverridesByGroup[groupName] = values" in after


def test_postprocess_invalid_editor_input_keeps_dialog_open() -> None:
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(encoding="utf-8")
    editor = page.split("private async Task<OdbPostprocessJobDraft?> ShowJobConfigurationDialogAsync", 1)[1]
    handler = editor.split("dialog.PrimaryButtonClick +=", 1)[1].split("var inputControls =", 1)[0]
    assert "string.IsNullOrWhiteSpace(manualFrames.Text)" in handler
    assert "diameter.ParseEditingValue(diameter.EditingText)" in handler
    assert "prefracture.ParseEditingValue(prefracture.EditingText)" in handler
    assert "Math.Truncate(frameIndex.Value)" in handler
    assert "args.Cancel = error.Length > 0" in handler
    assert "validationMessage.Text = error" in handler


def _named_element(root: ET.Element, name: str) -> ET.Element:
    return next(element for element in root.iter() if element.attrib.get(XAML_NAME) == name)


def test_direct_result_toolbar_can_build_the_same_index_as_the_filtered_view():
    page = ET.parse(WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml").getroot()
    direct = _named_element(page, "DirectToolbar")
    assert _named_element(direct, "DirectRefreshButton").get("Click") == "OnDirectRefreshClicked"
    for panel, name in ((direct, "DirectBuildIndexButton"), (page, "BuildIndexButton")):
        assert _named_element(panel, name).get("Click") == "OnBuildIndexClicked"


def test_result_sort_headers_match_record_columns_and_offer_secondary_orders():
    page = ET.parse(WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml").getroot()
    headers = _named_element(page, "SortHeaders")
    record_list = _named_element(page, "ResultList")
    def columns(panel: ET.Element):
        return [col.attrib["Width"] for col in panel.findall(".//{*}ColumnDefinition")]

    assert columns(headers) == columns(record_list)
    buttons = sorted(headers.findall("{*}Button"), key=lambda button: int(button.get("Grid.Column", 0)))
    assert [button.get("Tag") for button in buttons] == ["recommended", "useCase", "name", "size", "modified"]
    menu = [_named_element(page, name) for name in ("SortPathMenuItem", "SortDescriptionMenuItem", "ResetSortMenuItem")]
    assert [item.get("Tag") for item in menu] == ["path", "description", "default"]
    assert all(control.get("Click") == "OnSortClicked" for control in buttons + menu)


def test_cached_result_page_reattaches_its_snapshot_and_reports_status_only_while_visible():
    window = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    page = (WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml.cs").read_text(encoding="utf-8")
    assert "refreshOnAttach: ContentFrame.Content is not ResultBrowserPage { HasLoadedDirectory: true }" in window
    assert "HasLoadedDirectory => _location.LoadedRoot is not null" in page
    assert "ReportPageStatus(page.StatusBarMessage)" in window
    assert page.count("App.Current.MainWindow.ReportPageStatus(") == 1
    assert "if (ReferenceEquals(Frame?.Content, this)) App.Current.MainWindow.ReportPageStatus(message)" in page


def test_result_export_and_recycle_register_the_entire_operation_before_dialogs():
    page = (WINUI_ROOT / "Pages" / "ResultBrowserPage.Export.cs").read_text(encoding="utf-8")
    assert page.index("PendingResultFileOperation = completion.Task") < page.index("PickSingleFolderAsync")
    assert "!App.Current.PendingResultFileOperation.IsCompleted" in page
    assert "App.Current.Session.IsClosing" in page
    assert "completion.TrySetResult()" in page and "ResultFileExport.CopyAsync" in page
    assert "ReferenceEquals(_exportCancellation, cancellation)" in page
    shell = ET.parse(WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml").getroot()
    assert _named_element(shell, "CancelExportButton").attrib["Click"] == "OnCancelExportClicked"
    assert _named_element(shell, "ExportDetailsText").attrib["IsReadOnly"] == "True"
    original = (WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml.cs").read_text(encoding="utf-8")
    recycle = original.split("private async void OnRecycleClicked", 1)[1].split("private async Task RecycleSelectedAsync", 1)[0]
    assert recycle.index("PendingResultFileOperation = completion.Task") < recycle.index("confirm.ShowAsync")
    assert "FileOperationBusy" in recycle and "App.Current.Session.IsClosing" in recycle


def test_result_file_actions_use_loaded_directory_and_keep_pending_root_visible():
    page = (WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml.cs").read_text(encoding="utf-8")
    export = (WINUI_ROOT / "Pages" / "ResultBrowserPage.Export.cs").read_text(encoding="utf-8")
    assert "var root = RootTextBox.Text" not in page + export
    assert "var root = _location.LoadedRoot;" in export
    assert "_appliedQuery?.Root ?? _location.RequireLoadedRoot()" in page
    assert "Root = _location.RequireLoadedRoot()" in page
    assert "RefreshScopesAsync(snapshot.Request.TimeDirectory, snapshot.Request.Root)" in page
    assert "RefreshScopesAsync(_selectedScope?.Path, _location.LoadedRoot)" in page
    shell = ET.parse(WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml").getroot()
    assert _named_element(shell, "RootTextBox").get("TextChanged") == "OnRootTextChanged"
    assert _named_element(shell, "RootContextHint").get("Visibility") == "Collapsed"


def test_current_job_route_is_distinct_and_does_not_replace_pending_workspace():
    shell = ET.parse(WINUI_ROOT / "MainWindow.xaml").getroot()
    assert _named_element(shell, "CurrentJobPostprocessingMenuItem").attrib["Click"] == "OnCurrentJobPostprocessingMenuClicked"
    route = (WINUI_ROOT / "MainWindow.Postprocessing.cs").read_text(encoding="utf-8")
    assert "JobPostprocessRoute.ResolveAsync" in route
    assert "target != CaptureCurrentJobTarget()" in route
    assert "ReferenceEquals(origin, ContentFrame.Content)" in route
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(encoding="utf-8")
    loader = page.split("public async Task<bool> LoadOdbPathAsync", 1)[1].split("private async void OnPageLoaded", 1)[0]
    assert "await _initialLoadTask" in loader
    assert "DraftPending" in loader and "_compatibilityBusy" in loader
    assert "RootTextBox.Text =" not in loader
    assert "if (!await DiscoverCoreAsync(directory, canApply)) return false" in loader
    assert "未能定位作业 ODB" in loader
    discovery = page.split("private async Task<bool> DiscoverCoreAsync", 1)[1].split("private void UpdateExplorer", 1)[0]
    before_apply = discovery.split("DiscoverOdbsAsync", 1)[1].split("OdbList.SelectedItems.Clear()", 1)[0]
    assert "canApply?.Invoke() is false" in before_apply


def test_native_upgrade_entry_confirmation_and_recovery_wiring() -> None:
    root = ET.parse(WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml").getroot()
    for name, handler in [
        ("UpgradeButton", "OnUpgradeClicked"),
        ("RecoverUpgradeButton", "OnRecoverUpgradeClicked"),
        ("CancelUpgradeButton", "OnCancelUpgradeClicked"),
    ]:
        assert _named_element(root, name).attrib["Click"] == handler
    assert _named_element(root, "UpgradeDetailsTextBox").attrib["IsReadOnly"] == "True"
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.Upgrade.cs").read_text(encoding="utf-8")
    shell = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(encoding="utf-8")
    assert "DefaultButton = ContentDialogButton.Close" in page
    assert "if (!await ConfirmUpgradeAsync(preview)) return;" in page
    assert page.count("_pendingUpgradeRequestId = Guid.NewGuid()") == 1
    assert "if (snapshot is null && _pendingUpgradePreview is not null && showHistory)" in page
    assert "MarkStructureAnalysisIncomplete" in page
    assert "UpgradeBlocksEditing" in shell
    assert "RecoverUpgradeAsync(showHistory: false)" in shell
    assert 'ChooseUpgradeHistoryAsync(list.Operations)' in page
    assert 'item.Error?.Code == "UPGRADE_INTERRUPTED"' in page
    assert 'return showHistory || wasActive;' in page
    assert 'ListOdbUpgradeOperationsAsync(activeOnly: true)' in page
    assert 'snapshot.PersistenceWarning' in page
    assert 'selectedRows.All(row => row.CompatibilityStatus == "upgrade_required")' in shell


def test_native_shell_keeps_the_eight_page_information_architecture() -> None:
    root = ET.parse(WINUI_ROOT / "MainWindow.xaml").getroot()
    items = root.findall(
        ".//xaml:NavigationView.MenuItems/xaml:NavigationViewItem",
        XAML_NAMESPACE,
    )

    assert [item.attrib["Content"] for item in items] == [
        "新建作业",
        "作业队列",
        "作业概览",
        "计算资源",
        "重启动链",
        "ODB 合并",
        "ODB 后处理",
        "结果浏览",
    ]
    assert [item.attrib["Tag"] for item in items] == [
        "new-job",
        "job-queue",
        "job-overview",
        "compute-resources",
        "restart-chain",
        "odb-merge",
        "odb-postprocessing",
        "result-browser",
    ]


def test_native_shell_exposes_the_four_menu_groups_and_honest_statuses() -> None:
    root = ET.parse(WINUI_ROOT / "MainWindow.xaml").getroot()
    menu_items = root.findall(".//xaml:MenuBarItem", XAML_NAMESPACE)
    text = (WINUI_ROOT / "MainWindow.xaml").read_text(encoding="utf-8")

    assert [item.attrib["Title"] for item in menu_items] == [
        "文件(F)",
        "作业(J)",
        "服务器(S)",
        "后处理(P)",
    ]
    assert [item.get("AccessKey") for item in menu_items] == ["F", "J", "S", "P"]
    assert "队列 0 · 运行 0 · 等待 0" in text
    assert "远端 ○ 未连接" in text
    assert "Abaqus ○ 待检测" in text
    assert "迁移中" not in text
    assert ".NET 10 · WinUI 3" in text
    assert "ScrollLeftButton" not in text
    assert "ScrollRightButton" not in text


def test_native_bootstrap_and_http_client_preserve_safety_contracts() -> None:
    app_xaml = (WINUI_ROOT / "App.xaml").read_text(encoding="utf-8")
    program = (WINUI_ROOT / "Program.cs").read_text(encoding="utf-8")
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )

    assert program.index("ComWrappersSupport.InitializeComWrappers()") < program.index(
        "AppInstance.GetCurrent()"
    )
    assert "FindOrRegisterForKey" in program
    assert '<XamlControlsResources xmlns="using:Microsoft.UI.Xaml.Controls" />' in app_xaml
    assert "DISABLE_XAML_GENERATED_MAIN" in (
        WINUI_ROOT / "AbaqusTools.WinUI.csproj"
    ).read_text(encoding="utf-8")
    assert "SerializeToUtf8Bytes" in host
    assert "ByteArrayContent" in host
    assert "JsonContent.Create" not in host
    assert '"127.0.0.1"' in host
    assert "control-plane.launch.lock" in host


def test_control_plane_launch_uses_a_nonce_instead_of_redirector_pid() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    contracts = (WINUI_ROOT / "Services" / "ControlPlaneContracts.cs").read_text(
        encoding="utf-8"
    )

    assert 'startInfo.Environment["ABAQUS_TOOLS_LAUNCH_TOKEN"]' in host
    assert "candidate.LaunchToken" in host
    assert "_ownedLaunchToken" in host
    assert "candidate.Pid == ownedProcess.Id" not in host
    assert '[JsonPropertyName("launchToken")]' in contracts


def test_odb_page_can_reattach_to_an_active_compatibility_operation() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(
        encoding="utf-8"
    )

    assert "ListOperationsAsync" in host
    assert '"/api/v1/operations?activeOnly=true"' in host
    assert "Loaded += OnPageLoaded" in page
    assert "RecoverActiveCompatibilityOperationAsync" in page
    assert "RestoreRowsFromOperationRequest" in page


def test_result_browser_is_native_and_uses_async_index_contracts() -> None:
    window = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    page = (WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml.cs").read_text(
        encoding="utf-8"
    )

    assert "typeof(ResultBrowserPage)" in window
    assert '"/api/v1/result-scopes"' in host
    assert '"/api/v1/result-records"' in host
    assert '"/api/v1/result-previews"' in host
    assert '"/api/v1/result-index-builds"' in host
    assert "PollResultIndexUntilTerminalAsync" in page
    assert "CancelResultIndexOperationAsync" in page


def test_restored_index_uses_same_progress_indicator_as_new_index() -> None:
    page = (WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml.cs").read_text(encoding="utf-8")
    refresh = page.split("private void RefreshInteractionState()", 1)[1].split("\n    }", 1)[0]
    assert "IndexProgressBar.Visibility = _indexBusy ? Visibility.Visible : Visibility.Collapsed;" in refresh
    assert "IndexProgressBar.IsIndeterminate = _activeIndexBatchId is null;" in refresh
    assert page.count("IndexProgressBar.Visibility =") == 1
    recovery = page.split("private async Task<bool> RecoverActiveIndexOperationAsync()", 1)[1]
    single = recovery.split("_activeIndexOperationId = snapshot.OperationId;", 1)[1]
    assert single.index("RefreshInteractionState();") < single.index("PollResultIndexUntilTerminalAsync(")


def test_odb_page_routes_its_result_directory_into_the_native_browser() -> None:
    window = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    odb_page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(
        encoding="utf-8"
    )
    result_page = (WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml.cs").read_text(
        encoding="utf-8"
    )

    assert "OpenResultBrowserAsync" in window
    assert "_resultLocations.Resolve(RootTextBox.Text, _lastDiscoveryRoot," in odb_page
    assert "_resultLocations.Complete(snapshot)" in odb_page
    discovery = odb_page.split("private async Task<bool> DiscoverCoreAsync", 1)[1].split("catch (ControlPlaneException", 1)[0]
    accepted = discovery.split("_lastDiscoveryRoot = result.Root;", 1)[1]
    assert "_resultLocations.DiscoveryAccepted(result.Root);" in accepted
    assert odb_page.count("_resultLocations.DiscoveryAccepted(") == 1
    assert "OpenResultBrowserAsync(resultRoot)" in odb_page
    routed_read = result_page.split("public Task SetResultRootAsync", 1)[1].split("private async Task<bool>", 1)[0]
    assert "_loads.OpenRootAsync(" in routed_read and "RefreshScopesAsync(explicitRoot: target)" in routed_read
    assert "if (IsLoaded)" not in routed_read
    assert "Directory.CreateDirectory" not in odb_page


def test_submitter_routes_use_real_native_pages_instead_of_placeholders() -> None:
    window = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")

    expected_pages = {
        "new-job": "NewJobPage",
        "job-queue": "JobQueuePage",
        "job-overview": "JobOverviewPage",
        "compute-resources": "ComputeResourcesPage",
        "restart-chain": "RestartChainPage",
        "odb-merge": "OdbMergePage",
    }
    for route, page_type in expected_pages.items():
        assert f'["{route}"]' in window
        assert f"typeof({page_type})" in window
        assert (WINUI_ROOT / "Pages" / f"{page_type}.xaml").is_file()
        assert (WINUI_ROOT / "Pages" / f"{page_type}.xaml.cs").is_file()

    assert "PlaceholderPage" not in window
    assert not (WINUI_ROOT / "Pages" / "PlaceholderPage.xaml").exists()


def test_native_submitter_pages_preserve_the_original_information_architecture() -> None:
    page_expectations = {
        "NewJobPage.xaml": (
            "作业输入",
            "执行环境与资源",
            "运行选项",
            "预览提交命令",
            "提交作业",
        ),
        "JobQueuePage.xaml": (
            "候选区",
            "正式队列",
            "扫描文件夹",
            "开始队列",
            "重启动依赖",
        ),
        "JobOverviewPage.xaml": (
            "状态",
            "进度",
            "目录",
            "STA",
            "MSG",
            "DAT",
            "运行日志",
        ),
        "ComputeResourcesPage.xaml": (
            "资源节点",
            "连接状态",
            "CPU",
            "内存",
            "计算目录",
            "活动作业",
        ),
        "RestartChainPage.xaml": (
            "依赖拓扑",
            "循环依赖",
            "缺失父作业",
            "路径兼容性",
            "提交顺序",
        ),
        "OdbMergePage.xaml": (
            "原始 ODB",
            "重启动 ODB",
            "输出 ODB",
            "包含历史输出",
            "结果命名",
            "合并结果",
        ),
    }

    for filename, expected_texts in page_expectations.items():
        text = (WINUI_ROOT / "Pages" / filename).read_text(encoding="utf-8")
        if filename == "JobQueuePage.xaml":
            text += (WINUI_ROOT / "Controls" / "QueueTableRow.cs").read_text(encoding="utf-8")
        for expected in expected_texts:
            assert expected in text


def test_native_pages_use_the_full_workbench_without_static_placeholder_rails() -> None:
    shell = (WINUI_ROOT / "MainWindow.xaml").read_text(encoding="utf-8")

    assert 'x:Name="ContentFrame"' in shell
    assert 'x:Name="ProjectRail"' not in shell
    assert 'x:Name="PropertiesRail"' not in shell
    assert 'x:Name="LogPanel"' not in shell
    assert "<TabView" not in shell


def test_reported_workbench_layout_regressions_stay_fixed() -> None:
    shell_root = ET.parse(WINUI_ROOT / "MainWindow.xaml").getroot()
    odb_root = ET.parse(WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml").getroot()
    new_job_root = ET.parse(WINUI_ROOT / "Pages" / "NewJobPage.xaml").getroot()

    explorer_host = _named_element(shell_root, "ExplorerHost")
    assert explorer_host.attrib["Width"] == "280"
    explorer_root = ET.parse(
        WINUI_ROOT / "Controls" / "WorkbenchExplorerHost.xaml"
    ).getroot()
    assert _named_element(explorer_root, "ExplorerTree") is not None
    assert _named_element(explorer_root, "ExplorerRefreshButton") is not None
    assert _named_element(explorer_root, "ExplorerSearchBox") is not None
    assert _named_element(explorer_root, "ExplorerSelectionCard") is not None
    shell_text = (
        WINUI_ROOT / "Controls" / "WorkbenchExplorerHost.xaml"
    ).read_text(encoding="utf-8")
    for expected_text in (
        "搜索当前内容",
        "刷新当前浏览内容",
        "当前没有可浏览的内容",
    ):
        assert expected_text in shell_text

    window_code = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    adapter_code = (
        WINUI_ROOT / "Explorer" / "WorkbenchExplorerAdapters.cs"
    ).read_text(encoding="utf-8")
    assert "ExplorerHost.Attach" in window_code
    assert "RefreshProjectExplorerAsync" not in window_code
    assert "ProjectExplorerAdapter" in adapter_code
    assert "DiscoverSiblingOdbs" in adapter_code
    assert "ActivateFallbackExplorerItemAsync" in window_code
    new_job_code = (WINUI_ROOT / "Pages" / "NewJobPage.xaml.cs").read_text(
        encoding="utf-8"
    )
    odb_code = (
        WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs"
    ).read_text(encoding="utf-8")
    assert "LoadInputPath" in new_job_code
    assert "UpdateSelectedInputPath" in new_job_code
    assert "LoadOdbPathAsync" in odb_code

    navigation_items = shell_root.findall(
        ".//xaml:NavigationView.MenuItems/xaml:NavigationViewItem",
        XAML_NAMESPACE,
    )
    assert {item.attrib["MinWidth"] for item in navigation_items} == {"118"}
    assert _named_element(shell_root, "ShellNavigation").attrib["KeyboardAcceleratorPlacementMode"] == "Hidden"
    shortcuts = shell_root.findall(".//xaml:NavigationView.KeyboardAccelerators/xaml:KeyboardAccelerator", XAML_NAMESPACE)
    assert {item.attrib["Key"] for item in shortcuts} == {"B", "Number7", "Number8"}

    output_settings = _named_element(odb_root, "OutputSettingsExpander")
    assert output_settings.attrib["HorizontalAlignment"] == "Stretch"
    assert output_settings.attrib["HorizontalContentAlignment"] == "Stretch"
    settings_grid = _named_element(odb_root, "OutputSettingsGrid")
    assert settings_grid.attrib["MinWidth"] == "0"

    postprocess_log = _named_element(odb_root, "PostprocessLogExpander")
    assert postprocess_log.attrib["HorizontalAlignment"] == "Stretch"
    assert postprocess_log.attrib["HorizontalContentAlignment"] == "Stretch"

    input_picker_column = _named_element(new_job_root, "InputPickerColumn")
    assert input_picker_column.attrib["Width"] == "138"
    resource_grid = _named_element(new_job_root, "ResourceGrid")
    resource_columns = resource_grid.find("xaml:Grid.ColumnDefinitions", XAML_NAMESPACE)
    assert resource_columns is not None
    assert [column.attrib["Width"] for column in resource_columns] == ["*", "*"]
    assert resource_grid.attrib["SizeChanged"] == "OnResourceGridSizeChanged"
    assert _named_element(new_job_root, "PriorityComboBox").attrib["HorizontalAlignment"] == "Stretch"

    command_preview = _named_element(new_job_root, "CommandPreviewExpander")
    assert command_preview.attrib["HorizontalAlignment"] == "Stretch"
    assert command_preview.attrib["HorizontalContentAlignment"] == "Stretch"
    assert _named_element(new_job_root, "PreviewButton").attrib["MinWidth"] == "148"
    assert _named_element(new_job_root, "SubmitButton").attrib["MinWidth"] == "190"


def test_subpages_use_compact_headers_and_consistent_picker_buttons() -> None:
    page_names = (
        "NewJobPage.xaml",
        "JobQueuePage.xaml",
        "JobOverviewPage.xaml",
        "ComputeResourcesPage.xaml",
        "RestartChainPage.xaml",
        "OdbMergePage.xaml",
        "OdbPostprocessingPage.xaml",
        "ResultBrowserPage.xaml",
    )
    page_texts = {
        name: (WINUI_ROOT / "Pages" / name).read_text(encoding="utf-8")
        for name in page_names
    }
    assert all("WorkbenchPageTitleStyle" not in text for text in page_texts.values())
    assert 'Text="ODB 后处理工作台"' not in page_texts["OdbPostprocessingPage.xaml"]
    assert 'Text="结果浏览"' not in page_texts["ResultBrowserPage.xaml"]

    odb_root = ET.parse(WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml").getroot()
    settings_grid = _named_element(odb_root, "OutputSettingsGrid")
    row_definitions = settings_grid.find("xaml:Grid.RowDefinitions", XAML_NAMESPACE)
    assert row_definitions is not None
    assert len(row_definitions.findall("xaml:RowDefinition", XAML_NAMESPACE)) == 5

    app_root = ET.parse(WINUI_ROOT / "App.xaml").getroot()
    picker_style = next(
        style
        for style in app_root.findall(".//xaml:Style", XAML_NAMESPACE)
        if style.attrib.get(XAML_KEY) == "WorkbenchPickerButtonStyle"
    )
    setters = {
        setter.attrib["Property"]: setter.attrib["Value"]
        for setter in picker_style.findall("xaml:Setter", XAML_NAMESPACE)
    }
    assert setters["MinWidth"] == "138"
    assert setters["HorizontalContentAlignment"] == "Center"
    assert setters["VerticalContentAlignment"] == "Center"

    picker_names = {
        "NewJobPage.xaml": (
            "ChooseInputButton",
            "ChooseOldjobButton",
            "ChooseFortranButton",
            "ChooseCalculationRootButton",
            "ChooseArchiveRootButton",
        ),
        "OdbMergePage.xaml": (
            "ChooseOriginalButton",
            "ChooseRestartButton",
            "ChooseOutputButton",
        ),
        "OdbPostprocessingPage.xaml": ("BrowseButton",),
        "ResultBrowserPage.xaml": ("BrowseButton",),
    }
    for page_name, names in picker_names.items():
        page_root = ET.parse(WINUI_ROOT / "Pages" / page_name).getroot()
        for name in names:
            assert _named_element(page_root, name).attrib["Style"] == (
                "{StaticResource WorkbenchPickerButtonStyle}"
            )

    for page_name, required_actions in {
        "JobQueuePage.xaml": ("RefreshQueueButton", "EditCandidateButton"),
        "JobOverviewPage.xaml": ("JobSelector", "OverviewMessageText"),
        "ComputeResourcesPage.xaml": ("RefreshButton", "AddServerButton"),
        "RestartChainPage.xaml": ("RefreshButton",),
        "OdbPostprocessingPage.xaml": ("OpenResultsButton",),
    }.items():
        page_root = ET.parse(WINUI_ROOT / "Pages" / page_name).getroot()
        for action in required_actions:
            assert _named_element(page_root, action) is not None


def test_shell_uses_the_compact_legacy_style_custom_title_bar() -> None:
    shell = (WINUI_ROOT / "MainWindow.xaml").read_text(encoding="utf-8")
    window = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")

    assert 'x:Name="WindowTitleText"' in shell
    assert "Abaqus Workbench — 新建作业" in shell
    assert 'x:Name="TitleBarDragRegion"' in shell
    assert "WinUI 3 前端" not in shell
    assert "原生工作台" not in shell
    assert "ExtendsContentIntoTitleBar = true" in window
    assert "SetTitleBar(TitleBarDragRegion)" in window


def test_new_job_page_uses_native_pickers_and_control_plane_command_preview() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    page = (WINUI_ROOT / "Pages" / "NewJobPage.xaml.cs").read_text(
        encoding="utf-8"
    )
    xaml = (WINUI_ROOT / "Pages" / "NewJobPage.xaml").read_text(
        encoding="utf-8"
    )

    assert '"/api/v1/local-job-draft-previews"' in host
    assert "PreviewLocalJobDraftAsync" in host
    assert "FileOpenPicker" in page
    assert "FolderPicker" in page
    assert "OnPreviewClicked" in page
    assert 'Click="OnChooseInputClicked"' in xaml
    assert 'Click="OnPreviewClicked"' in xaml


def test_local_resource_snapshot_drives_shell_status_and_compute_page() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    window = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    page = (WINUI_ROOT / "Pages" / "ComputeResourcesPage.xaml.cs").read_text(
        encoding="utf-8"
    )

    assert '"/api/v1/local-resources"' in host
    assert "GetLocalResourceAsync" in host
    assert "DispatcherTimer" in window
    assert "ApplyLocalResourceSnapshot" in window
    assert "ApplySnapshot(LocalResourceSnapshot snapshot)" in page
    assert "RefreshLocalResourceNowAsync" in page


def test_compute_resource_background_refresh_keeps_toolbar_interactive() -> None:
    page = (WINUI_ROOT / "Pages" / "ComputeResourcesPage.xaml.cs").read_text(
        encoding="utf-8"
    )

    timer_handler = page.split(
        "private async void OnRemoteRefreshTimerTick", maxsplit=1
    )[1].split("private async void OnRefreshClicked", maxsplit=1)[0]
    background_refresh = page.split(
        "private async Task RefreshRemoteSnapshotInBackgroundAsync", maxsplit=1
    )[1].split("private async void OnRefreshClicked", maxsplit=1)[0]

    assert "_backgroundRefreshBusy" in page
    assert "RefreshRemoteSnapshotInBackgroundAsync" in timer_handler
    assert "RunRemoteActionAsync" not in timer_handler
    assert "_backgroundRefreshBusy = true" in background_refresh
    assert "_backgroundRefreshBusy = false" in background_refresh
    assert "_busy = true" not in background_refresh
    assert "UpdateButtons();" not in background_refresh


def test_cross_page_remote_menu_checks_transfer_discovery_before_dispatch() -> None:
    page = (WINUI_ROOT / "Pages" / "ComputeResourcesPage.xaml.cs").read_text(encoding="utf-8")
    shell = (WINUI_ROOT / "MainWindow.Commands.cs").read_text(encoding="utf-8").split("private async Task RunRemoteMenuAsync", 1)[1]
    loading = page.split("private async void OnPageLoaded", 1)[1].split("public bool SelectConnectedServer", 1)[0]
    recovery = page.split("private async Task RecoverTransfersAsync", 1)[1].split("private void ShowTransferObservationWarning", 1)[0]
    assert loading.index("await RecoverTransfersAsync(ready)") < loading.index("ready.TrySetResult(")
    assert recovery.index("if (!operation.IsTerminal) menuReady?.TrySetResult(false)") < recovery.index("await ObserveTransferAsync(")
    assert shell.index("await page.WaitForMenuReadyAsync()") < shell.index("if (!ready)") < shell.index("page.SelectConnectedServer(profile)")
    assert shell.index("var expected = commands.ConnectedProfile!") < shell.index("NavigateToRoute(")
    assert "page.DisconnectAsync(expected)" in shell and "page.RefreshConnectedServerAsync(expected)" in shell


def test_transfer_observation_preserves_identity_and_never_resubmits_on_refresh() -> None:
    page = (WINUI_ROOT / "Pages" / "ComputeResourcesPage.xaml.cs").read_text(encoding="utf-8")
    unload = page.split("private void OnPageUnloaded", 1)[1].split("private async void OnRemoteRefreshTimerTick", 1)[0]
    recovery = page.split("private async Task RecoverTransfersAsync", 1)[1].split("private void ShowTransferObservationWarning", 1)[0]
    observer = page.split("private async Task<RemoteTransferOperationSnapshot> ObserveTransferAsync", 1)[1].split("private async Task RecoverTransfersAsync", 1)[0]
    assert "_transferObservationSource.Cancel()" in unload
    assert "CancelRemoteTransferAsync" not in unload
    assert "GetRemoteTransferAsync(_activeTransferId, observationToken)" in recovery
    assert "GetActiveRemoteTransfersAsync(observationToken)" in recovery
    assert "StartRemoteTransferAsync" not in recovery and "CancelRemoteTransferAsync" not in recovery
    assert "_activeTransferId = string.Empty" not in recovery.split("finally", 1)[1]
    assert "operation.IsTerminal ? operation" in observer
    assert "}, cancellationToken)" in observer
    assert 'error.Code == "REMOTE_TRANSFER_NOT_FOUND"' in recovery
    assert 'ShowError("后台传输状态读取失败' not in recovery


def test_shell_uses_page_aware_workbench_explorer_modules() -> None:
    shell = (WINUI_ROOT / "MainWindow.xaml").read_text(encoding="utf-8")
    window = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    models = (WINUI_ROOT / "Explorer" / "WorkbenchExplorerModels.cs").read_text(
        encoding="utf-8"
    )
    adapters = (
        WINUI_ROOT / "Explorer" / "WorkbenchExplorerAdapters.cs"
    ).read_text(encoding="utf-8")
    host_xaml = (
        WINUI_ROOT / "Controls" / "WorkbenchExplorerHost.xaml"
    ).read_text(encoding="utf-8")
    host_code = (
        WINUI_ROOT / "Controls" / "WorkbenchExplorerHost.xaml.cs"
    ).read_text(encoding="utf-8")

    assert "IWorkbenchExplorerAdapter" in models
    assert "IWorkbenchExplorerPage" in models
    assert "StableId" in models
    for adapter in (
        "ProjectExplorerAdapter",
        "WorkspaceExplorerAdapter",
        "QueueExplorerAdapter",
        "JobMonitorExplorerAdapter",
        "ResourceExplorerAdapter",
        "RestartChainExplorerAdapter",
        "OdbMergeExplorerAdapter",
        "PostprocessingExplorerAdapter",
        "ResultExplorerAdapter",
    ):
        assert f"class {adapter}" in adapters

    assert "WorkbenchExplorerHost" in shell
    assert "ProjectExplorerRail" not in shell
    assert "ProjectTree" not in shell
    assert "ExplorerHost.Attach" in window
    assert "_projectNodePaths" not in window
    assert 'x:Name="ExplorerSearchBox"' in host_xaml
    assert "RestoreSelection" in host_code
    assert "ApplyFilter" in host_code

    for page_name in (
        "NewJobPage",
        "JobQueuePage",
        "JobOverviewPage",
        "ComputeResourcesPage",
        "RestartChainPage",
        "OdbMergePage",
        "OdbPostprocessingPage",
        "ResultBrowserPage",
    ):
        page = (WINUI_ROOT / "Pages" / f"{page_name}.xaml.cs").read_text(
            encoding="utf-8"
        )
        assert f"{page_name} : Page, IWorkbenchExplorerPage" in page
        assert "ExplorerAdapter" in page


def test_workbench_explorer_tree_template_binds_through_tree_node_content() -> None:
    xaml = (
        WINUI_ROOT / "Controls" / "WorkbenchExplorerHost.xaml"
    ).read_text(encoding="utf-8")

    for field in ("IconGlyph", "Title", "Subtitle", "Badge"):
        assert f"{{Binding Content.{field}}}" in xaml
    assert 'Text="{Binding Title}"' not in xaml


def test_workbench_explorer_collapses_empty_subtitle_for_single_line_groups() -> None:
    xaml = (
        WINUI_ROOT / "Controls" / "WorkbenchExplorerHost.xaml"
    ).read_text(encoding="utf-8")
    converter = (
        WINUI_ROOT / "Controls" / "NonEmptyStringToVisibilityConverter.cs"
    ).read_text(encoding="utf-8")

    assert 'x:Key="NonEmptyStringToVisibilityConverter"' in xaml
    assert (
        'Visibility="{Binding Content.Subtitle, '
        'Converter={StaticResource NonEmptyStringToVisibilityConverter}}"'
    ) in xaml
    assert 'VerticalAlignment="Center"' in xaml
    assert "string.IsNullOrWhiteSpace" in converter
    assert "Visibility.Collapsed" in converter


def test_parallel_limit_inputs_have_space_for_permanent_buttons() -> None:
    for page, name in (("JobQueuePage.xaml", "ParallelLimitNumberBox"),
                       ("NewJobPage.xaml", "MaxParallelNumberBox"),
                       ("OdbPostprocessingPage.xaml", "ParallelWorkersNumberBox")):
        control = _named_element(ET.parse(WINUI_ROOT / "Pages" / page).getroot(), name)
        assert control.tag.endswith('}WorkbenchNumberBox')
        assert control.get("SpinButtonPlacementMode") == "Inline"
        assert float(control.get("Width", "0")) >= 160


def test_queue_numbers_use_the_frame_of_their_neighboring_fields() -> None:
    page = ET.parse(WINUI_ROOT / "Pages" / "JobQueuePage.xaml").getroot()
    assert _named_element(page, "ParallelLimitNumberBox").get("FrameAppearance") == "ComboBox"
    editor = (WINUI_ROOT / "Pages" / "JobQueuePage.Edit.cs").read_text(encoding="utf-8")
    assert editor.count("FrameAppearance = Controls.NumberBoxFrameAppearance.TextField") == 2


def test_feedback_overlay_and_unread_job_menu_do_not_reserve_page_rows() -> None:
    shell = ET.parse(WINUI_ROOT / "MainWindow.xaml").getroot()
    overlay = _named_element(shell, "FeedbackHost")
    navigation = _named_element(shell, "ShellNavigation")
    parent = next(node for node in shell.iter() if overlay in node)
    assert navigation in parent and overlay.get("Grid.Row") == navigation.get("Grid.Row")
    assert (overlay.get("HorizontalAlignment"), overlay.get("VerticalAlignment")) == ("Right", "Bottom")
    menu = _named_element(shell, "WindowMenuBar")
    assert _named_element(menu, "JobNotificationFlyout").tag.endswith("}Flyout")
    queue = ET.parse(WINUI_ROOT / "Pages" / "JobQueuePage.xaml")
    assert not any(child.tag.endswith("}InfoBar") for child in queue.iter())


def test_adjustable_numeric_fields_use_the_same_permanent_button_control() -> None:
    import re
    xaml_fields = []
    dynamic_count = 0
    for page in (WINUI_ROOT / "Pages").glob("*.xaml"):
        xaml_fields.extend(node for node in ET.parse(page).iter()
                           if node.tag.endswith("}WorkbenchNumberBox"))
        assert not any(node.tag.endswith("}NumberBox") for node in ET.parse(page).iter())
    for page in (WINUI_ROOT / "Pages").glob("*.cs"):
        source = page.read_text(encoding="utf-8")
        dynamic_count += len(re.findall(r"new Controls\.WorkbenchNumberBox\b", source))
        assert "new NumberBox" not in source
        assert "NumberBoxSpinButtonPlacementMode.Compact" not in source
        assert "NumberBoxSpinButtonPlacementMode.Hidden" not in source
    # SSH ports are typed directly; they deliberately have no stepper.
    assert len(xaml_fields) == 10 and dynamic_count == 5
    assert all(node.get("SpinButtonPlacementMode") == "Inline" for node in xaml_fields)


def test_gif_timing_controls_expose_two_modes_and_the_active_value():
    root = ET.parse(WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml").getroot()
    mode = _named_element(root, "AnimationTimingModeComboBox")
    assert [item.get("Tag") for item in mode] == ["fps", "duration"]
    assert mode.get("SelectionChanged") == "OnAnimationTimingModeChanged"
    assert _named_element(root, "AnimationFpsNumberBox").get("Value") == "25"
    duration = _named_element(root, "AnimationDurationNumberBox")
    assert duration.get("Value") == "4" and duration.get("Visibility") == "Collapsed"


def test_job_queue_restores_external_local_job_scan_controls() -> None:
    xaml = (WINUI_ROOT / "Pages" / "JobQueuePage.xaml").read_text(encoding="utf-8")
    page = (WINUI_ROOT / "Pages" / "JobQueuePage.xaml.cs").read_text(
        encoding="utf-8"
    )
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )

    for control in ("ExternalWorkDirTextBox", "ChooseExternalWorkDirButton", "ScanExternalJobsButton"):
        assert f'x:Name="{control}"' in xaml
    assert 'Text="工作目录："' in xaml
    assert 'Content="浏览…"' in xaml
    assert 'Content="扫描"' in xaml
    assert (
        xaml.index('x:Name="FormalQueueActionBar"')
        < xaml.index('x:Name="ExternalJobScanBar"')
        < xaml.index('x:Name="FormalTable"')
    )
    assert "OnScanExternalJobsClicked" in page
    assert "ScanExternalJobsAsync" in page
    assert "ScanExternalJobsAsync" in host
    assert 'Action = "scanExternalJobs"' in host
    assert '"jobQueue.scanExternalJobs"' in host
    assert "health.Capabilities.Contains" in host


def test_job_queue_page_restores_persisted_candidates_and_formal_jobs() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    page = (WINUI_ROOT / "Pages" / "JobQueuePage.xaml.cs").read_text(
        encoding="utf-8"
    )
    xaml = (WINUI_ROOT / "Pages" / "JobQueuePage.xaml").read_text(
        encoding="utf-8"
    )

    assert '"/api/v1/job-queues"' in host
    assert "GetJobQueuesAsync" in host
    assert "ObservableCollection<JobQueueItem>" in page
    assert "GetJobQueuesAsync" in page
    assert "AddJobQueueCandidatesAsync" in page
    assert "StartLocalQueueAsync" in page
    assert "PreviewQueueTerminationAsync" in page and "ConfirmQueueTerminationAsync(preview)" in page
    assert "ContentDialogButton.Close" in page and 'PrimaryButtonText = "终止整个队列"' in page
    assert "LOCAL_QUEUE_TERMINATION_SCOPE_CHANGED" in page
    assert _named_element(ET.fromstring(xaml), "TerminateEntireQueueButton").attrib["Click"] == "OnTerminateEntireQueueClicked"
    assert "QueueListUpdates.Apply(CandidateList, _candidates, snapshot.Candidates)" in page
    assert "QueueListUpdates.Apply(FormalQueueList, _queueItems, snapshot.QueueItems)" in page
    updates = (WINUI_ROOT / "Controls" / "QueueListUpdates.cs").read_text(encoding="utf-8")
    assert "list.SelectedItems.Add(row)" in updates
    assert 'x:Name="CandidateTable"' in xaml
    assert 'CandidateTable.List' in page
    assert 'x:Name="FormalTable"' in xaml
    assert 'FormalTable.List' in page


def test_job_overview_uses_the_shared_queue_snapshot_and_safe_file_launchers() -> None:
    page = (WINUI_ROOT / "Pages" / "JobOverviewPage.xaml.cs").read_text(
        encoding="utf-8"
    )
    xaml = (WINUI_ROOT / "Pages" / "JobOverviewPage.xaml").read_text(
        encoding="utf-8"
    )

    assert "GetLocalQueueRuntimeAsync" in page
    assert "SetLocalQueueItemsPausedAsync" in page
    assert "TerminateLocalQueueItemsAsync" in page
    assert "Launcher.LaunchFolderAsync" in page
    assert "Launcher.LaunchFileAsync" in page
    assert "File.Exists(path)" in page
    assert 'x:Name="JobSelector"' in xaml
    assert 'Tag=".sta"' in xaml
    assert 'Tag=".msg"' in xaml
    assert 'Tag=".dat"' in xaml


def test_restart_chain_page_uses_the_control_plane_dependency_model() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    page = (WINUI_ROOT / "Pages" / "RestartChainPage.xaml.cs").read_text(
        encoding="utf-8"
    )
    xaml = (WINUI_ROOT / "Pages" / "RestartChainPage.xaml").read_text(
        encoding="utf-8"
    )

    assert '"/api/v1/restart-chains"' in host
    assert "GetRestartChainsAsync" in host
    assert "ObservableCollection<RestartChainNode>" in page
    assert "GetRestartChainsAsync" in page
    assert 'x:Name="RestartGraphCanvas"' in xaml
    assert "RenderRestartGraph" in page
    assert "GenerateFullResultButton" in xaml
    assert "CreateRestartResultPlanAsync" in page
    assert "NavigateToOdbMergePlan" in page
    assert 'x:Name="CycleCheckText"' in xaml


def test_restart_graph_uses_scrollviewer_zoom_and_validates_in_the_open_editor() -> None:
    page = (WINUI_ROOT / "Pages" / "RestartChainPage.xaml.cs").read_text(encoding="utf-8")
    xaml = (WINUI_ROOT / "Pages" / "RestartChainPage.xaml").read_text(encoding="utf-8")
    viewer = xaml.split('x:Name="RestartGraphScrollViewer"', 1)[1].split(">", 1)[0]
    assert 'ZoomMode="Enabled"' in viewer and "viewer.ChangeView(" in page
    assert "RestartGraphCanvas.RenderTransform" not in page

    save = page.split("dialog.PrimaryButtonClick +=", 1)[1].split("await dialog.ShowAsync()", 1)[0]
    assert save.index("args.GetDeferral()") < save.index("await App.Current.ControlPlane.UpdateRestartDependencyAsync")
    assert save.index("UpdateRestartDependencyAsync") < save.index("args.Cancel = false")
    assert "error.Visibility = Visibility.Visible" in save and "deferral.Complete()" in save


def test_restart_result_materialization_is_separate_from_the_job_graph() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    restart_page = (WINUI_ROOT / "Pages" / "RestartChainPage.xaml.cs").read_text(
        encoding="utf-8"
    )
    restart_xaml = (WINUI_ROOT / "Pages" / "RestartChainPage.xaml").read_text(
        encoding="utf-8"
    )
    merge_page = (WINUI_ROOT / "Pages" / "OdbMergePage.xaml.cs").read_text(
        encoding="utf-8"
    )
    merge_xaml = (WINUI_ROOT / "Pages" / "OdbMergePage.xaml").read_text(
        encoding="utf-8"
    )

    assert '"/api/v1/restart-result-plans"' in host
    assert "CreateRestartResultPlanAsync" in host
    assert "RestartResultPlan" in restart_page
    assert "MergeNode" not in restart_page
    assert "合并节点" not in restart_xaml
    assert "LoadMaterializationPlan" in merge_page
    assert "个节点 · {snapshot.NodeCount} 个重启动作业" in restart_page
    assert "{_nodes.Count} 个节点" in restart_page
    assert 'x:Name="MaterializationPlanCard"' in merge_xaml
    assert 'x:Name="MaterializationStepsList"' in merge_xaml


def test_merge_execute_button_and_click_dispatch_use_the_same_checked_plan() -> None:
    page = (WINUI_ROOT / "Pages" / "OdbMergePage.xaml.cs").read_text(encoding="utf-8")
    graph = (WINUI_ROOT / "Pages" / "OdbMergePage.ResultGraph.cs").read_text(encoding="utf-8")
    editor = (WINUI_ROOT / "Controls" / "OdbResultGraphEditor.xaml.cs").read_text(encoding="utf-8")
    assert "ExecuteButton.IsEnabled = ExecutionCommand != OdbMergeCommand.None;" in page
    click = page.split("private async void OnExecuteClicked(", 1)[1].split("private async void OnStopClicked", 1)[0]
    assert click.index("switch (ExecutionCommand)") < click.index("await ExecuteResultBatchAsync();")
    assert click.index("case OdbMergeCommand.Manual:") < click.index("await PreviewDraftAsync()")
    assert click.index("preview.WillOverwrite && !await ConfirmOverwriteAsync") < click.index("StartOdbMergeAsync(")
    mode_change = graph.split("private void OnMergeModeChanged(", 1)[1].split("private void OnResultGraphChanged", 1)[0]
    assert "DetachMaterializationPlan();" in mode_change and "InvalidatePlan();" in mode_change
    assert "MergeModeComboBox.SelectedIndex != 0" in graph.split("private void OnGraphPlansRequested(", 1)[1].split("private async Task", 1)[0]
    assert 'kind = "graph"' in graph and 'kind = "restart"' in graph
    assert "if (requestVersion != _planRequestVersion) return;" in editor
    assert "_savedSnapshot.HasEdits(OutputDirectoryTextBox.Text, _nodes)" in editor


def test_postprocess_partial_scan_recovery_cannot_overwrite_workspace() -> None:
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(encoding="utf-8")
    recovery = page.split("private void RestoreRowsFromPostprocessRequest(", 1)[1].split(
        "private async Task RecoverActiveCompatibilityOperationAsync", 1
    )[0]
    # Recovery contains only the scan request's subset, not a complete discovery.
    # Null keeps SaveWorkspace guarded and makes the next discovery load disk state.
    assert "_lastDiscoveryRoot = null;" in recovery
    assert "_lastDiscoveryRoot = request.Root;" not in recovery
    compatibility = page.split("private void RestoreRowsFromOperationRequest(", 1)[1].split(
        "private static OdbDiscoveryItem CreateRecoveryDiscoveryItem", 1
    )[0]
    assert "_lastDiscoveryRoot = null;" in compatibility
    assert "_lastDiscoveryRoot = request.Root;" not in compatibility
    save = page.split("private bool SaveWorkspace(bool forClose = false)", 1)[1].split(
        "private OdbPostprocessOutputOptions", 1
    )[0]
    assert "_lastDiscoveryRoot is null" in save


def test_postprocess_execution_uses_isolated_group_identity() -> None:
    page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(encoding="utf-8")
    scope = (WINUI_ROOT / "Services" / "OdbScopedRunPlan.cs").read_text(encoding="utf-8")
    assert "OdbComparisonGroups.ForExecution(rows)" in scope
    assert "Standalone = group.Standalone" in scope
    assert "!group.Standalone && legends.TryGetValue" in scope
    assert "OdbComparisonGroups.OrderMembers(group.Members," in scope
    assert "var submission = BuildScopedQueueRequest();" in page
    assert "if (plan.CanRun) return BuildQueueRequest(plan.Rows, plan.Groups);" in page
    assert "RunPostprocessButton.IsEnabled = idle && runScope.CanRun;" in page
    assert "_groupQueue?.Groups," in page
    assert "_lastDiscoveryRoot is null || !_unreadableWorkspaces.Contains(PathKey(_lastDiscoveryRoot))" in page
    assert "_unreadableWorkspaces.Remove(PathKey(result.Root));" in page
    drafts = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.Drafts.cs").read_text(encoding="utf-8")
    assert "GroupMemberOrder = _groupMemberOrder.ToDictionary" in drafts
    xaml = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml").read_text(encoding="utf-8")
    assert 'Click="OnGroupOrderClicked"' in xaml
    assert 'Click="OnManageGroupsClicked"' in xaml
    assert 'x:Name="RunScopeComboBox" Header="运行范围"' in xaml
    assert "OdbComparisonGroups.ChangeGroup(_odbItems, oldName," in page
    assert 'Click="OnCreateGroupsClicked"' in xaml
    assert "ManageGroupsButton.IsEnabled = CreateGroupsButton.IsEnabled" in page


def test_group_execution_order_uses_the_saved_workspace_and_the_actual_run_plan() -> None:
    pages = WINUI_ROOT / "Pages"
    xaml = (pages / "OdbPostprocessingPage.xaml").read_text(encoding="utf-8")
    page = (pages / "OdbPostprocessingPage.xaml.cs").read_text(encoding="utf-8")
    editor = (pages / "OdbPostprocessingPage.GroupExecutionOrder.cs").read_text(encoding="utf-8")
    drafts = (pages / "OdbPostprocessingPage.Drafts.cs").read_text(encoding="utf-8")
    for event in ("OnGroupOrderClicked", "OnGroupExecutionOrderClicked", "OnRunOrderPreviewClicked"):
        assert f'Click="{event}"' in xaml
    assert "RunScopePreviewText.Text = runScope.Summary;" in page
    assert "BuildQueueRequest(plan.Rows, plan.Groups)" in page
    preview = editor.split("private async void OnRunOrderPreviewClicked", 1)[1]
    assert "ResolveRunScope(" in preview and "plan.Groups.Select(" in preview
    assert "saved?.GroupExecutionOrder.ToList()" in page
    assert "GroupExecutionOrder = [.. _groupExecutionOrder]" in drafts
    assert "_groupExecutionOrder = [.. workspace.GroupExecutionOrder]" in drafts
    assert "ShowRecoverableDialogAsync" in editor and "CompleteDialogDraftAsync" in editor
    assert editor.index("click.Cancel = true;") < editor.index("TrySaveWorkspaceChange(")
    assert editor.index("TrySaveWorkspaceChange(") < editor.index("_groupExecutionOrder = nextOrder;")
    assert editor.index("_groupExecutionOrder = nextOrder;") < editor.index("click.Cancel = false;")


def test_odb_merge_page_uses_native_pickers_and_safe_plan_preview() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    page = (WINUI_ROOT / "Pages" / "OdbMergePage.xaml.cs").read_text(
        encoding="utf-8"
    )
    xaml = (WINUI_ROOT / "Pages" / "OdbMergePage.xaml").read_text(
        encoding="utf-8"
    )

    assert '"/api/v1/odb-merge-draft-previews"' in host
    assert "PreviewOdbMergeDraftAsync" in host
    assert "FileOpenPicker" in page
    assert "FolderPicker" in page
    assert "PreviewOdbMergeDraftAsync" in page
    assert 'Click="OnChooseOriginalClicked"' in xaml
    assert 'Click="OnChooseRestartClicked"' in xaml
    assert 'Click="OnChooseOutputClicked"' in xaml
    assert 'Click="OnPreviewClicked"' in xaml
    assert 'x:Name="ExecuteButton"' in xaml
    assert 'IsEnabled="False"' in xaml


def test_odb_merge_page_executes_tracks_cancels_and_recovers_operations() -> None:
    host = (WINUI_ROOT / "Services" / "ControlPlaneHost.cs").read_text(
        encoding="utf-8"
    )
    page = (WINUI_ROOT / "Pages" / "OdbMergePage.xaml.cs").read_text(
        encoding="utf-8"
    )
    xaml = (WINUI_ROOT / "Pages" / "OdbMergePage.xaml").read_text(
        encoding="utf-8"
    )

    for expected in (
        "StartOdbMergeAsync",
        "PollOdbMergeUntilTerminalAsync",
        "CancelOdbMergeOperationAsync",
        "ListOdbMergeOperationsAsync",
        "BestEffortCancelOdbMergeAsync",
    ):
        assert expected in host
    assert "StartOdbMergeAsync" in page
    assert "PollOdbMergeUntilTerminalAsync" in page
    assert "CancelOdbMergeOperationAsync" in page
    assert "ListOdbMergeOperationsAsync" in page
    assert "ConfirmOverwriteAsync" in page
    assert "Launcher.LaunchFileAsync" in page
    assert "Launcher.LaunchFolderAsync" in page
    assert 'Click="OnExecuteClicked"' in xaml
    assert 'Click="OnStopClicked"' in xaml
    assert "StopButton.IsEnabled = OdbMergeExecution.CanStop(_batchBusy, _operationBusy, _activeOperationId, _cancelRequested)" in page
    observer = page.split("private async Task<OdbMergeOperationSnapshot> ObserveOperationAsync", 1)[1].split("private void OnClearMaterializationClicked", 1)[0]
    assert observer.index("_activeOperationId = initial.IsTerminal ? null : initial.OperationId") < observer.index("RefreshInteractionState()") < observer.index("PollOdbMergeUntilTerminalAsync")
    assert "_activeOperationId ??= snapshot.OperationId" not in page
    assert 'x:Name="MergeOperationLogTextBox"' in xaml
    assert "AbaqusCommandTextBox" not in xaml


def test_overview_directory_and_output_download_identify_the_selected_remote_job():
    page = (WINUI_ROOT / "Pages" / "JobOverviewPage.xaml.cs").read_text(encoding="utf-8")
    browser = (WINUI_ROOT / "Pages" / "RemoteFileBrowserDialog.cs").read_text(encoding="utf-8")
    directory = page.split("private async void OnOpenDirectoryClicked", 1)[1].split("var currentJob", 1)[0]
    assert "RemoteSelectionMode.Browse" in directory and "remote.OperationId" in directory
    assert "DownloadRemoteOutputAsync(remote.OperationId, remotePath)" in page
    assert "sourceOperationId: sourceOperationId" in page
    assert "sourceOperationId: _sourceOperationId, expectedProfile: _expectedProfile" in browser


def test_both_remote_download_pages_use_the_path_only_picker_and_its_overwrite_decision():
    pages = WINUI_ROOT / "Pages"
    picker = (pages / "RemoteDownloadDestination.cs").read_text(encoding="utf-8")
    assert "using Microsoft.Windows.Storage.Pickers;" in picker
    assert "ShowOverwritePrompt = false" in picker
    assert "DefaultButton = ContentDialogButton.Close" in picker
    for source in ("ComputeResourcesPage.xaml.cs", "JobOverviewPage.xaml.cs"):
        page = (pages / source).read_text(encoding="utf-8")
        assert "RemoteDownloadDestination.PickAsync(" in page
        assert "destination.Overwrite" in page
