using System.Globalization;
using System.Text.Json;

namespace AbaqusTools.WinUI.Services;

/// <summary>Seed untouched native pages from the settings saved explicitly by the PySide workbench.</summary>
internal static class LegacyWorkbenchSettings
{
    public static void ImportMissingPages(WorkbenchSessionState state, string path)
    {
        bool newJob = !state.Pages.ContainsKey("new-job");
        bool merge = !state.Pages.ContainsKey("odb-merge");
        if (!newJob && !merge) return;

        JsonDocument document;
        try
        {
            using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete);
            document = JsonDocument.Parse(input);
        }
        catch (FileNotFoundException) { return; }
        catch (DirectoryNotFoundException) { return; }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                throw new InvalidDataException("旧版配置的根节点不是对象。");
            root.TryGetProperty("workbench", out var values);
            if (values.ValueKind is not (JsonValueKind.Object or JsonValueKind.Undefined))
                throw new InvalidDataException("旧版 workbench 配置格式无效。");

            if (newJob)
            {
                var fields = new Dictionary<string, string>();
                Text(values, "inp_file", fields, "InputPathTextBox");
                Text(values, "job_name", fields, "JobNameTextBox");
                Text(values, "oldjob_path", fields, "OldjobPathTextBox");
                Text(values, "fortran_path", fields, "FortranPathTextBox");
                Text(values, "abaqus_command", fields, "AbaqusCommandTextBox");
                Text(values, "memory_value", fields, "MemoryValueTextBox");
                Choice(values, "memory_unit", fields, "MemoryUnitComboBox", "%", "MB", "GB");
                Integer(values, "cpus", fields, "CpuNumberBox", 0);
                Integer(values, "max_parallel", fields, "MaxParallelNumberBox", 1);
                if (Property(values, "priority") is { ValueKind: JsonValueKind.Number } priority
                    && priority.TryGetInt32(out int number) && number is 0 or 10 or -10)
                    fields["PriorityComboBox"] = number switch { 10 => "1", -10 => "2", _ => "0" };
                Flag(values, "interactive", fields, "InteractiveCheckBox");
                Flag(values, "datacheck", fields, "DatacheckCheckBox");
                Flag(values, "notify", fields, "NotifyCheckBox");
                Flag(values, "use_ssd_calculation", fields, "UseSsdCheckBox");
                // Older releases kept these two paths outside the workbench section.
                Text(root, "qt_ssd_work_dir", fields, "CalculationRootTextBox");
                Text(root, "qt_archive_dir", fields, "ArchiveRootTextBox");
                Text(values, "calculation_root_dir", fields, "CalculationRootTextBox");
                Text(values, "archive_dir", fields, "ArchiveRootTextBox");
                if (fields.Count > 0) state.Pages.Add("new-job", fields);
            }
            if (merge)
            {
                var fields = new Dictionary<string, string>();
                Flag(values, "merge_include_history", fields, "IncludeHistoryCheckBox");
                Flag(values, "merge_compress_result", fields, "CompressResultCheckBox");
                Flag(values, "merge_copy_original", fields, "CopyOriginalCheckBox");
                Choice(values, "merge_name_source", fields, "ResultNamingComboBox", "restart", "original", "custom");
                Choice(values, "merge_conflict_strategy", fields, "ConflictPolicyComboBox", "auto_number", "confirm");
                if (fields.Count > 0) state.Pages.Add("odb-merge", fields);
            }
        }
    }

    private static JsonElement Property(JsonElement values, string key) =>
        values.ValueKind == JsonValueKind.Object && values.TryGetProperty(key, out var value) ? value : default;

    private static void Text(JsonElement values, string key, Dictionary<string, string> fields, string field)
    {
        var value = Property(values, key);
        if (value.ValueKind == JsonValueKind.String && value.GetString() is { Length: <= 32768 } text)
            fields[field] = text;
    }

    private static void Integer(JsonElement values, string key, Dictionary<string, string> fields, string field, int minimum)
    {
        var value = Property(values, key);
        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var number) && number >= minimum)
            fields[field] = number.ToString(CultureInfo.InvariantCulture);
    }

    private static void Flag(JsonElement values, string key, Dictionary<string, string> fields, string field)
    {
        var value = Property(values, key);
        if (value.ValueKind is JsonValueKind.True or JsonValueKind.False)
            fields[field] = value.GetBoolean() ? "true" : "false";
    }

    private static void Choice(JsonElement values, string key, Dictionary<string, string> fields, string field, params string[] choices)
    {
        var value = Property(values, key);
        if (value.ValueKind != JsonValueKind.String) return;
        var index = Array.IndexOf(choices, value.GetString());
        if (index >= 0) fields[field] = index.ToString(CultureInfo.InvariantCulture);
    }
}
