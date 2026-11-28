using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

namespace AbaqusTools.WinUI.Pages;

public enum RemoteSelectionMode
{
    File,
    Folder,
    Browse,
}

public sealed record RemoteFileSelection(string Path, bool IsDirectory);

public sealed class RemoteFileBrowserDialog
{
    private readonly RemoteSelectionMode _mode;
    private readonly string? _sourceOperationId;
    private readonly RemoteServerProfile? _expectedProfile;
    private readonly ContentDialog _dialog;
    private readonly TextBox _pathBox;
    private readonly ListView _list;
    private readonly Button _upButton;
    private readonly Button _openButton;
    private readonly InfoBar _infoBar;
    private readonly ObservableCollection<RemoteDirectoryEntry> _entries = [];
    private string _parentPath = string.Empty;
    private string? _retryPath;
    private bool _busy;

    public RemoteFileBrowserDialog(
        XamlRoot xamlRoot,
        RemoteSelectionMode mode,
        string title,
        string? sourceOperationId = null,
        RemoteServerProfile? expectedProfile = null)
    {
        _mode = mode;
        _sourceOperationId = sourceOperationId;
        _expectedProfile = expectedProfile;
        _pathBox = new TextBox { IsReadOnly = true, PlaceholderText = "服务器目录" };
        _upButton = new Button { Content = "上一级", IsEnabled = false };
        _openButton = new Button { Content = "进入", IsEnabled = false };
        _list = new ListView
        {
            ItemsSource = _entries,
            SelectionMode = ListViewSelectionMode.Single,
            MinHeight = 330,
            MaxHeight = 500,
        };
        _infoBar = new InfoBar { IsOpen = false, IsClosable = true };
        _list.DoubleTapped += OnListDoubleTapped;
        _upButton.Click += OnUpClicked;
        _openButton.Click += OnOpenClicked;

        var header = new Grid { ColumnSpacing = 8 };
        header.ColumnDefinitions.Add(new ColumnDefinition());
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.Children.Add(_pathBox);
        Grid.SetColumn(_upButton, 1);
        header.Children.Add(_upButton);
        Grid.SetColumn(_openButton, 2);
        header.Children.Add(_openButton);

        var panel = new StackPanel { Spacing = 10, HorizontalAlignment = HorizontalAlignment.Stretch };
        panel.Children.Add(_infoBar);
        panel.Children.Add(header);
        panel.Children.Add(_list);
        panel.Children.Add(new TextBlock
        {
            Text = mode switch
            {
                RemoteSelectionMode.File => "双击进入文件夹，选择文件后确认。",
                RemoteSelectionMode.Folder => "双击进入文件夹，确认时选择当前目录。",
                _ => "双击文件夹查看内容。",
            },
            Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[
                "TextFillColorSecondaryBrush"],
        });

        _dialog = new ContentDialog
        {
            XamlRoot = xamlRoot,
            Title = title,
            Content = panel,
            PrimaryButtonText = mode switch
            {
                RemoteSelectionMode.File => "选择文件",
                RemoteSelectionMode.Folder => "选择当前目录",
                _ => "",
            },
            CloseButtonText = mode == RemoteSelectionMode.Browse ? "关闭" : "取消",
            DefaultButton = mode == RemoteSelectionMode.Browse ? ContentDialogButton.Close : ContentDialogButton.Primary,
        };
        _dialog.Closing += OnDialogClosing;
        _list.SelectionChanged += (_, _) => SetControlsEnabled(!_busy);
    }

    public RemoteFileSelection? Selection { get; private set; }

    public async Task<RemoteFileSelection?> ShowAsync(string initialPath = "")
    {
        await NavigateAsync(initialPath);
        var result = await _dialog.ShowAsync();
        return result == ContentDialogResult.Primary ? Selection : null;
    }

    private void OnDialogClosing(ContentDialog sender, ContentDialogClosingEventArgs args)
    {
        if (args.Result != ContentDialogResult.Primary)
        {
            return;
        }
        if (_mode == RemoteSelectionMode.Folder)
        {
            Selection = new RemoteFileSelection(_pathBox.Text, true);
            return;
        }
        if (_list.SelectedItem is not RemoteDirectoryEntry { IsDirectory: false } file)
        {
            args.Cancel = true;
            ShowError("请选择一个文件；如需进入文件夹，请双击该文件夹。");
            return;
        }
        Selection = new RemoteFileSelection(file.Path, false);
    }

    private async void OnListDoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
    {
        if (_list.SelectedItem is RemoteDirectoryEntry { IsDirectory: true } directory)
        {
            await NavigateAsync(directory.Path);
        }
    }

    private async void OnOpenClicked(object sender, RoutedEventArgs e)
    {
        if (_retryPath is { } path)
        {
            await NavigateAsync(path);
        }
        else if (_list.SelectedItem is RemoteDirectoryEntry { IsDirectory: true } directory)
        {
            await NavigateAsync(directory.Path);
        }
    }

    private async void OnUpClicked(object sender, RoutedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(_parentPath))
        {
            await NavigateAsync(_parentPath);
        }
    }

    private async Task NavigateAsync(string path)
    {
        if (_busy)
        {
            return;
        }
        _busy = true;
        SetControlsEnabled(false);
        _infoBar.IsOpen = false;
        try
        {
            var listing = await App.Current.ControlPlane.BrowseRemoteDirectoryAsync(path,
                sourceOperationId: _sourceOperationId, expectedProfile: _expectedProfile);
            _retryPath = null;
            _pathBox.Text = listing.Path;
            _parentPath = listing.ParentPath;
            _entries.Clear();
            foreach (var entry in listing.Entries)
            {
                _entries.Add(entry);
            }
            _list.SelectedItem = null;
        }
        catch (Exception exception)
        {
            _retryPath = path;
            _entries.Clear();
            _pathBox.Text = "";
            _parentPath = "";
            ShowError(exception.Message);
        }
        finally
        {
            _busy = false;
            SetControlsEnabled(true);
        }
    }

    private void SetControlsEnabled(bool enabled)
    {
        _upButton.IsEnabled = enabled && !string.IsNullOrWhiteSpace(_parentPath);
        _openButton.Content = _retryPath is null ? "进入" : "重试";
        _openButton.IsEnabled = enabled && (_retryPath is not null || _list.SelectedItem is RemoteDirectoryEntry { IsDirectory: true });
        _list.IsEnabled = enabled;
        _dialog.IsPrimaryButtonEnabled = enabled && (_mode switch
        {
            RemoteSelectionMode.Folder => !string.IsNullOrEmpty(_pathBox.Text),
            RemoteSelectionMode.File => _list.SelectedItem is RemoteDirectoryEntry { IsDirectory: false },
            _ => false,
        });
    }

    private void ShowError(string message)
    {
        _infoBar.Title = "远端目录读取失败";
        _infoBar.Message = message;
        _infoBar.Severity = InfoBarSeverity.Error;
        _infoBar.IsOpen = true;
    }
}
