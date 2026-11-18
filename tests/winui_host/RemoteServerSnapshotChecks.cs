using System.Text.Json;
using AbaqusTools.WinUI.Services;

internal static class RemoteServerSnapshotChecks
{
    public static void Run()
    {
        var old = JsonSerializer.Deserialize<RemoteServerConnection>(
            """{"status":"connected","profileName":"节点 A"}""")!;
        Require(!old.IsBusy && old.DisplayText == "已连接 · 节点 A", "Old backend connection compatibility");
        var busy = JsonSerializer.Deserialize<RemoteServerConnection>(
            """{"status":"connected","busy":true,"activity":"正在刷新远端资源","resource":{"cpu_total":32}}""")!;
        Require(busy.DisplayText == "正在刷新远端资源 · 资源值为上次读取"
            && busy.StatusBarText == "远端 ◐ 更新中", "Cached metrics must not appear freshly measured");
        var connecting = new RemoteServerConnection { Status = "connecting", IsBusy = true, Activity = "正在连接服务器" };
        Require(connecting.DisplayText == "正在连接服务器", "Connecting without old-server metrics");
        var failed = new RemoteServerConnection { Status = "error" };
        Require(failed.DisplayText == "连接异常" && failed.StatusBarText.Contains("连接异常"), "Failure clears busy presentation");
        Console.WriteLine("Remote connection snapshot: 4 checks passed.");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
