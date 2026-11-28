using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Windows.Storage.Pickers;

namespace AbaqusTools.WinUI.Pages;

internal sealed record RemoteDownloadDestination(string Path, bool Overwrite)
{
    internal static async Task<RemoteDownloadDestination?> PickAsync(XamlRoot root, string remotePath, string action)
    {
        var extension = System.IO.Path.GetExtension(remotePath);
        var picker = new FileSavePicker(App.Current.MainWindow.AppWindow.Id)
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            SuggestedFileName = System.IO.Path.GetFileName(remotePath),
            CommitButtonText = action,
            ShowOverwritePrompt = false,
        };
        if (!string.IsNullOrWhiteSpace(extension))
            picker.FileTypeChoices.Add($"{extension} 文件", [extension]);

        // This desktop picker returns a path without creating or truncating the target.
        var result = await picker.PickSaveFileAsync();
        if (result is null) return null;
        if (!File.Exists(result.Path)) return new(result.Path, false);

        var confirm = new ContentDialog
        {
            XamlRoot = root,
            Title = "替换本机同名文件？",
            Content = result.Path,
            PrimaryButtonText = "替换并下载",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        return await confirm.ShowAsync() == ContentDialogResult.Primary ? new(result.Path, true) : null;
    }
}
