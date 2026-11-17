using Microsoft.VisualBasic.FileIO;

namespace AbaqusTools.WinUI.Services;

internal static class ResultFileRecycle
{
    private static readonly HashSet<string> ExportExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".csv", ".xlsx", ".png", ".jpg", ".jpeg", ".gif", ".txt", ".log",
    };

    public static bool IsExport(string path) => ExportExtensions.Contains(Path.GetExtension(path));

    public static string ValidatePath(string root, string path)
    {
        var directory = Path.GetFullPath(root);
        var file = Path.GetFullPath(path);
        var relative = Path.GetRelativePath(directory, file);
        if (relative == ".." || relative.StartsWith(".." + Path.DirectorySeparatorChar)
            || Path.IsPathFullyQualified(relative) || !IsExport(file))
            throw new IOException("请选择当前结果根目录内的导出文件。");
        if (!File.Exists(file)) throw new FileNotFoundException("文件已移动或不存在。", file);
        for (var current = file; current is not null; current = Path.GetDirectoryName(current))
        {
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("文件路径包含链接，请到实际存放目录操作。");
            if (string.Equals(current, directory, StringComparison.OrdinalIgnoreCase)) return file;
        }
        throw new IOException("无法验证文件所属的结果目录。");
    }

    public static void Recycle(string root, string path)
    {
        var file = ValidatePath(root, path);
        FileSystem.DeleteFile(file, UIOption.AllDialogs, RecycleOption.SendToRecycleBin,
            UICancelOption.ThrowException);
    }
}
