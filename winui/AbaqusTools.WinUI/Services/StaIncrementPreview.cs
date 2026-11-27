using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32.SafeHandles;

namespace AbaqusTools.WinUI.Services;

internal sealed record StaIncrementPreview(string Header, string Rows, string Status)
{
    internal static StaIncrementPreview Empty(string message) => new("", "", message);
}

/// <summary>Reads a bounded preview from the selected job's Standard status file.</summary>
internal sealed partial class StaIncrementReader
{
    private const int HeadBytes = 8192;
    private const int TailBytes = 128 * 1024;
    internal const int MaxRows = 300;
    private (string Path, long Length, DateTime Created, DateTime Modified)? _signature;
    private StaIncrementPreview? _preview;

    // Includes the alternatives printed in the native multi-line Standard header.
    private static readonly string[] ColumnNames =
        ["STEP", "INC", "ATT", "SEVERE", "EQUIL", "TOTAL", "TOTAL TIME/FREQ",
         "STEP TIME/LPF", "INC TIME/LPF", "DOF MONITOR", "IF RIKS"];

    // One reader is owned by one active job view. All reads run serially on a worker.
    internal StaIncrementPreview Read(string path, Action? afterReading = null)
    {
        try
        {
            var file = new FileInfo(path);
            if (!file.Exists) return Clear("STA 文件尚未生成或已移走。");
            var signature = (file.FullName, file.Length, file.CreationTimeUtc, file.LastWriteTimeUtc);
            if (_signature == signature && _preview is not null) return _preview;

            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            long length = signature.Length;
            var head = ReadSlice(stream, 0, (int)Math.Min(length, HeadBytes));
            long tailStart = Math.Max(0, length - TailBytes);
            long tailOffset = Math.Max(0, tailStart - 1);
            string? tail = null;
            StaIncrementPreview preview;
            var header = StandardHeader(head);
            if (header is null)
            {
                preview = StaIncrementPreview.Empty("尚未识别到 Abaqus/Standard 增量表头。可查看运行日志或打开 STA 原文件。");
            }
            else
            {
                // Include the byte before the tail to distinguish a partial first line.
                tail = length <= HeadBytes ? head : ReadSlice(stream, tailOffset, (int)(length - tailOffset));
                preview = tailStart == 0 ? Format(tail, false, true, header)
                    : Format(tail[1..], tail[0] != '\n', false, header);
            }
            afterReading?.Invoke();
            file.Refresh();
            if (!file.Exists || file.CreationTimeUtc != signature.CreationTimeUtc || file.Length < length
                || (file.Length == length && file.LastWriteTimeUtc != signature.LastWriteTimeUtc))
                return Clear("STA 文件正在更新，等待下一次读取。");
            if (file.Length > length)
            {
                // Abaqus may append while we format. Check the bytes we actually present
                // on a fresh handle, so a concurrent replacement or rewrite is detectable.
                using var current = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
                if (!SameFile(stream.SafeFileHandle, current.SafeFileHandle) || current.Length <= length
                    || ReadSlice(current, 0, head.Length) != head
                    || (tail is not null && length > HeadBytes && ReadSlice(current, tailOffset, tail.Length) != tail))
                    return Clear("STA 文件正在更新，等待下一次读取。");
            }
            // Cache only through the length actually read; an append must be picked up next poll.
            _signature = signature;
            return _preview = preview;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return Clear($"暂时无法读取 STA 文件。{ex.Message}");
        }
    }

    private StaIncrementPreview Clear(string message)
    {
        _signature = null;
        _preview = null;
        return StaIncrementPreview.Empty(message);
    }

    private static string ReadSlice(Stream stream, long offset, int count)
    {
        var bytes = new byte[count];
        stream.Position = offset;
        stream.ReadExactly(bytes);
        // All parsed fields are ASCII. Latin1 also preserves every other byte for comparison.
        return Encoding.Latin1.GetString(bytes);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct FileId
    {
        public ulong Volume;
        public Guid Id;
    }

    [DllImport("kernel32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(SafeFileHandle handle, int infoClass,
        out FileId info, uint size);

    private static bool SameFile(SafeFileHandle first, SafeFileHandle second)
    {
        const int fileIdInfo = 18; // FILE_INFO_BY_HANDLE_CLASS.FileIdInfo
        uint size = (uint)Marshal.SizeOf<FileId>();
        return OperatingSystem.IsWindows() && GetFileInformationByHandleEx(first, fileIdInfo, out var a, size)
            && GetFileInformationByHandleEx(second, fileIdInfo, out var b, size)
            && a.Id != Guid.Empty && a.Volume == b.Volume && a.Id == b.Id;
    }

    private static string? StandardHeader(string head)
    {
        var lines = head.Split('\n');
        var solver = lines.FirstOrDefault(line => line.TrimStart().StartsWith("Abaqus/", StringComparison.OrdinalIgnoreCase));
        return solver?.TrimStart().StartsWith("Abaqus/Standard ", StringComparison.OrdinalIgnoreCase) == true
            ? lines.FirstOrDefault(line => StandardColumns().IsMatch(line)) : null;
    }

    [GeneratedRegex(@"^\s*STEP\s+INC\s+ATT\s+SEVERE\s+EQUIL\s+TOTAL\s+TOTAL\s+STEP\s+INC(?:\s+OF)?(?:\s+DOF)?(?:\s+(?:IF|RIKS))?\s*$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex StandardColumns();

    [GeneratedRegex(@"^[0-9]+$")]
    private static partial Regex IntegerField();

    [GeneratedRegex(@"^[0-9]+U?$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex AttemptField();

    private static bool Number(string field) =>
        double.TryParse(field.Replace('D', 'E').Replace('d', 'e'), NumberStyles.Float,
            CultureInfo.InvariantCulture, out var number) && double.IsFinite(number);

    private static StaIncrementPreview Format(string tail, bool partialFirst, bool startsAtHead, string header)
    {
        var lines = tail.Split('\n');
        var inTable = !startsAtHead;
        int dofAt = header.IndexOf("DOF", StringComparison.OrdinalIgnoreCase);
        int riksAt = header.LastIndexOf("IF", StringComparison.OrdinalIgnoreCase);
        if (riksAt < 0) riksAt = header.IndexOf("RIKS", StringComparison.OrdinalIgnoreCase);
        string[] labels = [.. ColumnNames[..9], .. (dofAt >= 0 ? ColumnNames[9..10] : []),
            .. (riksAt >= 0 ? ColumnNames[10..11] : [])];
        var rows = new Queue<string[]>(MaxRows);
        for (var i = partialFirst ? 1 : 0; i < lines.Length - 1; i++)
        {
            // Ignore the incomplete last record while Abaqus is writing it.
            var line = lines[i];
            if (!inTable)
            {
                inTable = StandardColumns().IsMatch(line);
                continue;
            }
            var fields = line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length < 9 || fields.Length > labels.Length || !IntegerField().IsMatch(fields[0])
                || !IntegerField().IsMatch(fields[1]) || !AttemptField().IsMatch(fields[2])
                || !fields[3..6].All(IntegerField().IsMatch) || !fields[6..9].All(Number))
                continue;
            if (fields.Length == 10 && dofAt >= 0 && riksAt >= 0
                && line.LastIndexOf(fields[9], StringComparison.Ordinal) >= riksAt - 1)
                fields = [.. fields[..9], "", fields[9]];
            if (fields.Length > 9 && dofAt >= 0 && fields[9].Length > 0 && !Number(fields[9])) continue;
            if (rows.Count == MaxRows) rows.Dequeue();
            rows.Enqueue(fields);
        }
        if (rows.Count == 0) return StaIncrementPreview.Empty("当前 STA 尾部暂无完整的标准增量记录。");
        int columns = rows.Max(row => row.Length);
        int[] widths = labels[..columns].Select(name => name.Length).ToArray();
        foreach (var row in rows)
            for (var i = 0; i < row.Length; i++)
                widths[i] = Math.Max(widths[i], row[i].Length);
        string Align(string[] fields) => string.Join("  ", fields.Select((field, i) => field.PadLeft(widths[i])));
        return new(Align(labels[..columns]), string.Join("\r\n", rows.Select(Align)),
            $"STA 尾部 · 最近 {rows.Count} 条增量");
    }
}
