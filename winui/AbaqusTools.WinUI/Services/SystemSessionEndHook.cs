using System.Runtime.InteropServices;

namespace AbaqusTools.WinUI.Services;

/// <summary>Install and remove on the window's UI thread; keep the delegate rooted.</summary>
public sealed class SystemSessionEndHook : IDisposable
{
    private const nuint SubclassId = 0x41545345;
    private readonly SubclassProcedure _callback;
    private readonly SystemSessionEndState _state;
    private nint _window;

    public SystemSessionEndHook(nint window, SystemSessionEndState state)
    {
        _state = state;
        _callback = WindowProcedure;
        if (!SetWindowSubclass(window, _callback, SubclassId, 0))
            throw new InvalidOperationException("无法登记系统会话结束处理；定期草稿保存仍可使用。");
        _window = window;
    }

    private nint WindowProcedure(nint window, uint message, nuint wParam, nint lParam,
        nuint subclassId, nuint referenceData)
    {
        if (message == 0x0082) Dispose(); // WM_NCDESTROY
        if (_state.TryHandle(message, wParam, out var result)) return result;
        return DefSubclassProc(window, message, wParam, lParam);
    }

    public void Dispose()
    {
        if (_window == 0) return;
        RemoveWindowSubclass(_window, _callback, SubclassId);
        _window = 0;
    }

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate nint SubclassProcedure(nint window, uint message, nuint wParam, nint lParam,
        nuint subclassId, nuint referenceData);

    [DllImport("comctl32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowSubclass(nint window, SubclassProcedure callback, nuint id, nuint data);
    [DllImport("comctl32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool RemoveWindowSubclass(nint window, SubclassProcedure callback, nuint id);
    [DllImport("comctl32.dll", ExactSpelling = true)]
    private static extern nint DefSubclassProc(nint window, uint message, nuint wParam, nint lParam);
}
