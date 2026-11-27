using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace AbaqusTools.WinUI.Services;

public sealed partial class ControlPlaneHost : IAsyncDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
    };
    private static readonly IReadOnlySet<string> OperationStatuses =
        new HashSet<string>(StringComparer.Ordinal)
        {
            "queued",
            "starting",
            "running",
            "cancelling",
            "succeeded",
            "cancelled",
            "failed",
        };
    private static readonly IReadOnlySet<string> CompatibilityResultStatuses =
        new HashSet<string>(StringComparer.Ordinal)
        {
            "valid",
            "upgrade_required",
            "newer_release",
            "invalid",
            "missing",
            "empty",
        };

    private readonly SemaphoreSlim _connectionGate = new(1, 1);
    private readonly SemaphoreSlim _operationCreationGate = new(1, 1);
    private readonly CancellationTokenSource _shutdownSource = new();
    private readonly HttpClient _httpClient = new()
    {
        Timeout = Timeout.InfiniteTimeSpan,
    };
    private readonly StringBuilder _processOutput = new();
    private readonly object _processOutputGate = new();
    private readonly object _operationGate = new();
    private readonly object _disposeGate = new();
    private readonly HashSet<string> _activeOperationIds = new(StringComparer.Ordinal);
    private readonly HashSet<string> _activeResultIndexOperationIds = new(StringComparer.Ordinal);
    private readonly HashSet<string> _activeOdbMergeOperationIds = new(StringComparer.Ordinal);
    private readonly HashSet<string> _activePostprocessOperationIds = new(StringComparer.Ordinal);
    private readonly string _descriptorPath;
    private readonly string _launchLockPath;

    private Process? _ownedProcess;
    private string? _ownedInstanceId;
    private string? _ownedLaunchToken;
    private ControlPlaneDescriptor? _descriptor;
    private Task? _disposeTask;
    private string _lastReadinessDiagnostic = "尚未执行健康检查";
    private bool _acceptNewOperations = true;
    private bool _disposed;

    public ControlPlaneHost()
    {
        WorkbenchProfile.Current.ConfigureBackendEnvironment();
        var runtimeDirectory = Path.Combine(WorkbenchProfile.Current.StateDirectory, "runtime");
        _descriptorPath = Path.Combine(runtimeDirectory, "control-plane.json");
        _launchLockPath = Path.Combine(runtimeDirectory, "control-plane.launch.lock");
    }

    public event EventHandler<ControlPlaneStateChangedEventArgs>? StateChanged;

    public ControlPlaneState State { get; private set; } = ControlPlaneState.Disconnected;

    public string StatusMessage { get; private set; } = "控制面尚未连接";

    public string DescriptorPath => _descriptorPath;

    public async Task<ControlPlaneDescriptor> EnsureReadyAsync(CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var effectiveToken = effectiveSource.Token;
        await _connectionGate.WaitAsync(effectiveToken);
        try
        {
            if (_descriptor is not null && await IsHealthyAsync(_descriptor, effectiveToken))
            {
                SetState(ControlPlaneState.Ready, $"控制面已连接 · PID {_descriptor.Pid}");
                return _descriptor;
            }

            SetState(ControlPlaneState.Connecting, "正在连接本地控制面…");
            var existing = await TryReadDescriptorAsync(effectiveToken);
            if (existing is not null && await IsHealthyAsync(existing, effectiveToken))
            {
                _descriptor = existing;
                SetState(ControlPlaneState.Ready, $"控制面已连接 · PID {existing.Pid}");
                return existing;
            }

            Directory.CreateDirectory(Path.GetDirectoryName(_descriptorPath)!);
            await using var launchLock = await AcquireLaunchLockAsync(effectiveToken);

            // Another WinUI instance may have started the shared control plane
            // while this instance was waiting for the inter-process launch lock.
            existing = await TryReadDescriptorAsync(effectiveToken);
            if (existing is not null && await IsHealthyAsync(existing, effectiveToken))
            {
                _descriptor = existing;
                SetState(ControlPlaneState.Ready, $"控制面已连接 · PID {existing.Pid}");
                return existing;
            }

            SetState(ControlPlaneState.Starting, "正在启动本地 Python 控制面…");
            effectiveToken.ThrowIfCancellationRequested();
            StartOwnedProcess(ControlPlaneLaunch.Resolve(AppContext.BaseDirectory,
                Environment.GetEnvironmentVariable("ABAQUS_TOOLS_ROOT"),
                Environment.GetEnvironmentVariable("ABAQUS_TOOLS_PYTHON")));

            var ready = await WaitForReadyDescriptorAsync(TimeSpan.FromSeconds(25), effectiveToken);
            _descriptor = ready;
            _ownedInstanceId = ready.InstanceId;
            SetState(ControlPlaneState.Ready, $"控制面已就绪 · PID {ready.Pid} · 端口 {ready.Port}");
            return ready;
        }
        catch (OperationCanceledException) when (_shutdownSource.IsCancellationRequested)
        {
            StopOwnedProcess();
            SetState(ControlPlaneState.Disconnected, "控制面正在关闭");
            throw;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            StopOwnedProcess();
            SetState(ControlPlaneState.Disconnected, "控制面连接已取消");
            throw;
        }
        catch (Exception exception)
        {
            StopOwnedProcess();
            var wrapped = exception as ControlPlaneException
                ?? new ControlPlaneException("无法连接本地控制面。" + Environment.NewLine + exception.Message, innerException: exception);
            SetState(ControlPlaneState.Error, wrapped.ToDisplayMessage(), wrapped);
            throw wrapped;
        }
        finally
        {
            _connectionGate.Release();
        }
    }

    public async Task<OdbDiscoveryResponse> DiscoverOdbsAsync(
        string root,
        bool recursive = true,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(root))
        {
            throw new ArgumentException("请选择或输入 ODB 根目录。", nameof(root));
        }

        var descriptor = await EnsureReadyAsync(cancellationToken);
        var endpoint = BuildEndpoint(descriptor, "/api/v1/odb-discoveries");
        var requestBody = JsonSerializer.SerializeToUtf8Bytes(
            new OdbDiscoveryRequest
            {
                Root = root.Trim(),
                Recursive = recursive,
            },
            JsonOptions);
        using var request = new HttpRequestMessage(HttpMethod.Post, endpoint)
        {
            Content = new ByteArrayContent(requestBody),
        };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json")
        {
            CharSet = "utf-8",
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", descriptor.Token);

        HttpResponseMessage response;
        try
        {
            response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken);
        }
        catch (HttpRequestException exception)
        {
            _descriptor = null;
            var wrapped = new ControlPlaneException(
                "本地控制面连接已中断。",
                code: "CONTROL_PLANE_DISCONNECTED",
                retryable: true,
                innerException: exception);
            SetState(ControlPlaneState.Error, wrapped.ToDisplayMessage(), wrapped);
            throw wrapped;
        }

        using (response)
        {
            var payload = await response.Content.ReadAsStringAsync(cancellationToken);
            if (!response.IsSuccessStatusCode)
            {
                throw CreateApiException(response.StatusCode, payload);
            }

            OdbDiscoveryResponse? discovery;
            try
            {
                discovery = JsonSerializer.Deserialize<OdbDiscoveryResponse>(payload, JsonOptions);
            }
            catch (JsonException exception)
            {
                throw new ControlPlaneException("控制面返回了无法解析的 ODB 发现结果。", innerException: exception);
            }

            if (discovery is null || discovery.SchemaVersion != 1)
            {
                throw new ControlPlaneException("控制面返回了不受支持的 ODB 发现协议版本。");
            }

            return discovery;
        }
    }

    public async Task<OdbCompatibilityOperationSnapshot> StartOdbCompatibilityCheckAsync(
        string root,
        IReadOnlyCollection<string> paths,
        bool forceRescan,
        Guid clientRequestId,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(root))
        {
            throw new ArgumentException("请选择或输入 ODB 根目录。", nameof(root));
        }

        var requestedPaths = paths
            .Where(path => !string.IsNullOrWhiteSpace(path))
            .Select(path => path.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (requestedPaths.Length == 0)
        {
            throw new ArgumentException("请至少选择一个要检查的 ODB。", nameof(paths));
        }

        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var effectiveToken = effectiveSource.Token;
        await _operationCreationGate.WaitAsync(effectiveToken);
        try
        {
            lock (_operationGate)
            {
                if (!_acceptNewOperations)
                {
                    throw new OperationCanceledException("应用正在关闭，无法创建兼容性检查。");
                }
            }

            var descriptor = await EnsureReadyAsync(effectiveToken);
            var snapshot = await SendOperationRequestAsync(
                descriptor,
                HttpMethod.Post,
                "/api/v1/odb-compatibility-checks",
                new OdbCompatibilityCheckRequest
                {
                    ClientRequestId = clientRequestId.ToString("D"),
                    Root = root.Trim(),
                    Paths = requestedPaths,
                    ForceRescan = forceRescan,
                },
                "兼容性检查创建响应",
                effectiveToken);
            ValidateOperationSnapshot(snapshot);
            if (!UpdateActiveOperationTracking(snapshot) && !snapshot.IsTerminal)
            {
                using var cancellationTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                await BestEffortCancelOperationAsync(
                    descriptor,
                    snapshot.OperationId,
                    cancellationTimeout.Token);
                throw new OperationCanceledException("应用正在关闭，兼容性检查已取消。", effectiveToken);
            }

            return snapshot;
        }
        finally
        {
            _operationCreationGate.Release();
        }
    }

    public async Task<OdbCompatibilityOperationSnapshot> GetOperationAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var effectiveToken = effectiveSource.Token;
        var descriptor = await EnsureReadyAsync(effectiveToken);
        var snapshot = await SendOperationRequestAsync(
            descriptor,
            HttpMethod.Get,
            $"/api/v1/operations/{Uri.EscapeDataString(operationId)}",
            requestBody: null,
            "操作快照",
            effectiveToken);
        ValidateOperationSnapshot(snapshot, operationId);
        UpdateActiveOperationTracking(snapshot);
        return snapshot;
    }

    public async Task<OdbOperationListResponse> ListOperationsAsync(
        bool activeOnly = false,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var effectiveToken = effectiveSource.Token;
        var descriptor = await EnsureReadyAsync(effectiveToken);
        var relativePath = activeOnly
            ? "/api/v1/operations?activeOnly=true"
            : "/api/v1/operations";
        var response = await SendJsonRequestAsync<OdbOperationListResponse>(
            descriptor,
            HttpMethod.Get,
            relativePath,
            requestBody: null,
            "操作列表",
            effectiveToken);
        ValidateOperationListResponse(response, activeOnly);
        foreach (var snapshot in response.Operations)
        {
            UpdateActiveOperationTracking(snapshot);
        }

        return response;
    }

    public async Task<ResultScopesResponse> DiscoverResultScopesAsync(
        string root,
        bool includeInternal = false,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(root))
        {
            throw new ArgumentException("请选择或输入结果根目录。", nameof(root));
        }

        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<ResultScopesResponse>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/result-scopes",
            new ResultScopesRequest
            {
                Root = root.Trim(),
                IncludeInternal = includeInternal,
            },
            "结果范围",
            effectiveSource.Token);
        ValidateResultScopesResponse(response);
        return response;
    }

    public async Task<LocalJobDraftPreviewResponse> PreviewLocalJobDraftAsync(
        string inpFile,
        string jobName,
        int cpus,
        string memoryValue,
        string memoryUnit,
        string oldjobPath,
        string fortranPath,
        bool interactive,
        bool datacheck,
        bool notify,
        string abaqusCommand,
        int priority,
        int maxParallel,
        bool useSsdCalculation,
        string calculationRootDir,
        string archiveDir,
        CancellationToken cancellationToken = default,
        ExecutionOptionsValues? executionOptions = null)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(15));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<LocalJobDraftPreviewResponse>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/local-job-draft-previews",
            new LocalJobDraftPreviewRequest
            {
                InpFile = inpFile.Trim(),
                JobName = jobName.Trim(),
                Cpus = cpus,
                GpuCount = executionOptions?.GpuCount,
                ExplicitPrecision = executionOptions?.ExplicitPrecision ?? "default",
                OutputPrecision = executionOptions?.OutputPrecision ?? "default",
                MemoryValue = memoryValue.Trim(),
                MemoryUnit = memoryUnit.Trim(),
                OldjobPath = oldjobPath.Trim(),
                FortranPath = fortranPath.Trim(),
                Interactive = interactive,
                Datacheck = datacheck,
                Notify = notify,
                AbaqusCommand = abaqusCommand.Trim(),
                Priority = priority,
                MaxParallel = maxParallel,
                UseSsdCalculation = useSsdCalculation,
                CalculationRootDir = calculationRootDir.Trim(),
                ArchiveDir = archiveDir.Trim(),
            },
            "本机作业草稿预览",
            effectiveSource.Token);
        if (response.SchemaVersion != 1)
        {
            throw new ControlPlaneException("控制面返回了不受支持的作业草稿协议版本。");
        }

        return response;
    }

    public async Task<LocalResourceSnapshot> GetLocalResourceAsync(
        CancellationToken cancellationToken = default, string? abaqusCommand = null)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<LocalResourceSnapshot>(
            descriptor,
            HttpMethod.Get,
            "/api/v1/local-resources" + (abaqusCommand is null ? "" : "?abaqusCommand=" + Uri.EscapeDataString(abaqusCommand)),
            requestBody: null,
            "本机资源快照",
            effectiveSource.Token);
        if (response.SchemaVersion != 1
            || !string.Equals(response.ResourceId, "local", StringComparison.Ordinal)
            || response.LogicalCpus < 1
            || response.MemoryTotalBytes < 1)
        {
            throw new ControlPlaneException("控制面返回了无效的本机资源快照。");
        }

        return response;
    }

    public async Task<RemoteServersSnapshot> GetRemoteServersAsync(
        CancellationToken cancellationToken = default)
    {
        var response = await ReadRemoteStateAsync<RemoteServersSnapshot>(
            "/api/v1/remote-servers", "远端连接状态", cancellationToken);
        ValidateRemoteServersSnapshot(response);
        return response;
    }

    public Task<RemoteServersSnapshot> SaveRemoteServerProfileAsync(
        RemoteServerProfile profile,
        CancellationToken cancellationToken = default) =>
        ExecuteRemoteServerCommandAsync(
            new RemoteServerCommandRequest
            {
                Action = "saveProfile",
                Profile = profile,
            },
            cancellationToken);

    public Task<RemoteServersSnapshot> DeleteRemoteServerProfileAsync(
        string profileName,
        CancellationToken cancellationToken = default) =>
        ExecuteRemoteServerCommandAsync(
            new RemoteServerCommandRequest
            {
                Action = "deleteProfile",
                ProfileName = profileName.Trim(),
            },
            cancellationToken);

    public Task<RemoteServersSnapshot> ConnectRemoteServerAsync(
        RemoteServerProfile profile,
        RemoteServerCredentials credentials,
        string confirmFingerprint = "",
        bool saveProfile = true,
        CancellationToken cancellationToken = default) =>
        ExecuteRemoteServerCommandAsync(
            new RemoteServerCommandRequest
            {
                Action = "connect",
                Profile = profile,
                Credentials = credentials,
                ConfirmFingerprint = string.IsNullOrWhiteSpace(confirmFingerprint)
                    ? null
                    : confirmFingerprint.Trim(),
                SaveProfile = saveProfile,
            },
            cancellationToken,
            timeout: TimeSpan.FromSeconds(40));

    public Task<RemoteServersSnapshot> CancelHostKeyReviewAsync(RemoteServerProfile profile,
        string observedFingerprint, CancellationToken cancellationToken) =>
        ExecuteRemoteServerCommandAsync(new RemoteServerCommandRequest
        {
            Action = "cancelHostKeyReview", Profile = profile, ConfirmFingerprint = observedFingerprint,
        }, cancellationToken);

    public Task<RemoteServersSnapshot> RefreshRemoteServerAsync(
        CancellationToken cancellationToken = default) =>
        ExecuteRemoteServerCommandAsync(
            new RemoteServerCommandRequest { Action = "refresh" },
            cancellationToken,
            timeout: TimeSpan.FromSeconds(30));

    public Task<RemoteServersSnapshot> DisconnectRemoteServerAsync(
        CancellationToken cancellationToken = default) =>
        ExecuteRemoteServerCommandAsync(
            new RemoteServerCommandRequest { Action = "disconnect" },
            cancellationToken);

    public Task<RemoteServersSnapshot> RefreshRemoteServerForProfileAsync(RemoteServerProfile profile,
        CancellationToken cancellationToken = default) => ExecuteRemoteServerCommandAsync(
            new RemoteServerCommandRequest { Action = "refresh", Profile = profile }, cancellationToken,
            timeout: TimeSpan.FromSeconds(30));

    public Task<RemoteServersSnapshot> DisconnectRemoteServerForProfileAsync(RemoteServerProfile profile,
        CancellationToken cancellationToken = default) => ExecuteRemoteServerCommandAsync(
            new RemoteServerCommandRequest { Action = "disconnect", Profile = profile }, cancellationToken);

    private async Task<RemoteServersSnapshot> ExecuteRemoteServerCommandAsync(
        RemoteServerCommandRequest request,
        CancellationToken cancellationToken,
        TimeSpan? timeout = null)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(timeout ?? TimeSpan.FromSeconds(15));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RemoteServersSnapshot>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/remote-server-commands",
            request,
            "远端服务器操作",
            effectiveSource.Token);
        ValidateRemoteServersSnapshot(response);
        return response;
    }

    private static void ValidateRemoteServersSnapshot(RemoteServersSnapshot response)
    {
        if (response.SchemaVersion != 1
            || response.Connection is null
            || response.Profiles is null
            || response.Profiles.Any(profile =>
                string.IsNullOrWhiteSpace(profile.ProfileName)
                || string.IsNullOrWhiteSpace(profile.Host)
                || string.IsNullOrWhiteSpace(profile.Username)
                || profile.Port is < 1 or > 65535))
        {
            throw new ControlPlaneException("控制面返回了无效的远端服务器快照。");
        }
    }

    public async Task<RemoteDirectoryListing> BrowseRemoteDirectoryAsync(
        string path = "",
        CancellationToken cancellationToken = default,
        string? sourceOperationId = null)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(20));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RemoteDirectoryListing>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/remote-file-listings",
            new RemoteDirectoryListingRequest { Path = path.Trim(), SourceOperationId = sourceOperationId },
            "远端目录浏览",
            effectiveSource.Token);
        if (response.SchemaVersion != 1
            || string.IsNullOrWhiteSpace(response.Path)
            || response.Entries.Any(entry =>
                string.IsNullOrWhiteSpace(entry.Name)
                || string.IsNullOrWhiteSpace(entry.Path)
                || entry.Kind is not ("file" or "directory")
                || entry.SizeBytes < 0))
        {
            throw new ControlPlaneException("控制面返回了无效的远端目录列表。");
        }
        return response;
    }

    public async Task<RemoteTransferOperationSnapshot> StartRemoteTransferAsync(
        string direction,
        string source,
        string destination,
        bool overwrite,
        CancellationToken cancellationToken = default,
        string? sourceOperationId = null)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(15));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RemoteTransferOperationSnapshot>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/remote-transfers",
            new RemoteTransferRequest
            {
                SourceOperationId = sourceOperationId,
                ClientRequestId = Guid.NewGuid().ToString("N"),
                Direction = direction,
                Source = source.Trim(),
                Destination = destination.Trim(),
                Overwrite = overwrite,
            },
            "创建远端文件传输",
            effectiveSource.Token);
        ValidateRemoteTransferSnapshot(response);
        return response;
    }

    public async Task<RemoteTransferListSnapshot> GetActiveRemoteTransfersAsync(CancellationToken cancellationToken = default)
    {
        var response = await ReadRemoteStateAsync<RemoteTransferListSnapshot>(
            "/api/v1/remote-transfers?activeOnly=true", "后台传输列表", cancellationToken);
        if (response.SchemaVersion != 1 || response.Operations is null)
            throw new InvalidDataException("后台传输列表无效。");
        foreach (var operation in response.Operations) ValidateRemoteTransferSnapshot(operation);
        return response;
    }

    public async Task<RemoteTransferOperationSnapshot> GetRemoteTransferAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        var response = await ReadRemoteStateAsync<RemoteTransferOperationSnapshot>(
            $"/api/v1/remote-transfers/{Uri.EscapeDataString(ValidateOperationId(operationId))}",
            "远端文件传输状态", cancellationToken);
        ValidateRemoteTransferSnapshot(response, operationId);
        return response;
    }

    private async Task<T> ReadRemoteStateAsync<T>(string path, string label, CancellationToken cancellationToken)
    {
        ControlPlaneDescriptor descriptor;
        using (var readiness = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token))
        {
            // Cold startup already has a 25-second budget. Waiting for it must
            // not consume the shorter HTTP response deadline below.
            readiness.CancelAfter(TimeSpan.FromSeconds(30));
            try { descriptor = await EnsureReadyAsync(readiness.Token); }
            catch (OperationCanceledException error) when (!cancellationToken.IsCancellationRequested && !_shutdownSource.IsCancellationRequested)
            {
                throw new ControlPlaneException("等待本地后台就绪超时，尚未确认远端状态。请刷新状态，勿重复提交任务。",
                    code: "REMOTE_STATE_TIMEOUT", retryable: true, innerException: error);
            }
        }
        using var response = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        response.CancelAfter(TimeSpan.FromSeconds(10));
        try { return await SendJsonRequestAsync<T>(descriptor, HttpMethod.Get, path, null, label, response.Token); }
        catch (OperationCanceledException error) when (!cancellationToken.IsCancellationRequested && !_shutdownSource.IsCancellationRequested)
        {
            throw new ControlPlaneException($"读取{label}超时，尚未确认最新状态。现有任务未被取消，请刷新状态，勿重复提交。",
                code: "REMOTE_STATE_TIMEOUT", retryable: true, innerException: error);
        }
    }

    public async Task<RemoteTransferOperationSnapshot> CancelRemoteTransferAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RemoteTransferOperationSnapshot>(
            descriptor,
            HttpMethod.Post,
            $"/api/v1/remote-transfers/{Uri.EscapeDataString(ValidateOperationId(operationId))}/cancel",
            requestBody: null,
            "取消远端文件传输",
            effectiveSource.Token);
        ValidateRemoteTransferSnapshot(response, operationId);
        return response;
    }

    public async Task<RemoteTransferOperationSnapshot> PollRemoteTransferUntilTerminalAsync(
        string operationId,
        Action<RemoteTransferOperationSnapshot>? progress = null,
        CancellationToken cancellationToken = default)
    {
        while (true)
        {
            var snapshot = await GetRemoteTransferAsync(operationId, cancellationToken);
            progress?.Invoke(snapshot);
            if (snapshot.IsTerminal)
            {
                return snapshot;
            }
            await Task.Delay(350, cancellationToken);
        }
    }

    private static void ValidateRemoteTransferSnapshot(
        RemoteTransferOperationSnapshot response,
        string? expectedOperationId = null)
    {
        if (response.SchemaVersion != 1
            || !string.Equals(response.Kind, "remote.transfer", StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(response.OperationId)
            || (!string.IsNullOrWhiteSpace(expectedOperationId)
                && !string.Equals(response.OperationId, expectedOperationId, StringComparison.Ordinal))
            || response.Status is not (
                "queued" or "running" or "cancelling" or "succeeded" or "failed" or "cancelled")
            || response.Progress.CompletedBytes < 0
            || response.Progress.TotalBytes < 0
            || response.Progress.Percent is < 0 or > 100)
        {
            throw new ControlPlaneException("控制面返回了无效的远端文件传输状态。");
        }
    }

    public async Task<RemoteJobPreview> PreviewRemoteJobAsync(
        RemoteJobRequest request,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(15));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RemoteJobPreview>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/remote-job-previews",
            request,
            "远端作业预览",
            effectiveSource.Token);
        if (response.SchemaVersion != 1
            || !response.Valid
            || string.IsNullOrWhiteSpace(response.ProfileName)
            || string.IsNullOrWhiteSpace(response.Command))
        {
            throw new ControlPlaneException("控制面返回了无效的远端作业预览。");
        }
        return response;
    }

    public async Task<RemoteJobOperationSnapshot> StartRemoteJobAsync(
        RemoteJobRequest request,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(15));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RemoteJobOperationSnapshot>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/remote-jobs",
            request,
            "提交远端作业",
            effectiveSource.Token);
        ValidateRemoteJobSnapshot(response);
        return response;
    }

    public async Task<RemoteJobOperationSnapshot> GetRemoteJobAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RemoteJobOperationSnapshot>(
            descriptor,
            HttpMethod.Get,
            $"/api/v1/remote-jobs/{Uri.EscapeDataString(ValidateOperationId(operationId))}",
            requestBody: null,
            "远端作业状态",
            effectiveSource.Token);
        ValidateRemoteJobSnapshot(response, operationId);
        return response;
    }

    public async Task<RemoteJobListResponse> ListRemoteJobsAsync(
        bool activeOnly = false,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var path = activeOnly ? "/api/v1/remote-jobs?activeOnly=true" : "/api/v1/remote-jobs";
        var response = await SendJsonRequestAsync<RemoteJobListResponse>(
            descriptor,
            HttpMethod.Get,
            path,
            requestBody: null,
            "远端作业列表",
            effectiveSource.Token);
        if (response.SchemaVersion != 1)
        {
            throw new ControlPlaneException("控制面返回了无效的远端作业列表。");
        }
        foreach (var operation in response.Operations)
        {
            ValidateRemoteJobSnapshot(operation);
        }
        return response;
    }

    public async Task<RemoteJobOperationSnapshot> ControlRemoteJobAsync(
        string operationId,
        string action,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RemoteJobOperationSnapshot>(
            descriptor,
            HttpMethod.Post,
            $"/api/v1/remote-jobs/{Uri.EscapeDataString(ValidateOperationId(operationId))}/control",
            new RemoteJobControlRequest { Action = action },
            "远端作业控制",
            effectiveSource.Token);
        ValidateRemoteJobSnapshot(response, operationId);
        return response;
    }

    private static void ValidateRemoteJobSnapshot(
        RemoteJobOperationSnapshot response,
        string? expectedOperationId = null)
    {
        if (response.SchemaVersion != 1
            || !string.Equals(response.Kind, "remote.job", StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(response.OperationId)
            || (!string.IsNullOrWhiteSpace(expectedOperationId)
                && !string.Equals(response.OperationId, expectedOperationId, StringComparison.Ordinal))
            || response.Status is not (
                "queued" or "starting" or "running" or "cancelling" or "succeeded" or "failed" or "cancelled")
            || response.Percent is < 0 or > 100
            || string.IsNullOrWhiteSpace(response.Request.JobName))
        {
            throw new ControlPlaneException("控制面返回了无效的远端作业状态。");
        }
    }

    public async Task<OdbMergeDraftPreviewResponse> PreviewOdbMergeDraftAsync(
        string originalOdb,
        string restartOdb,
        string outputOdb,
        bool includeHistory,
        bool compressResult,
        bool copyOriginal,
        string conflictPolicy,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(15));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<OdbMergeDraftPreviewResponse>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/odb-merge-draft-previews",
            new OdbMergeDraftPreviewRequest
            {
                OriginalOdb = originalOdb.Trim(),
                RestartOdb = restartOdb.Trim(),
                OutputOdb = outputOdb.Trim(),
                IncludeHistory = includeHistory,
                CompressResult = compressResult,
                CopyOriginal = copyOriginal,
                ConflictPolicy = conflictPolicy,
            },
            "ODB 合并草稿预览",
            effectiveSource.Token);
        if (response.SchemaVersion != 1)
        {
            throw new ControlPlaneException("控制面返回了不受支持的 ODB 合并草稿版本。");
        }

        return response;
    }

    public async Task<OdbMergeOperationSnapshot> StartOdbMergeAsync(
        string originalOdb,
        string restartOdb,
        string outputOdb,
        bool includeHistory,
        bool compressResult,
        bool copyOriginal,
        string conflictPolicy,
        Guid clientRequestId,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var effectiveToken = effectiveSource.Token;
        await _operationCreationGate.WaitAsync(effectiveToken);
        try
        {
            lock (_operationGate)
            {
                if (!_acceptNewOperations)
                {
                    throw new OperationCanceledException("应用正在关闭，无法创建 ODB 合并操作。");
                }
            }

            var descriptor = await EnsureReadyAsync(effectiveToken);
            var snapshot = await SendJsonRequestAsync<OdbMergeOperationSnapshot>(
                descriptor,
                HttpMethod.Post,
                "/api/v1/odb-merge-operations",
                new OdbMergeOperationCreateRequest
                {
                    ClientRequestId = clientRequestId.ToString("D"),
                    OriginalOdb = originalOdb.Trim(),
                    RestartOdb = restartOdb.Trim(),
                    OutputOdb = outputOdb.Trim(),
                    IncludeHistory = includeHistory,
                    CompressResult = compressResult,
                    CopyOriginal = copyOriginal,
                    ConflictPolicy = conflictPolicy,
                },
                "ODB 合并创建响应",
                effectiveToken);
            ValidateOdbMergeSnapshot(snapshot);
            if (!UpdateActiveOdbMergeTracking(snapshot) && !snapshot.IsTerminal)
            {
                using var cancellationTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                await BestEffortCancelOdbMergeAsync(
                    descriptor,
                    snapshot.OperationId,
                    cancellationTimeout.Token);
                throw new OperationCanceledException("应用正在关闭，ODB 合并已取消。", effectiveToken);
            }

            return snapshot;
        }
        finally
        {
            _operationCreationGate.Release();
        }
    }

    public async Task<OdbMergeOperationSnapshot> GetOdbMergeOperationAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var snapshot = await SendJsonRequestAsync<OdbMergeOperationSnapshot>(
            descriptor,
            HttpMethod.Get,
            $"/api/v1/odb-merge-operations/{Uri.EscapeDataString(operationId)}",
            requestBody: null,
            "ODB 合并操作快照",
            effectiveSource.Token);
        ValidateOdbMergeSnapshot(snapshot, operationId);
        UpdateActiveOdbMergeTracking(snapshot);
        return snapshot;
    }

    public async Task<OdbMergeOperationSnapshot> CancelOdbMergeOperationAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var snapshot = await SendJsonRequestAsync<OdbMergeOperationSnapshot>(
            descriptor,
            HttpMethod.Post,
            $"/api/v1/odb-merge-operations/{Uri.EscapeDataString(operationId)}/cancel",
            requestBody: null,
            "ODB 合并取消响应",
            effectiveSource.Token);
        ValidateOdbMergeSnapshot(snapshot, operationId);
        UpdateActiveOdbMergeTracking(snapshot);
        return snapshot;
    }

    public async Task<OdbMergeOperationSnapshot> PollOdbMergeUntilTerminalAsync(
        OdbMergeOperationSnapshot initialSnapshot,
        IProgress<OdbMergeOperationSnapshot>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ValidateOdbMergeSnapshot(initialSnapshot);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var snapshot = initialSnapshot;
        while (!snapshot.IsTerminal)
        {
            await Task.Delay(TimeSpan.FromMilliseconds(400), effectiveSource.Token);
            snapshot = await GetOdbMergeOperationAsync(
                snapshot.OperationId,
                effectiveSource.Token);
            progress?.Report(snapshot);
        }

        return snapshot;
    }

    public async Task<OdbMergeOperationListResponse> ListOdbMergeOperationsAsync(
        bool activeOnly = false,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var path = activeOnly
            ? "/api/v1/odb-merge-operations?activeOnly=true"
            : "/api/v1/odb-merge-operations";
        var response = await SendJsonRequestAsync<OdbMergeOperationListResponse>(
            descriptor,
            HttpMethod.Get,
            path,
            requestBody: null,
            "ODB 合并操作列表",
            effectiveSource.Token);
        ValidateOdbMergeListResponse(response, activeOnly);
        foreach (var snapshot in response.Operations)
        {
            UpdateActiveOdbMergeTracking(snapshot);
        }

        return response;
    }

    public async Task<OdbPostprocessOperationSnapshot> StartOdbPostprocessScanAsync(
        string root,
        IReadOnlyList<string> paths,
        int parallelWorkers,
        bool forceRescan,
        Guid clientRequestId,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var effectiveToken = effectiveSource.Token;
        await _operationCreationGate.WaitAsync(effectiveToken);
        try
        {
            lock (_operationGate)
            {
                if (!_acceptNewOperations)
                {
                    throw new OperationCanceledException("应用正在关闭，无法读取 ODB 结构。");
                }
            }

            var descriptor = await EnsureReadyAsync(effectiveToken);
            var snapshot = await SendJsonRequestAsync<OdbPostprocessOperationSnapshot>(
                descriptor,
                HttpMethod.Post,
                "/api/v1/odb-postprocess-scans",
                new OdbPostprocessScanCreateRequest
                {
                    ClientRequestId = clientRequestId.ToString("D"),
                    Root = root.Trim(),
                    Paths = paths,
                    ParallelWorkers = parallelWorkers,
                    ForceRescan = forceRescan,
                },
                "ODB 结构读取创建响应",
                effectiveToken);
            ValidatePostprocessSnapshot(snapshot);
            if (!UpdateActivePostprocessTracking(snapshot) && !snapshot.IsTerminal)
            {
                using var cancellationTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                await BestEffortCancelPostprocessAsync(
                    descriptor,
                    snapshot.OperationId,
                    cancellationTimeout.Token);
                throw new OperationCanceledException("应用正在关闭，ODB 结构读取已取消。", effectiveToken);
            }

            return snapshot;
        }
        finally
        {
            _operationCreationGate.Release();
        }
    }

    public Task<OdbPostprocessOperationSnapshot> StartOdbPostprocessAsync(
        OdbPostprocessRunCreateRequest request,
        CancellationToken cancellationToken = default)
        => StartPostprocessRequestAsync(request, "/api/v1/odb-postprocess-operations", cancellationToken);

    public Task<OdbPostprocessOperationSnapshot> StartOdbRegionExtractionAsync(
        OdbRegionExtractionRequest request,
        CancellationToken cancellationToken = default)
        => StartPostprocessRequestAsync(request, "/api/v1/odb-region-extractions", cancellationToken);

    private async Task<OdbPostprocessOperationSnapshot> StartPostprocessRequestAsync(
        object request, string endpoint, CancellationToken cancellationToken)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var effectiveToken = effectiveSource.Token;
        await _operationCreationGate.WaitAsync(effectiveToken);
        try
        {
            lock (_operationGate)
            {
                if (!_acceptNewOperations)
                {
                    throw new OperationCanceledException("应用正在关闭，无法创建 ODB 后处理操作。");
                }
            }

            var descriptor = await EnsureReadyAsync(effectiveToken);
            var snapshot = await SendJsonRequestAsync<OdbPostprocessOperationSnapshot>(
                descriptor,
                HttpMethod.Post,
                endpoint,
                request,
                "ODB 后处理创建响应",
                effectiveToken);
            ValidatePostprocessSnapshot(snapshot);
            if (!UpdateActivePostprocessTracking(snapshot) && !snapshot.IsTerminal)
            {
                using var cancellationTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                await BestEffortCancelPostprocessAsync(
                    descriptor,
                    snapshot.OperationId,
                    cancellationTimeout.Token);
                throw new OperationCanceledException("应用正在关闭，ODB 后处理已取消。", effectiveToken);
            }

            return snapshot;
        }
        finally
        {
            _operationCreationGate.Release();
        }
    }

    public async Task<OdbPostprocessOperationSnapshot> GetOdbPostprocessOperationAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var snapshot = await SendJsonRequestAsync<OdbPostprocessOperationSnapshot>(
            descriptor,
            HttpMethod.Get,
            $"/api/v1/odb-postprocess-operations/{Uri.EscapeDataString(operationId)}",
            requestBody: null,
            "ODB 后处理操作快照",
            effectiveSource.Token);
        ValidatePostprocessSnapshot(snapshot, operationId);
        UpdateActivePostprocessTracking(snapshot);
        return snapshot;
    }

    public async Task<OdbPostprocessOperationSnapshot> CancelOdbPostprocessOperationAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var snapshot = await SendJsonRequestAsync<OdbPostprocessOperationSnapshot>(
            descriptor,
            HttpMethod.Post,
            $"/api/v1/odb-postprocess-operations/{Uri.EscapeDataString(operationId)}/cancel",
            requestBody: null,
            "ODB 后处理取消响应",
            effectiveSource.Token);
        ValidatePostprocessSnapshot(snapshot, operationId);
        UpdateActivePostprocessTracking(snapshot);
        return snapshot;
    }

    public async Task<OdbPostprocessOperationSnapshot> PollOdbPostprocessUntilTerminalAsync(
        OdbPostprocessOperationSnapshot initialSnapshot,
        IProgress<OdbPostprocessOperationSnapshot>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ValidatePostprocessSnapshot(initialSnapshot);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var snapshot = initialSnapshot;
        while (!snapshot.IsTerminal)
        {
            await Task.Delay(TimeSpan.FromMilliseconds(450), effectiveSource.Token);
            snapshot = await GetOdbPostprocessOperationAsync(
                snapshot.OperationId,
                effectiveSource.Token);
            progress?.Report(snapshot);
        }

        return snapshot;
    }

    public async Task<OdbPostprocessOperationListResponse> ListOdbPostprocessOperationsAsync(
        bool activeOnly = false,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var path = activeOnly
            ? "/api/v1/odb-postprocess-operations?activeOnly=true"
            : "/api/v1/odb-postprocess-operations";
        var response = await SendJsonRequestAsync<OdbPostprocessOperationListResponse>(
            descriptor,
            HttpMethod.Get,
            path,
            requestBody: null,
            "ODB 后处理操作列表",
            effectiveSource.Token);
        if (response.SchemaVersion != 1 || response.Operations is null)
        {
            throw new ControlPlaneException("控制面返回了无效的 ODB 后处理操作列表。");
        }

        foreach (var snapshot in response.Operations)
        {
            ValidatePostprocessSnapshot(snapshot);
            UpdateActivePostprocessTracking(snapshot);
        }

        return response;
    }

    public async Task<JobQueueSnapshot> GetJobQueuesAsync(
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<JobQueueSnapshot>(
            descriptor,
            HttpMethod.Get,
            "/api/v1/job-queues",
            requestBody: null,
            "作业队列快照",
            effectiveSource.Token);
        if (response.SchemaVersion != 1
            || response.CandidateCount != response.Candidates.Count
            || response.QueueCount != response.QueueItems.Count)
        {
            throw new ControlPlaneException("控制面返回了无效的作业队列快照。");
        }

        return response;
    }

    public Task<JobQueueCommandResponse> AddJobQueueCandidatesAsync(
        IReadOnlyList<string> paths,
        bool skipRestartNames,
        bool skipExistingResults,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "addCandidates",
                Paths = paths,
                Source = "文件",
                SkipRestartNames = skipRestartNames,
                SkipExistingResults = skipExistingResults,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> ScanJobQueueCandidatesAsync(
        string root,
        bool recursive,
        bool skipRestartNames,
        bool skipExistingResults,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "scanCandidates",
                Root = root.Trim(),
                Recursive = recursive,
                SkipRestartNames = skipRestartNames,
                SkipExistingResults = skipExistingResults,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> ScanExternalJobsAsync(
        string root,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "scanExternalJobs",
                Root = root.Trim(),
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> SetJobQueueCandidateSelectionAsync(
        IReadOnlyList<string> itemIds,
        bool selected,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "setCandidateSelection",
                ItemIds = itemIds,
                Selected = selected,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> InvertJobQueueCandidateSelectionAsync(
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest { Action = "invertCandidateSelection" },
            cancellationToken);

    public Task<JobQueueCommandResponse> RemoveJobQueueCandidatesAsync(
        IReadOnlyList<string> itemIds,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "removeCandidates",
                ItemIds = itemIds,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> ConfirmJobQueueCandidatesAsync(
        IReadOnlyList<string> itemIds,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "confirmCandidates",
                ItemIds = itemIds,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> UpdateJobQueueItemAsync(
        string itemId,
        bool candidate,
        string jobName,
        int cores,
        string memory,
        int priority,
        string oldjobPath,
        string fortranPath,
        CancellationToken cancellationToken = default,
        ExecutionOptionsValues? executionOptions = null,
        string? calculationRootDir = null,
        string? archiveDir = null,
        bool? cleanupAfterArchive = null) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = candidate ? "updateCandidate" : "updateQueueItem",
                ItemId = itemId.Trim(),
                JobName = jobName.Trim(),
                Cores = cores,
                GpuCount = executionOptions is null ? null : JsonSerializer.SerializeToElement(executionOptions.GpuCount),
                ExplicitPrecision = executionOptions?.ExplicitPrecision,
                OutputPrecision = executionOptions?.OutputPrecision,
                Memory = memory.Trim(),
                Priority = priority,
                OldjobPath = oldjobPath.Trim(),
                FortranPath = fortranPath.Trim(),
                CalculationRootDir = calculationRootDir?.Trim(),
                ArchiveDir = archiveDir?.Trim(),
                CleanupAfterArchive = cleanupAfterArchive,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> SetCandidateDirectoriesAsync(
        IReadOnlyList<string> itemIds,
        string? calculationRootDir = null,
        string? archiveDir = null,
        bool? cleanupAfterArchive = null,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(new JobQueueCommandRequest
        {
            Action = "setCandidateDirectories",
            ItemIds = itemIds,
            CalculationRootDir = calculationRootDir?.Trim(),
            ArchiveDir = archiveDir?.Trim(),
            CleanupAfterArchive = cleanupAfterArchive,
        }, cancellationToken);

    public Task<JobQueueCommandResponse> UpdateRestartDependencyAsync(
        string itemId, string oldjobPath, CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(new JobQueueCommandRequest
        {
            Action = "updateQueueItem",
            ItemId = itemId.Trim(),
            OldjobPath = oldjobPath.Trim(),
        }, cancellationToken);

    public Task<JobQueueCommandResponse> SetJobQueueHoldAsync(
        IReadOnlyList<string> itemIds,
        bool held,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "setQueueHold",
                ItemIds = itemIds,
                Held = held,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> RequeueJobQueueItemsAsync(
        IReadOnlyList<string> itemIds,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "requeueQueueItems",
                ItemIds = itemIds,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> RemoveJobQueueItemsAsync(
        IReadOnlyList<string> itemIds,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "removeQueueItems",
                ItemIds = itemIds,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> ClearFinishedJobQueueItemsAsync(
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest { Action = "clearFinished" },
            cancellationToken);

    public Task<JobQueueCommandResponse> MoveJobQueueItemAsync(
        string itemId,
        string direction,
        CancellationToken cancellationToken = default) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "moveQueueItem",
                ItemId = itemId.Trim(),
                Direction = direction,
            },
            cancellationToken);

    public Task<JobQueueCommandResponse> EnqueueLocalJobDraftAsync(
        string inpFile,
        string jobName,
        int cpus,
        string memoryValue,
        string memoryUnit,
        string oldjobPath,
        string fortranPath,
        bool interactive,
        bool datacheck,
        bool notify,
        string abaqusCommand,
        int priority,
        int maxParallel,
        bool useSsdCalculation,
        string calculationRootDir,
        string archiveDir,
        CancellationToken cancellationToken = default,
        ExecutionOptionsValues? executionOptions = null) =>
        ExecuteJobQueueCommandAsync(
            new JobQueueCommandRequest
            {
                Action = "enqueueDraft",
                Draft = new LocalJobDraftPreviewRequest
                {
                    InpFile = inpFile.Trim(),
                    JobName = jobName.Trim(),
                    Cpus = cpus,
                    GpuCount = executionOptions?.GpuCount,
                    ExplicitPrecision = executionOptions?.ExplicitPrecision ?? "default",
                    OutputPrecision = executionOptions?.OutputPrecision ?? "default",
                    MemoryValue = memoryValue.Trim(),
                    MemoryUnit = memoryUnit.Trim(),
                    OldjobPath = oldjobPath.Trim(),
                    FortranPath = fortranPath.Trim(),
                    Interactive = interactive,
                    Datacheck = datacheck,
                    Notify = notify,
                    AbaqusCommand = abaqusCommand.Trim(),
                    Priority = priority,
                    MaxParallel = maxParallel,
                    UseSsdCalculation = useSsdCalculation,
                    CalculationRootDir = calculationRootDir.Trim(),
                    ArchiveDir = archiveDir.Trim(),
                },
            },
            cancellationToken);

    private async Task<JobQueueCommandResponse> ExecuteJobQueueCommandAsync(
        JobQueueCommandRequest request,
        CancellationToken cancellationToken)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<JobQueueCommandResponse>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/job-queue-commands",
            request,
            "作业队列操作",
            effectiveSource.Token);
        ValidateJobQueueSnapshot(response.Snapshot);
        if (response.SchemaVersion != 1 || string.IsNullOrWhiteSpace(response.Action))
        {
            throw new ControlPlaneException("控制面返回了无效的作业队列操作结果。");
        }

        return response;
    }

    private static void ValidateJobQueueSnapshot(JobQueueSnapshot response)
    {
        if (response.SchemaVersion != 1
            || response.CandidateCount != response.Candidates.Count
            || response.QueueCount != response.QueueItems.Count)
        {
            throw new ControlPlaneException("控制面返回了无效的作业队列快照。");
        }
    }

    public async Task<LocalQueueRuntimeSnapshot> GetLocalQueueRuntimeAsync(
        CancellationToken cancellationToken = default, bool deferIfBusy = false)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<LocalQueueRuntimeSnapshot>(
            descriptor,
            HttpMethod.Get,
            "/api/v1/local-queue-runtime",
            requestBody: null,
            "本机队列运行状态",
            effectiveSource.Token,
            preferNoWait: deferIfBusy);
        if (deferIfBusy && response.SchemaVersion == 1 && response.RefreshPending)
            return response;
        ValidateLocalQueueRuntime(response);
        return response;
    }

    public Task<LocalQueueRuntimeSnapshot> StartLocalQueueAsync(
        int maxParallel,
        string existingResultPolicy,
        CancellationToken cancellationToken = default) =>
        ControlLocalQueueAsync(
            new LocalQueueControlRequest
            {
                Action = "start",
                MaxParallel = maxParallel,
                ExistingResultPolicy = existingResultPolicy,
            },
            cancellationToken);

    public Task<LocalQueueRuntimeSnapshot> StopLocalQueueAsync(
        CancellationToken cancellationToken = default) =>
        ControlLocalQueueAsync(
            new LocalQueueControlRequest { Action = "stop" },
            cancellationToken);

    public Task<LocalQueueRuntimeSnapshot> TerminateLocalQueueItemsAsync(
        IReadOnlyList<string> itemIds,
        CancellationToken cancellationToken = default) =>
        ControlLocalQueueAsync(
            new LocalQueueControlRequest
            {
                Action = "terminate",
                ItemIds = itemIds,
            },
            cancellationToken);

    public Task<LocalQueueRuntimeSnapshot> SetLocalQueueItemsPausedAsync(
        IReadOnlyList<string> itemIds,
        bool paused,
        CancellationToken cancellationToken = default) =>
        ControlLocalQueueAsync(
            new LocalQueueControlRequest
            {
                Action = paused ? "suspend" : "resume",
                ItemIds = itemIds,
            },
            cancellationToken);

    public Task<LocalQueueRuntimeSnapshot> RetryLocalArchiveAsync(
        string itemId, CancellationToken cancellationToken = default) =>
        ControlLocalQueueAsync(new LocalQueueControlRequest { Action = "retryArchive", ItemIds = [itemId] }, cancellationToken);

    private async Task<LocalQueueRuntimeSnapshot> ControlLocalQueueAsync(
        LocalQueueControlRequest request,
        CancellationToken cancellationToken)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<LocalQueueRuntimeSnapshot>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/local-queue-controls",
            request,
            "本机队列控制",
            effectiveSource.Token);
        ValidateLocalQueueRuntime(response);
        return response;
    }

    private static void ValidateLocalQueueRuntime(LocalQueueRuntimeSnapshot response)
    {
        ValidateJobQueueSnapshot(response.Queue);
        if (response.SchemaVersion != 1 || response.RefreshPending
            || response.MaxParallel < 1
            || response.Operations.Any(operation => string.IsNullOrWhiteSpace(operation.ItemId)))
        {
            throw new ControlPlaneException("控制面返回了无效的本机队列运行状态。");
        }
    }

    public async Task<RestartChainSnapshot> GetRestartChainsAsync(
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RestartChainSnapshot>(
            descriptor,
            HttpMethod.Get,
            "/api/v1/restart-chains",
            requestBody: null,
            "重启动依赖链",
            effectiveSource.Token);
        if (response.SchemaVersion != 1
            || response.NodeCount != response.Nodes.Count
            || response.GraphNodeCount != response.GraphNodes.Count)
        {
            throw new ControlPlaneException("控制面返回了无效的重启动依赖链。");
        }

        return response;
    }

    public async Task<RestartResultPlan> CreateRestartResultPlanAsync(
        string itemId,
        string outputDirectory = "",
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(10));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<RestartResultPlan>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/restart-result-plans",
            new RestartResultPlanRequest
            {
                ItemId = itemId.Trim(),
                OutputDirectory = outputDirectory.Trim(),
            },
            "重启动完整结果计划",
            effectiveSource.Token);
        if (response.SchemaVersion != 1
            || !string.Equals(
                response.PlanKind,
                "restart-result-materialization",
                StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(response.TargetJobId)
            || (response.Valid && response.Steps.Count == 0))
        {
            throw new ControlPlaneException("控制面返回了无效的完整结果计划。");
        }

        return response;
    }

    public Task<OdbResultGraphSnapshot> GetOdbResultGraphAsync(
        CancellationToken cancellationToken = default) =>
        SendResultGraphRequestAsync<OdbResultGraphSnapshot>(
            HttpMethod.Get, "/api/v1/odb-result-graph", null, cancellationToken);

    public Task<OdbResultGraphSnapshot> SaveOdbResultGraphAsync(
        int expectedRevision,
        string outputDirectory,
        IReadOnlyList<OdbResultGraphNode> nodes,
        CancellationToken cancellationToken = default) =>
        SendResultGraphRequestAsync<OdbResultGraphSnapshot>(
            HttpMethod.Post, "/api/v1/odb-result-graph-commands",
            new { SchemaVersion = 1, Action = "save", ExpectedRevision = expectedRevision,
                OutputDirectory = outputDirectory, Nodes = nodes }, cancellationToken);

    public Task<OdbResultBatchPlan> PreviewOdbResultGraphPlansAsync(
        IReadOnlyList<string> targetNodeIds,
        CancellationToken cancellationToken = default) =>
        SendResultGraphRequestAsync<OdbResultBatchPlan>(
            HttpMethod.Post, "/api/v1/odb-result-graph-plans",
            new { SchemaVersion = 1, TargetNodeIds = targetNodeIds }, cancellationToken);

    private async Task<T> SendResultGraphRequestAsync<T>(
        HttpMethod method, string path, object? body, CancellationToken cancellationToken)
    {
        using var source = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, _shutdownSource.Token);
        source.CancelAfter(TimeSpan.FromSeconds(15));
        var descriptor = await EnsureReadyAsync(source.Token);
        return await SendJsonRequestAsync<T>(
            descriptor, method, path, body, "ODB 结果图", source.Token);
    }

    public async Task<ResultRecordsResponse> GetResultRecordsAsync(
        string root,
        string scope,
        string timeDirectory,
        string section,
        string query,
        string useCase,
        bool includeInternal,
        CancellationToken cancellationToken = default,
        int offset = 0,
        string? directDirectory = null,
        ResultDirectPageAnchor? directAnchor = null,
        string? sortBy = null,
        bool sortDescending = false)
    {
        if (string.IsNullOrWhiteSpace(root) || string.IsNullOrWhiteSpace(scope))
        {
            throw new ArgumentException("结果根目录和浏览范围不能为空。");
        }

        var requestedOrder = sortBy is null or "default" ? null : sortBy;
        var descending = requestedOrder is not null && sortDescending;
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<ResultRecordsResponse>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/result-records",
            new ResultRecordsRequest
            {
                Root = root.Trim(),
                Scope = scope.Trim(),
                TimeDirectory = timeDirectory?.Trim() ?? string.Empty,
                DirectDirectory = directDirectory,
                DirectAnchor = directAnchor,
                SortBy = requestedOrder,
                SortDescending = descending,
                Section = string.IsNullOrWhiteSpace(section) ? "all" : section.Trim(),
                Query = query?.Trim() ?? string.Empty,
                UseCase = useCase?.Trim() ?? string.Empty,
                IncludeInternal = includeInternal,
                Offset = offset,
            },
            "结果记录",
            effectiveSource.Token);
        ValidateResultRecordsResponse(response);
        if (response.SortBy != (requestedOrder ?? "default") || response.SortDescending != descending
            || (directDirectory is not null && requestedOrder is not null && response.Records.Count > 0
                && (string.IsNullOrEmpty(response.Records[0].SortAnchor)
                    || string.IsNullOrEmpty(response.Records[^1].SortAnchor))))
            throw new ControlPlaneException("返回的结果排序与请求不一致，请重新读取目录。");
        if (directDirectory is not null && (response.Source != "direct"
            || !StringComparer.OrdinalIgnoreCase.Equals(response.DirectDirectory, directDirectory)
            || !StringComparer.OrdinalIgnoreCase.Equals(response.Scope, scope)
            || !StringComparer.OrdinalIgnoreCase.Equals(response.Root, root)
            || response.Records.Any(record => !StringComparer.OrdinalIgnoreCase.Equals(
                Path.GetDirectoryName(record.Path), directDirectory))))
            throw new ControlPlaneException("结果记录不属于请求的直接浏览目录，请重新读取目录。");
        var pageEnd = (long)response.Offset + response.Records.Count;
        var partialFirstPage = directAnchor?.Direction == "before" && response.Offset == 0;
        if ((directAnchor is null && response.Offset != offset) || response.Records.Count > response.Limit ||
            ((directAnchor is not null || response.Records.Count > 0) && pageEnd > response.FilteredCount) ||
            response.HasMore != (pageEnd < response.FilteredCount) ||
            (response.HasMore && response.Records.Count != response.Limit && !partialFirstPage))
        {
            throw new ControlPlaneException("结果列表分页响应不一致，请重新读取目录。");
        }
        return response;
    }

    public async Task<ResultPreviewResponse> GetResultPreviewAsync(
        string root,
        string path,
        int? maxRows = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(root) || string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("结果根目录和预览文件不能为空。");
        }

        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var response = await SendJsonRequestAsync<ResultPreviewResponse>(
            descriptor,
            HttpMethod.Post,
            "/api/v1/result-previews",
            new ResultPreviewRequest
            {
                Root = root.Trim(),
                Path = path.Trim(),
                MaxRows = maxRows is int count ? Math.Clamp(count, 1, 100) : null,
            },
            "结果预览",
            effectiveSource.Token);
        ValidateResultPreviewResponse(response, path);
        return response;
    }

    public async Task<ResultIndexOperationSnapshot> StartResultIndexBuildAsync(
        string root,
        string timeDirectory,
        Guid clientRequestId,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(root) || string.IsNullOrWhiteSpace(timeDirectory))
        {
            throw new ArgumentException("结果根目录和时间目录不能为空。");
        }

        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        effectiveSource.CancelAfter(TimeSpan.FromSeconds(30));
        var effectiveToken = effectiveSource.Token;
        await _operationCreationGate.WaitAsync(effectiveToken);
        try
        {
            lock (_operationGate)
            {
                if (!_acceptNewOperations)
                {
                    throw new OperationCanceledException("应用正在关闭，无法创建结果索引。");
                }
            }

            var descriptor = await EnsureReadyAsync(effectiveToken);
            var snapshot = await SendJsonRequestAsync<ResultIndexOperationSnapshot>(
                descriptor,
                HttpMethod.Post,
                "/api/v1/result-index-builds",
                new ResultIndexBuildRequest
                {
                    ClientRequestId = clientRequestId.ToString("D"),
                    Root = root.Trim(),
                    TimeDirectory = timeDirectory.Trim(),
                },
                "结果索引创建响应",
                effectiveToken);
            ValidateResultIndexSnapshot(snapshot);
            if (!UpdateActiveResultIndexTracking(snapshot) && !snapshot.IsTerminal)
            {
                using var cancellationTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                await BestEffortCancelResultIndexAsync(
                    descriptor,
                    snapshot.OperationId,
                    cancellationTimeout.Token);
                throw new OperationCanceledException("应用正在关闭，结果索引已取消。", effectiveToken);
            }

            return snapshot;
        }
        finally
        {
            _operationCreationGate.Release();
        }
    }

    public async Task<ResultIndexOperationSnapshot> GetResultIndexOperationAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var snapshot = await SendJsonRequestAsync<ResultIndexOperationSnapshot>(
            descriptor,
            HttpMethod.Get,
            $"/api/v1/result-index-builds/{Uri.EscapeDataString(operationId)}",
            requestBody: null,
            "结果索引操作快照",
            effectiveSource.Token);
        ValidateResultIndexSnapshot(snapshot, operationId);
        UpdateActiveResultIndexTracking(snapshot);
        return snapshot;
    }

    public async Task<ResultIndexOperationSnapshot> CancelResultIndexOperationAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var snapshot = await SendJsonRequestAsync<ResultIndexOperationSnapshot>(
            descriptor,
            HttpMethod.Post,
            $"/api/v1/result-index-builds/{Uri.EscapeDataString(operationId)}/cancel",
            requestBody: null,
            "结果索引取消响应",
            effectiveSource.Token);
        ValidateResultIndexSnapshot(snapshot, operationId);
        UpdateActiveResultIndexTracking(snapshot);
        return snapshot;
    }

    public async Task<ResultIndexOperationSnapshot> PollResultIndexUntilTerminalAsync(
        ResultIndexOperationSnapshot initialSnapshot,
        IProgress<ResultIndexOperationSnapshot>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ValidateResultIndexSnapshot(initialSnapshot);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var snapshot = initialSnapshot;
        while (!snapshot.IsTerminal)
        {
            await Task.Delay(TimeSpan.FromMilliseconds(400), effectiveSource.Token);
            snapshot = await GetResultIndexOperationAsync(
                snapshot.OperationId,
                effectiveSource.Token);
            progress?.Report(snapshot);
        }

        return snapshot;
    }

    public async Task<ResultIndexOperationListResponse> ListResultIndexOperationsAsync(
        bool activeOnly = false,
        CancellationToken cancellationToken = default)
    {
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var descriptor = await EnsureReadyAsync(effectiveSource.Token);
        var path = activeOnly
            ? "/api/v1/result-index-builds?activeOnly=true"
            : "/api/v1/result-index-builds";
        var response = await SendJsonRequestAsync<ResultIndexOperationListResponse>(
            descriptor,
            HttpMethod.Get,
            path,
            requestBody: null,
            "结果索引操作列表",
            effectiveSource.Token);
        ValidateResultIndexListResponse(response, activeOnly);
        foreach (var snapshot in response.Operations)
        {
            UpdateActiveResultIndexTracking(snapshot);
        }

        return response;
    }

    public async Task<OdbCompatibilityOperationSnapshot> CancelOperationAsync(
        string operationId,
        CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var effectiveToken = effectiveSource.Token;
        var descriptor = await EnsureReadyAsync(effectiveToken);
        var snapshot = await SendOperationRequestAsync(
            descriptor,
            HttpMethod.Post,
            $"/api/v1/operations/{Uri.EscapeDataString(operationId)}/cancel",
            requestBody: null,
            "操作取消响应",
            effectiveToken);
        ValidateOperationSnapshot(snapshot, operationId);
        UpdateActiveOperationTracking(snapshot);
        return snapshot;
    }

    public async Task<OdbCompatibilityOperationSnapshot> PollOperationUntilTerminalAsync(
        OdbCompatibilityOperationSnapshot initialSnapshot,
        IProgress<OdbCompatibilityOperationSnapshot>? progress = null,
        TimeSpan? pollInterval = null,
        CancellationToken cancellationToken = default)
    {
        ValidateOperationSnapshot(initialSnapshot);
        var interval = pollInterval ?? TimeSpan.FromMilliseconds(500);
        if (interval < TimeSpan.FromMilliseconds(100))
        {
            throw new ArgumentOutOfRangeException(
                nameof(pollInterval),
                "轮询间隔不得小于 100 毫秒。");
        }

        using var effectiveSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _shutdownSource.Token);
        var effectiveToken = effectiveSource.Token;
        var snapshot = initialSnapshot;
        while (!snapshot.IsTerminal)
        {
            await Task.Delay(interval, effectiveToken);
            snapshot = await GetOperationAsync(snapshot.OperationId, effectiveToken);
            progress?.Report(snapshot);
        }

        return snapshot;
    }

    private async Task<OdbCompatibilityOperationSnapshot> SendOperationRequestAsync(
        ControlPlaneDescriptor descriptor,
        HttpMethod method,
        string relativePath,
        object? requestBody,
        string responseLabel,
        CancellationToken cancellationToken)
    {
        return await SendJsonRequestAsync<OdbCompatibilityOperationSnapshot>(
            descriptor,
            method,
            relativePath,
            requestBody,
            responseLabel,
            cancellationToken);
    }

    private async Task<T> SendJsonRequestAsync<T>(
        ControlPlaneDescriptor descriptor,
        HttpMethod method,
        string relativePath,
        object? requestBody,
        string responseLabel,
        CancellationToken cancellationToken,
        bool preferNoWait = false)
    {
        if (requestBody is LocalJobDraftPreviewRequest or RemoteJobRequest
            || requestBody is JobQueueCommandRequest command && (command.Draft is not null
                || command.GpuCount.HasValue || command.ExplicitPrecision is not null || command.OutputPrecision is not null))
        {
            var health = await SendJsonRequestAsync<HealthResponse>(descriptor, HttpMethod.Get, "/healthz", null,
                "提交参数能力", cancellationToken);
            if (health.SchemaVersion != 1 || health.InstanceId != descriptor.InstanceId
                || health.Capabilities?.Contains("job.execution-options-v1", StringComparer.Ordinal) != true)
                throw new ControlPlaneException("当前连接的后台版本不支持这组提交参数。请先让现有作业安全结束并正常关闭旧后台，再启动新版；没有提交或更改作业。",
                    code: "EXECUTION_OPTIONS_UNSUPPORTED");
        }
        using var request = new HttpRequestMessage(method, BuildEndpoint(descriptor, relativePath));
        if (preferNoWait)
            request.Headers.Add("Prefer", "wait=0");
        if (requestBody is not null)
        {
            request.Content = new ByteArrayContent(
                JsonSerializer.SerializeToUtf8Bytes(requestBody, JsonOptions));
            request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json")
            {
                CharSet = "utf-8",
            };
        }

        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", descriptor.Token);
        HttpResponseMessage response;
        try
        {
            response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken);
        }
        catch (HttpRequestException exception)
        {
            _descriptor = null;
            var wrapped = new ControlPlaneException(
                "本地控制面连接已中断。",
                code: "CONTROL_PLANE_DISCONNECTED",
                retryable: true,
                innerException: exception);
            SetState(ControlPlaneState.Error, wrapped.ToDisplayMessage(), wrapped);
            throw wrapped;
        }

        using (response)
        {
            var payload = await response.Content.ReadAsStringAsync(cancellationToken);
            if (!response.IsSuccessStatusCode)
            {
                throw CreateApiException(response.StatusCode, payload);
            }

            try
            {
                return JsonSerializer.Deserialize<T>(
                        payload,
                        JsonOptions)
                    ?? throw new ControlPlaneException($"控制面返回了空的{responseLabel}。");
            }
            catch (JsonException exception)
            {
                throw new ControlPlaneException(
                    $"控制面返回了无法解析的{responseLabel}。",
                    innerException: exception);
            }
        }
    }

    private async Task<ControlPlaneDescriptor> WaitForReadyDescriptorAsync(
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutSource.CancelAfter(timeout);

        try
        {
            while (!timeoutSource.IsCancellationRequested)
            {
                if (_ownedProcess is { HasExited: true } process)
                {
                    throw new ControlPlaneException(
                        $"Python 控制面提前退出（退出码 {process.ExitCode}）。{GetProcessDiagnosticTail()}");
                }

                var candidate = await TryReadDescriptorAsync(timeoutSource.Token);
                if (candidate is null)
                {
                    RecordReadinessProbe("descriptor 不存在、不可读或结构无效");
                }
                else if (_ownedProcess is null)
                {
                    RecordReadinessProbe($"descriptor PID {candidate.Pid} 已出现，但宿主没有自有进程");
                }
                else if (string.IsNullOrWhiteSpace(_ownedLaunchToken)
                    || !string.Equals(
                        candidate.LaunchToken,
                        _ownedLaunchToken,
                        StringComparison.Ordinal))
                {
                    RecordReadinessProbe(
                        $"descriptor launchToken 与本次冷启动不一致（PID {candidate.Pid}）");
                }
                else if (await IsHealthyAsync(candidate, timeoutSource.Token))
                {
                    _ownedInstanceId = candidate.InstanceId;
                    return candidate;
                }

                await Task.Delay(150, timeoutSource.Token);
            }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // The local readiness deadline elapsed; report the bounded diagnostic below.
        }

        cancellationToken.ThrowIfCancellationRequested();
        throw new ControlPlaneException(
            $"等待 Python 控制面就绪超时。descriptor：{_descriptorPath}{Environment.NewLine}{_lastReadinessDiagnostic}{GetProcessDiagnosticTail()}",
            retryable: true);
    }

    private async Task<FileStream> AcquireLaunchLockAsync(CancellationToken cancellationToken)
    {
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                return new FileStream(
                    _launchLockPath,
                    FileMode.OpenOrCreate,
                    FileAccess.ReadWrite,
                    FileShare.None,
                    bufferSize: 1,
                    FileOptions.Asynchronous);
            }
            catch (IOException)
            {
                await Task.Delay(100, cancellationToken);
            }
        }
    }

    private async Task<ControlPlaneDescriptor?> TryReadDescriptorAsync(CancellationToken cancellationToken)
    {
        try
        {
            await using var stream = new FileStream(
                _descriptorPath,
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete,
                bufferSize: 4096,
                FileOptions.Asynchronous | FileOptions.SequentialScan);
            var descriptor = await JsonSerializer.DeserializeAsync<ControlPlaneDescriptor>(
                stream,
                JsonOptions,
                cancellationToken);
            return descriptor is not null && IsValidDescriptor(descriptor) ? descriptor : null;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            return null;
        }
    }

    private async Task<bool> IsHealthyAsync(
        ControlPlaneDescriptor descriptor,
        CancellationToken cancellationToken)
    {
        if (!IsValidDescriptor(descriptor))
        {
            RecordReadinessProbe("descriptor 结构未通过 IsValidDescriptor");
            return false;
        }

        try
        {
            using var healthTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            healthTimeout.CancelAfter(TimeSpan.FromSeconds(2));
            using var request = new HttpRequestMessage(HttpMethod.Get, BuildEndpoint(descriptor, "/healthz"));
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", descriptor.Token);
            using var response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                healthTimeout.Token);
            if (!response.IsSuccessStatusCode)
            {
                RecordReadinessProbe($"healthz 返回 HTTP {(int)response.StatusCode} {response.StatusCode}");
                return false;
            }

            await using var stream = await response.Content.ReadAsStreamAsync(healthTimeout.Token);
            var health = await JsonSerializer.DeserializeAsync<HealthResponse>(stream, JsonOptions, healthTimeout.Token);
            var healthy = health is not null
                && health.SchemaVersion == 1
                && string.Equals(health.ApiVersion, "v1", StringComparison.Ordinal)
                && string.Equals(health.Status, "ok", StringComparison.OrdinalIgnoreCase)
                && health.Capabilities.Contains("jobQueue.scanExternalJobs", StringComparer.Ordinal)
                && health.Capabilities.Contains("odb.resultGraph", StringComparer.Ordinal)
                && string.Equals(health.InstanceId, descriptor.InstanceId, StringComparison.Ordinal);
            RecordReadinessProbe(
                healthy
                    ? $"healthz 验证成功，instance {descriptor.InstanceId}"
                    : $"healthz JSON 校验失败：schema={health?.SchemaVersion}, api={health?.ApiVersion}, status={health?.Status}, capabilities={string.Join(',', health?.Capabilities ?? [])}, instance={health?.InstanceId}, expected={descriptor.InstanceId}");
            return healthy;
        }
        catch (Exception exception) when (exception is HttpRequestException or IOException or JsonException or OperationCanceledException)
        {
            RecordReadinessProbe($"healthz 异常 {exception.GetType().Name}: {exception.Message}");
            return false;
        }
    }

    private void RecordReadinessProbe(string message)
    {
        _lastReadinessDiagnostic = message;
    }

    private void StartOwnedProcess(ControlPlaneLaunch launch)
    {
        if (_ownedProcess is { HasExited: false })
        {
            return;
        }

        _ownedProcess?.Dispose();
        _ownedProcess = null;
        _ownedInstanceId = null;
        _ownedLaunchToken = Guid.NewGuid().ToString("N");
        lock (_processOutputGate)
        {
            _processOutput.Clear();
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = launch.Executable,
            WorkingDirectory = launch.Root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        if (!launch.Bundled)
        {
            startInfo.ArgumentList.Add("-m");
            startInfo.ArgumentList.Add("modules.control_plane");
        }
        startInfo.ArgumentList.Add("--port");
        startInfo.ArgumentList.Add("0");
        startInfo.ArgumentList.Add("--descriptor");
        startInfo.ArgumentList.Add(_descriptorPath);
        startInfo.Environment["PYTHONUTF8"] = "1";
        startInfo.Environment["PYTHONUNBUFFERED"] = "1";
        startInfo.Environment["ABAQUS_TOOLS_LAUNCH_TOKEN"] = _ownedLaunchToken;

        var process = new Process
        {
            StartInfo = startInfo,
            EnableRaisingEvents = true,
        };
        process.OutputDataReceived += OnProcessOutput;
        process.ErrorDataReceived += OnProcessOutput;
        process.Exited += OnOwnedProcessExited;
        try
        {
            if (!process.Start())
            {
                throw new ControlPlaneException("操作系统拒绝启动 Python 控制面进程。");
            }

            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            _ownedProcess = process;
        }
        catch
        {
            process.OutputDataReceived -= OnProcessOutput;
            process.ErrorDataReceived -= OnProcessOutput;
            process.Exited -= OnOwnedProcessExited;
            process.Dispose();
            _ownedLaunchToken = null;
            throw;
        }
    }

    private void OnOwnedProcessExited(object? sender, EventArgs args)
    {
        if (sender is not Process process
            || !ReferenceEquals(_ownedProcess, process)
            || _shutdownSource.IsCancellationRequested)
        {
            return;
        }

        var ownedPid = 0;
        var exitCode = -1;
        try
        {
            ownedPid = process.Id;
            exitCode = process.ExitCode;
        }
        catch (InvalidOperationException)
        {
            // Preserve the generic disconnected diagnostic below.
        }

        _descriptor = null;
        TryDeleteDescriptorOwnedBy(ownedPid, _ownedInstanceId);
        var exception = new ControlPlaneException(
            $"本地 Python 控制面意外退出（退出码 {exitCode}）。",
            code: "CONTROL_PLANE_EXITED",
            retryable: true);
        SetState(ControlPlaneState.Error, exception.ToDisplayMessage(), exception);
    }

    private void OnProcessOutput(object sender, DataReceivedEventArgs args)
    {
        if (string.IsNullOrWhiteSpace(args.Data))
        {
            return;
        }

        lock (_processOutputGate)
        {
            _processOutput.AppendLine(args.Data);
            const int maximumCharacters = 12_000;
            if (_processOutput.Length > maximumCharacters)
            {
                _processOutput.Remove(0, _processOutput.Length - maximumCharacters);
            }
        }
    }

    private string GetProcessDiagnosticTail()
    {
        lock (_processOutputGate)
        {
            if (_processOutput.Length == 0)
            {
                return string.Empty;
            }

            return Environment.NewLine + "控制面输出：" + Environment.NewLine + _processOutput.ToString().Trim();
        }
    }

    private static bool IsValidDescriptor(ControlPlaneDescriptor descriptor)
    {
        if (descriptor.SchemaVersion != 1
            || !string.Equals(descriptor.ApiVersion, "v1", StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(descriptor.InstanceId)
            || descriptor.Pid <= 0
            || descriptor.Port is < 1 or > 65535
            || string.IsNullOrWhiteSpace(descriptor.Token)
            || !Uri.TryCreate(descriptor.BaseUrl, UriKind.Absolute, out var baseUri)
            || baseUri.Scheme != Uri.UriSchemeHttp
            || !string.Equals(baseUri.Host, "127.0.0.1", StringComparison.Ordinal)
            || baseUri.Port != descriptor.Port
            || !string.Equals(descriptor.Host, "127.0.0.1", StringComparison.Ordinal)
            || !string.Equals(baseUri.Host, descriptor.Host, StringComparison.Ordinal))
        {
            return false;
        }

        return true;
    }

    private static Uri BuildEndpoint(ControlPlaneDescriptor descriptor, string relativePath)
    {
        var baseUri = new Uri(descriptor.BaseUrl.EndsWith('/') ? descriptor.BaseUrl : descriptor.BaseUrl + "/");
        return new Uri(baseUri, relativePath.TrimStart('/'));
    }

    private static ControlPlaneException CreateApiException(HttpStatusCode statusCode, string payload)
    {
        try
        {
            var envelope = JsonSerializer.Deserialize<ErrorEnvelope>(payload, JsonOptions);
            if (envelope is { SchemaVersion: 1, Error: { } error }
                && !string.IsNullOrWhiteSpace(error.Message))
            {
                return new ControlPlaneException(
                    error.Message,
                    error.Code,
                    error.TraceId,
                    error.Retryable,
                    statusCode: (int)statusCode);
            }
        }
        catch (JsonException)
        {
            // Fall through to a bounded protocol-level message.
        }

        var safeStatus = $"{(int)statusCode} {statusCode}";
        return new ControlPlaneException($"控制面请求失败：{safeStatus}。", statusCode: (int)statusCode);
    }

    private static string ValidateOperationId(string operationId)
    {
        if (string.IsNullOrWhiteSpace(operationId))
        {
            throw new ArgumentException("operationId 不能为空。", nameof(operationId));
        }

        return operationId.Trim();
    }

    private static void ValidateOperationSnapshot(
        OdbCompatibilityOperationSnapshot snapshot,
        string? expectedOperationId = null)
    {
        if (snapshot.SchemaVersion != 1)
        {
            throw new ControlPlaneException("控制面返回了不受支持的操作快照结构版本。");
        }

        if (string.IsNullOrWhiteSpace(snapshot.OperationId)
            || (!string.IsNullOrWhiteSpace(expectedOperationId)
                && !string.Equals(
                    snapshot.OperationId,
                    expectedOperationId,
                    StringComparison.Ordinal)))
        {
            throw new ControlPlaneException("控制面返回的 operationId 与请求不一致。");
        }

        if (string.IsNullOrWhiteSpace(snapshot.Kind)
            || !OperationStatuses.Contains(snapshot.Status)
            || snapshot.CreatedAt == default
            || snapshot.UpdatedAt == default
            || snapshot.Version < 1
            || snapshot.EventCursor < 0
            || snapshot.Progress is null
            || snapshot.Progress.Completed < 0
            || snapshot.Progress.Total < 0
            || snapshot.Progress.Completed > snapshot.Progress.Total
            || snapshot.Results is null)
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的操作快照。");
        }

        foreach (var result in snapshot.Results)
        {
            if (string.IsNullOrWhiteSpace(result.Path)
                || !CompatibilityResultStatuses.Contains(result.Status)
                || result.SizeBytes < 0
                || result.StepCount < 0)
            {
                throw new ControlPlaneException("控制面返回了不符合 v1 协议的 ODB 兼容性结果。");
            }
        }
    }

    private static void ValidateResultScopesResponse(ResultScopesResponse response)
    {
        if (response.SchemaVersion != 1
            || string.IsNullOrWhiteSpace(response.Root)
            || response.Nodes is null
            || response.Warnings is null
            || response.Count != response.Nodes.Count
            || response.Nodes.Any(
                node => string.IsNullOrWhiteSpace(node.Path)
                    || string.IsNullOrWhiteSpace(node.Name)
                    || string.IsNullOrWhiteSpace(node.Kind)))
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的结果范围。");
        }
    }

    private static void ValidateResultRecordsResponse(ResultRecordsResponse response)
    {
        if (response.SchemaVersion != 1
            || string.IsNullOrWhiteSpace(response.Root)
            || string.IsNullOrWhiteSpace(response.Scope)
            || response.Records is null
            || response.UseCases is null
            || response.SectionCounts is null
            || response.IndexMetadata is null
            || response.TotalCount < 0
            || response.FilteredCount < 0
            || response.FilteredCount > response.TotalCount
            || response.Offset < 0
            || response.Limit is < 1 or > 500
            || response.Records.Any(
                record => string.IsNullOrWhiteSpace(record.Path)
                    || string.IsNullOrWhiteSpace(record.Name)
                    || record.SizeBytes < -1))
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的结果记录。");
        }
    }

    private static void ValidateResultPreviewResponse(
        ResultPreviewResponse response,
        string expectedPath)
    {
        if (response.SchemaVersion != 1
            || string.IsNullOrWhiteSpace(response.Path)
            || !string.Equals(response.Path, expectedPath, StringComparison.OrdinalIgnoreCase)
            || response.SizeBytes < 0
            || response.Kind is not ("table" or "text" or "image" or "unsupported")
            || response.Headers is null
            || response.Rows is null)
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的结果预览。");
        }
    }

    private static void ValidateResultIndexSnapshot(
        ResultIndexOperationSnapshot snapshot,
        string? expectedOperationId = null)
    {
        if (snapshot.SchemaVersion != 1
            || string.IsNullOrWhiteSpace(snapshot.OperationId)
            || (!string.IsNullOrWhiteSpace(expectedOperationId)
                && !string.Equals(
                    snapshot.OperationId,
                    expectedOperationId,
                    StringComparison.Ordinal))
            || !string.Equals(snapshot.Kind, "result.index.build", StringComparison.Ordinal)
            || !OperationStatuses.Contains(snapshot.Status)
            || snapshot.CreatedAt == default
            || snapshot.UpdatedAt == default
            || snapshot.Version < 1
            || snapshot.EventCursor < 0
            || snapshot.Request is null
            || string.IsNullOrWhiteSpace(snapshot.Request.Root)
            || string.IsNullOrWhiteSpace(snapshot.Request.TimeDirectory)
            || snapshot.Progress is null
            || snapshot.Progress.Processed < 0
            || snapshot.Metadata is null)
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的结果索引快照。");
        }
    }

    private static void ValidateOdbMergeSnapshot(
        OdbMergeOperationSnapshot snapshot,
        string? expectedOperationId = null)
    {
        if (snapshot.SchemaVersion != 1
            || string.IsNullOrWhiteSpace(snapshot.OperationId)
            || (!string.IsNullOrWhiteSpace(expectedOperationId)
                && !string.Equals(
                    snapshot.OperationId,
                    expectedOperationId,
                    StringComparison.Ordinal))
            || !string.Equals(snapshot.Kind, "odb.merge", StringComparison.Ordinal)
            || !OperationStatuses.Contains(snapshot.Status)
            || snapshot.CreatedAt == default
            || snapshot.UpdatedAt == default
            || snapshot.Version < 1
            || snapshot.EventCursor < 0
            || snapshot.Request is null
            || string.IsNullOrWhiteSpace(snapshot.Request.OriginalOdb)
            || string.IsNullOrWhiteSpace(snapshot.Request.RestartOdb)
            || string.IsNullOrWhiteSpace(snapshot.Request.OutputOdb)
            || snapshot.Progress is null
            || snapshot.Progress.Percent is < 0 or > 100
            || snapshot.Logs is null)
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的 ODB 合并快照。");
        }

        if (snapshot.IsSuccessful
            && (snapshot.Result is null
                || string.IsNullOrWhiteSpace(snapshot.Result.OutputOdb)))
        {
            throw new ControlPlaneException("控制面返回的 ODB 合并成功快照缺少结果路径。");
        }
    }

    private static void ValidatePostprocessSnapshot(
        OdbPostprocessOperationSnapshot snapshot,
        string? expectedOperationId = null)
    {
        if (snapshot.SchemaVersion != 1
            || string.IsNullOrWhiteSpace(snapshot.OperationId)
            || (!string.IsNullOrWhiteSpace(expectedOperationId)
                && !string.Equals(
                    snapshot.OperationId,
                    expectedOperationId,
                    StringComparison.Ordinal))
            || snapshot.Kind is not ("odb.postprocess.scan" or "odb.postprocess.run" or "odb.postprocess.region")
            || !OperationStatuses.Contains(snapshot.Status)
            || snapshot.CreatedAt == default
            || snapshot.UpdatedAt == default
            || snapshot.Version < 1
            || snapshot.EventCursor < 0
            || snapshot.Request is null
            || string.IsNullOrWhiteSpace(snapshot.Request.Root)
            || snapshot.Progress is null
            || snapshot.Progress.Percent is < 0 or > 100
            || snapshot.Logs is null)
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的 ODB 后处理快照。");
        }

        if (string.Equals(snapshot.Status, "succeeded", StringComparison.Ordinal)
            && snapshot.Result is null)
        {
            throw new ControlPlaneException("控制面返回的 ODB 后处理成功快照缺少结果。 ");
        }
    }

    private static void ValidateOdbMergeListResponse(
        OdbMergeOperationListResponse response,
        bool activeOnly)
    {
        if (response.SchemaVersion != 1
            || response.EventCursor < 0
            || response.Operations is null)
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的 ODB 合并操作列表。");
        }

        var operationIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var snapshot in response.Operations)
        {
            ValidateOdbMergeSnapshot(snapshot);
            if (!operationIds.Add(snapshot.OperationId)
                || (activeOnly && snapshot.IsTerminal))
            {
                throw new ControlPlaneException("控制面返回了不符合 v1 协议的 ODB 合并操作列表。");
            }
        }
    }

    private static void ValidateResultIndexListResponse(
        ResultIndexOperationListResponse response,
        bool activeOnly)
    {
        if (response.SchemaVersion != 1
            || response.EventCursor < 0
            || response.Operations is null)
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的结果索引操作列表。");
        }

        var operationIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var snapshot in response.Operations)
        {
            ValidateResultIndexSnapshot(snapshot);
            if (!operationIds.Add(snapshot.OperationId)
                || (activeOnly && snapshot.IsTerminal))
            {
                throw new ControlPlaneException("控制面返回了不符合 v1 协议的结果索引操作列表。");
            }
        }
    }

    private static void ValidateOperationListResponse(
        OdbOperationListResponse response,
        bool activeOnly)
    {
        if (response.SchemaVersion != 1
            || response.EventCursor < 0
            || response.Operations is null)
        {
            throw new ControlPlaneException("控制面返回了不符合 v1 协议的操作列表。");
        }

        var operationIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var snapshot in response.Operations)
        {
            ValidateOperationSnapshot(snapshot);
            if (!operationIds.Add(snapshot.OperationId)
                || (activeOnly && snapshot.IsTerminal))
            {
                throw new ControlPlaneException("控制面返回了不符合 v1 协议的操作列表。");
            }
        }
    }

    private bool UpdateActiveOperationTracking(OdbCompatibilityOperationSnapshot snapshot)
    {
        lock (_operationGate)
        {
            if (snapshot.IsTerminal)
            {
                _activeOperationIds.Remove(snapshot.OperationId);
                return true;
            }

            if (!_acceptNewOperations)
            {
                return false;
            }

            _activeOperationIds.Add(snapshot.OperationId);
            return true;
        }
    }

    private bool UpdateActiveResultIndexTracking(ResultIndexOperationSnapshot snapshot)
    {
        lock (_operationGate)
        {
            if (!string.IsNullOrWhiteSpace(snapshot.BatchId))
            {
                if (!snapshot.IsTerminal && _acceptNewOperations) _activeResultIndexBatches.Add(snapshot.BatchId);
                return _acceptNewOperations || snapshot.IsTerminal;
            }
            if (snapshot.IsTerminal)
            {
                _activeResultIndexOperationIds.Remove(snapshot.OperationId);
                return true;
            }

            if (!_acceptNewOperations)
            {
                return false;
            }

            _activeResultIndexOperationIds.Add(snapshot.OperationId);
            return true;
        }
    }

    private bool UpdateActiveOdbMergeTracking(OdbMergeOperationSnapshot snapshot)
    {
        lock (_operationGate)
        {
            if (snapshot.IsTerminal)
            {
                _activeOdbMergeOperationIds.Remove(snapshot.OperationId);
                return true;
            }

            if (!_acceptNewOperations)
            {
                return false;
            }

            _activeOdbMergeOperationIds.Add(snapshot.OperationId);
            return true;
        }
    }

    private bool UpdateActivePostprocessTracking(OdbPostprocessOperationSnapshot snapshot)
    {
        // The queue owns this child. Stopping it independently could dispatch the next group.
        if (snapshot.Request.ClientRequestId.StartsWith("pgq:", StringComparison.Ordinal)) return true;
        lock (_operationGate)
        {
            if (snapshot.IsTerminal)
            {
                _activePostprocessOperationIds.Remove(snapshot.OperationId);
                return true;
            }

            if (!_acceptNewOperations)
            {
                return false;
            }

            _activePostprocessOperationIds.Add(snapshot.OperationId);
            return true;
        }
    }

    private async Task CancelActiveOperationsForShutdownAsync()
    {
        lock (_operationGate)
        {
            _acceptNewOperations = false;
        }

        await _operationCreationGate.WaitAsync();
        string[] operationIds;
        string[] resultIndexOperationIds;
        string[] resultIndexBatchIds;
        string[] odbMergeOperationIds;
        string[] resultBatchIds;
        string[] postprocessOperationIds;
        string[] postprocessGroupQueues;
        try
        {
            lock (_operationGate)
            {
                operationIds = [.. _activeOperationIds];
                resultIndexOperationIds = [.. _activeResultIndexOperationIds];
                resultIndexBatchIds = [.. _activeResultIndexBatches];
                odbMergeOperationIds = [.. _activeOdbMergeOperationIds];
                resultBatchIds = [.. _activeResultBatchIds];
                postprocessOperationIds = [.. _activePostprocessOperationIds];
                postprocessGroupQueues = [.. _activePostprocessGroupQueues];
            }
        }
        finally
        {
            _operationCreationGate.Release();
        }

        var descriptor = _descriptor;
        if ((operationIds.Length == 0
                && resultIndexOperationIds.Length == 0
                && resultIndexBatchIds.Length == 0
                && odbMergeOperationIds.Length == 0
                && resultBatchIds.Length == 0
                && postprocessGroupQueues.Length == 0
                && postprocessOperationIds.Length == 0)
            || descriptor is null
            || !IsValidDescriptor(descriptor))
        {
            return;
        }

        using var timeoutSource = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        var compatibilityCancellations = operationIds.Select(
                operationId => BestEffortCancelOperationAsync(
                    descriptor,
                    operationId,
                    timeoutSource.Token));
        var resultIndexCancellations = resultIndexOperationIds.Select(
            operationId => BestEffortCancelResultIndexAsync(
                descriptor,
                operationId,
                timeoutSource.Token));
        var odbMergeCancellations = odbMergeOperationIds.Select(
            operationId => BestEffortCancelOdbMergeAsync(
                descriptor,
                operationId,
                timeoutSource.Token));
        var postprocessCancellations = postprocessOperationIds.Select(
            operationId => BestEffortCancelPostprocessAsync(
                descriptor,
                operationId,
                timeoutSource.Token));
        await Task.WhenAll(
            compatibilityCancellations
                .Concat(resultBatchIds.Select(id => BestEffortCancelBatchAsync(descriptor, id, timeoutSource.Token)))
                .Concat(postprocessGroupQueues.Select(id => BestEffortStopGroupQueueAsync(descriptor, id, timeoutSource.Token)))
                .Concat(resultIndexCancellations)
                .Concat(resultIndexBatchIds.Select(id => BestEffortCancelIndexBatchAsync(descriptor, id, timeoutSource.Token)))
                .Concat(odbMergeCancellations)
                .Concat(postprocessCancellations));
    }

    private async Task BestEffortCancelOperationAsync(
        ControlPlaneDescriptor descriptor,
        string operationId,
        CancellationToken cancellationToken = default)
    {
        if (_preserveBackground) return;
        try
        {
            using var request = new HttpRequestMessage(
                HttpMethod.Post,
                BuildEndpoint(
                    descriptor,
                    $"/api/v1/operations/{Uri.EscapeDataString(operationId)}/cancel"));
            request.Headers.Authorization = new AuthenticationHeaderValue(
                "Bearer",
                descriptor.Token);
            using var response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken);
        }
        catch (Exception exception) when (
            exception is HttpRequestException
                or IOException
                or OperationCanceledException
                or ObjectDisposedException)
        {
            Debug.WriteLine(
                $"Best-effort cancellation failed for operation {operationId}: {exception.Message}");
        }
        finally
        {
            lock (_operationGate)
            {
                _activeOperationIds.Remove(operationId);
            }
        }
    }

    private async Task BestEffortCancelResultIndexAsync(
        ControlPlaneDescriptor descriptor,
        string operationId,
        CancellationToken cancellationToken = default)
    {
        if (_preserveBackground) return;
        try
        {
            using var request = new HttpRequestMessage(
                HttpMethod.Post,
                BuildEndpoint(
                    descriptor,
                    $"/api/v1/result-index-builds/{Uri.EscapeDataString(operationId)}/cancel"));
            request.Headers.Authorization = new AuthenticationHeaderValue(
                "Bearer",
                descriptor.Token);
            using var response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken);
        }
        catch (Exception exception) when (
            exception is HttpRequestException
                or IOException
                or OperationCanceledException
                or ObjectDisposedException)
        {
            Debug.WriteLine(
                $"Best-effort cancellation failed for result index {operationId}: {exception.Message}");
        }
        finally
        {
            lock (_operationGate)
            {
                _activeResultIndexOperationIds.Remove(operationId);
            }
        }
    }

    private async Task BestEffortCancelOdbMergeAsync(
        ControlPlaneDescriptor descriptor,
        string operationId,
        CancellationToken cancellationToken = default)
    {
        if (_preserveBackground) return;
        try
        {
            using var request = new HttpRequestMessage(
                HttpMethod.Post,
                BuildEndpoint(
                    descriptor,
                    $"/api/v1/odb-merge-operations/{Uri.EscapeDataString(operationId)}/cancel"));
            request.Headers.Authorization = new AuthenticationHeaderValue(
                "Bearer",
                descriptor.Token);
            using var response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken);
        }
        catch (Exception exception) when (
            exception is HttpRequestException
                or IOException
                or OperationCanceledException
                or ObjectDisposedException)
        {
            Debug.WriteLine(
                $"Best-effort cancellation failed for ODB merge {operationId}: {exception.Message}");
        }
        finally
        {
            lock (_operationGate)
            {
                _activeOdbMergeOperationIds.Remove(operationId);
            }
        }
    }

    private async Task BestEffortCancelPostprocessAsync(
        ControlPlaneDescriptor descriptor,
        string operationId,
        CancellationToken cancellationToken = default)
    {
        if (_preserveBackground) return;
        try
        {
            using var request = new HttpRequestMessage(
                HttpMethod.Post,
                BuildEndpoint(
                    descriptor,
                    $"/api/v1/odb-postprocess-operations/{Uri.EscapeDataString(operationId)}/cancel"));
            request.Headers.Authorization = new AuthenticationHeaderValue(
                "Bearer",
                descriptor.Token);
            using var response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken);
        }
        catch (Exception exception) when (
            exception is HttpRequestException
                or IOException
                or OperationCanceledException
                or ObjectDisposedException)
        {
            Debug.WriteLine(
                $"Best-effort cancellation failed for ODB postprocess {operationId}: {exception.Message}");
        }
        finally
        {
            lock (_operationGate)
            {
                _activePostprocessOperationIds.Remove(operationId);
            }
        }
    }

    private void SetState(ControlPlaneState state, string message, Exception? exception = null)
    {
        State = state;
        StatusMessage = message;
        var args = new ControlPlaneStateChangedEventArgs(state, message, exception);
        foreach (var callback in StateChanged?.GetInvocationList() ?? [])
        {
            try
            {
                ((EventHandler<ControlPlaneStateChangedEventArgs>)callback)(this, args);
            }
            catch (Exception stateCallbackError)
            {
                Debug.WriteLine($"Control-plane state callback failed: {stateCallbackError}");
            }
        }
    }

    private async Task<bool> ReserveSafeProcessShutdownAsync()
    {
        var descriptor = _descriptor;
        if (_ownedProcess is null)
        {
            return false;
        }
        if (_ownedInstanceId is null)
        {
            // No ready backend was published to this host during startup.
            return true;
        }
        if (descriptor is null || descriptor.InstanceId != _ownedInstanceId)
        {
            return false;
        }
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            using var request = new HttpRequestMessage(HttpMethod.Post,
                BuildEndpoint(descriptor, "/api/v1/odb-upgrade-shutdown-check"));
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", descriptor.Token);
            using var response = await _httpClient.SendAsync(request, timeout.Token);
            response.EnsureSuccessStatusCode();
            using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync(timeout.Token));
            var root = document.RootElement;
            return root.TryGetProperty("schemaVersion", out var schema)
                && schema.TryGetInt32(out var version) && version == 1
                && root.TryGetProperty("scope", out var scope)
                && scope.GetString() == "all-workers-v1"
                && root.TryGetProperty("safeToStop", out var safe)
                && safe.ValueKind == JsonValueKind.True
                && root.TryGetProperty("operations", out var operations)
                && operations.ValueKind == JsonValueKind.Array
                && operations.GetArrayLength() == 0;
        }
        catch (Exception exception) when (exception is HttpRequestException or IOException
            or OperationCanceledException or JsonException or InvalidOperationException)
        {
            // Unknown or old ODB-only state cannot establish full process safety.
            Debug.WriteLine($"Keeping backend alive: shutdown safety check failed: {exception.Message}");
            return false;
        }
    }

    private void StopOwnedProcess(bool shutdownReserved = false)
    {
        var process = _ownedProcess;
        _ownedProcess = null;
        var ownedInstanceId = _ownedInstanceId;
        _ownedInstanceId = null;
        _ownedLaunchToken = null;
        if (process is null)
        {
            return;
        }

        var ownedPid = 0;
        try
        {
            ownedPid = process.Id;
        }
        catch (InvalidOperationException)
        {
            // A process object that never fully started has no stable PID.
        }

        process.OutputDataReceived -= OnProcessOutput;
        process.ErrorDataReceived -= OnProcessOutput;
        process.Exited -= OnOwnedProcessExited;
        if (ownedInstanceId is not null && !shutdownReserved)
        {
            // Keep the descriptor so another window can reattach to the active
            // backend. Disposing this handle does not terminate its process.
            Debug.WriteLine("Detached from backend without terminating active or unverified background work.");
            process.Dispose();
            return;
        }
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                process.WaitForExit(2_000);
            }
        }
        catch (Exception exception) when (exception is InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            // The owned child may have exited between the state check and termination.
        }
        finally
        {
            process.Dispose();
            TryDeleteDescriptorOwnedBy(ownedPid, ownedInstanceId);
        }
    }

    private void TryDeleteDescriptorOwnedBy(int ownedPid, string? ownedInstanceId)
    {
        if (ownedPid <= 0 && string.IsNullOrWhiteSpace(ownedInstanceId))
        {
            return;
        }

        try
        {
            using var stream = new FileStream(
                _descriptorPath,
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(stream, JsonOptions);
            if (descriptor is not null
                && ((!string.IsNullOrWhiteSpace(ownedInstanceId)
                        && string.Equals(
                            descriptor.InstanceId,
                            ownedInstanceId,
                            StringComparison.Ordinal))
                    || (string.IsNullOrWhiteSpace(ownedInstanceId)
                        && descriptor.Pid == ownedPid)))
            {
                File.Delete(_descriptorPath);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            // Cleanup is conservative and best-effort; a newer process may own the path.
        }
    }

    public ValueTask DisposeAsync()
    {
        Task disposeTask;
        lock (_disposeGate)
        {
            _disposeTask ??= DisposeCoreAsync();
            disposeTask = _disposeTask;
        }

        return new ValueTask(disposeTask);
    }

    private async Task DisposeCoreAsync(bool preserveBackground = false)
    {
        if (_disposed)
        {
            return;
        }

        if (preserveBackground)
        {
            lock (_operationGate) _acceptNewOperations = false;
            await _operationCreationGate.WaitAsync();
            _operationCreationGate.Release();
        }
        else await CancelActiveOperationsForShutdownAsync();
        _shutdownSource.Cancel();
        await _connectionGate.WaitAsync();
        var completed = false;
        try
        {
            var shutdownReserved = !preserveBackground && await ReserveSafeProcessShutdownAsync();
            StopOwnedProcess(shutdownReserved);
            _httpClient.Dispose();
            SetState(ControlPlaneState.Disconnected, "控制面已断开");
            _disposed = true;
            completed = true;
        }
        finally
        {
            _connectionGate.Release();
            if (completed)
            {
                _connectionGate.Dispose();
                _operationCreationGate.Dispose();
                _shutdownSource.Dispose();
            }
        }
    }
}
