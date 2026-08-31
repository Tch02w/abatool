from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINUI_ROOT = ROOT / "winui" / "AbaqusTools.WinUI"
XAML_NAMESPACE = {"xaml": "http://schemas.microsoft.com/winfx/2006/xaml/presentation"}
XAML_NAME = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
XAML_KEY = "{http://schemas.microsoft.com/winfx/2006/xaml}Key"


def _named_element(root: ET.Element, name: str) -> ET.Element:
    return next(element for element in root.iter() if element.attrib.get(XAML_NAME) == name)


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


def test_odb_page_routes_its_result_directory_into_the_native_browser() -> None:
    window = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    odb_page = (WINUI_ROOT / "Pages" / "OdbPostprocessingPage.xaml.cs").read_text(
        encoding="utf-8"
    )
    result_page = (WINUI_ROOT / "Pages" / "ResultBrowserPage.xaml.cs").read_text(
        encoding="utf-8"
    )

    assert "OpenResultBrowserAsync" in window
    assert 'Path.Combine(root, "AbaqusODBPostProcessor_Results")' in odb_page
    assert "Directory.Exists(resultRoot)" in odb_page
    assert "SetResultRootAsync" in result_page
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

    project_rail = _named_element(shell_root, "ProjectExplorerRail")
    assert project_rail.attrib["Width"] == "260"
    assert _named_element(shell_root, "ProjectTree") is not None
    assert _named_element(shell_root, "ProjectRefreshButton") is not None
    assert _named_element(shell_root, "ProjectCpuProgress") is not None
    assert _named_element(shell_root, "ProjectMemoryProgress") is not None
    shell_text = (WINUI_ROOT / "MainWindow.xaml").read_text(encoding="utf-8")
    for expected_text in (
        "项目",
        "当前项目",
        "输入文件",
        "结果文件",
        "作业",
        "合并计划",
        "资源总览",
        "双击 INP 或 ODB 可载入主界面",
    ):
        assert expected_text in shell_text

    window_code = (WINUI_ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
    assert "RefreshProjectExplorerAsync" in window_code
    assert "GetJobQueuesAsync" in window_code
    assert "ApplyProjectSnapshot" in window_code
    assert "DiscoverResultFiles" in window_code
    assert "OnProjectTreeDoubleTapped" in window_code
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
    assert [column.attrib["Width"] for column in resource_columns] == [
        "92",
        "420",
        "76",
        "180",
        "*",
    ]

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
        "JobQueuePage.xaml": ("QueueInfoBar",),
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
    assert 'x:Name="CandidateList"' in xaml
    assert 'x:Name="FormalQueueList"' in xaml


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
    assert 'x:Name="ChainList"' in xaml
    assert 'x:Name="CycleCheckText"' in xaml


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
    assert 'x:Name="MergeOperationLogTextBox"' in xaml
    assert "AbaqusCommandTextBox" not in xaml
