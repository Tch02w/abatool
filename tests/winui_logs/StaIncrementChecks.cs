using AbaqusTools.WinUI.Services;

internal static class StaIncrementChecks
{
    private const string Header = " Abaqus/Standard 2025   DATE 06-10-2026\n SUMMARY OF JOB INFORMATION:\n"
        + " STEP  INC ATT SEVERE EQUIL TOTAL  TOTAL      STEP       INC OF       DOF    IF\n"
        + "               DISCON ITERS ITERS  TIME/    TIME/LPF    TIME/LPF    MONITOR RIKS\n"
        + "               ITERS               FREQ\n";
    private const string Cutback = "   7     1   1U    2     5     7  6.00       0.00       0.01000";

    internal static void Run()
    {
        var directory = Directory.CreateTempSubdirectory("workbench-sta-");
        var path = Path.Combine(directory.FullName, "selected.sta");
        var reader = new StaIncrementReader();
        try
        {
            Check(reader.Read(path).Rows.Length == 0, "missing STA");
            File.WriteAllText(path, Header + Cutback + "\n" + "   7 1 2 3 1 4 6.00 0.00250 0.00");
            var initial = reader.Read(path);
            Check(initial.Header.Contains("TOTAL TIME/FREQ") && initial.Rows.Contains("1U")
                && initial.Rows.Contains("0.01000") && initial.Rows.Split('\n').Length == 1, "no partial row");
            Check(ReferenceEquals(initial, reader.Read(path)), "unchanged file should reuse parsed result");
            File.AppendAllText(path, "2500\n" + Cutback.PadRight(78) + "*\n"
                + Cutback + "    2.34E-01 *\n" + "   7 2 1 3 1 4 6.00 warning 0.20\n");
            var updated = reader.Read(path);
            var rows = updated.Rows.Split("\r\n");
            Check(rows.Length == 4 && rows[1].Contains("0.002500")
                && rows[2].LastIndexOf('*') == rows[3].LastIndexOf('*')
                && rows[2].Length == updated.Header.Length && updated.Header.Contains("IF RIKS")
                && rows[3].Contains("2.34E-01"), "append, optional fields and common column widths");
            File.WriteAllText(path, Header.Replace("DOF    IF", "DOF") + Cutback + "  1.23E-04\n");
            var dofOnly = reader.Read(path);
            Check(dofOnly.Header.EndsWith("DOF MONITOR") && dofOnly.Rows.EndsWith("1.23E-04"), "DOF-only column");
            File.WriteAllText(path, Header.Replace("DOF    IF", "       IF") + Cutback + "  *\n");
            var riksOnly = reader.Read(path);
            Check(riksOnly.Header.EndsWith("IF RIKS") && !riksOnly.Header.Contains("DOF")
                && riksOnly.Rows.EndsWith('*'), "Riks-only column");
            File.WriteAllText(path, Header.Replace("Abaqus/Standard", "Abaqus/Explicit") + Cutback + "\n");
            Check(reader.Read(path).Rows.Length == 0, "Explicit source is never classified as Standard");
            File.WriteAllText(path, Cutback + "\n");
            Check(reader.Read(path).Rows.Length == 0, "numeric lines alone are insufficient evidence");
            File.WriteAllText(path, Header.Replace("DOF    IF", "CUSTOM") + Cutback + "  18\n");
            Check(reader.Read(path).Rows.Length == 0, "unsupported header must not mislabel optional fields");
            File.WriteAllText(path, Header + new string('x', 140000) + Cutback + "\n" +
                string.Concat(Enumerable.Range(1, 400).Select(i => $" 7 {i} 1 2 5 7 6D+00 0.0 0.01\n")));
            var bounded = reader.Read(path);
            rows = bounded.Rows.Split("\r\n");
            Check(rows.Length == StaIncrementReader.MaxRows && rows[0].Split(' ', StringSplitOptions.RemoveEmptyEntries)[1] == "101"
                && rows[^1].Contains("400") && bounded.Rows.Contains("6D+00"), "bounded tail and Fortran exponent");
            File.Delete(path);
            Check(reader.Read(path).Rows.Length == 0, "disappeared source clears old rows");
            File.WriteAllText(path, Header + Cutback + "\n");
            Check(reader.Read(path).Rows.Contains("1U"), "replacement source is readable");
            if (OperatingSystem.IsWindows()) CheckConcurrentUpdates(path);
            Console.WriteLine("STA increment preview file and column checks passed");
        }
        finally
        {
            File.Delete(path);
            directory.Delete();
        }
    }

    private static void CheckConcurrentUpdates(string path)
    {
        var reader = new StaIncrementReader();
        const string next = "   7 2 1 2 1 3 6.2 0.1 0.01\n";
        var content = Header + new string('x', 142000) + "\n" + Cutback + "\n";
        File.WriteAllText(path, content);
        var captured = reader.Read(path, () => File.AppendAllText(path, next));
        Check(captured.Rows.Contains("1U") && !captured.Rows.Contains("6.2"), "append while reading preserves complete sampled row");
        var advanced = reader.Read(path);
        Check(advanced.Rows.Contains("6.2") && ReferenceEquals(advanced, reader.Read(path)), "next poll picks up unconsumed append");

        File.WriteAllText(path, content);
        var rewritten = reader.Read(path, () => File.WriteAllText(path, content.Replace("1U ", "2U ") + next));
        Check(rewritten.Rows.Length == 0 && reader.Read(path).Rows.Contains("2U"), "growth with rewritten tail invalidates preview");
        File.WriteAllText(path, content);
        var shortened = reader.Read(path, () => File.WriteAllText(path, Header));
        Check(shortened.Rows.Length == 0 && reader.Read(path).Rows.Length == 0, "truncation during read clears old rows");
        File.WriteAllText(path, content);
        var sameSize = reader.Read(path, () =>
        {
            File.WriteAllText(path, content.Replace("1U ", "3U "));
            File.SetLastWriteTimeUtc(path, DateTime.UtcNow.AddMinutes(-1));
        });
        Check(sameSize.Rows.Length == 0 && reader.Read(path).Rows.Contains("3U"), "same-size rewrite retries");

        File.WriteAllText(path, content + next);
        var replacement = path + ".replacement";
        var previous = path + ".previous";
        try
        {
            var replaced = reader.Read(path, () =>
            {
                var created = File.GetCreationTimeUtc(path);
                File.WriteAllText(replacement, content + next + next);
                File.SetCreationTimeUtc(replacement, created);
                File.Move(path, previous);
                File.Move(replacement, path);
            });
            var reopened = reader.Read(path);
            Check(replaced.Rows.Length == 0 && reopened.Rows.Split("\r\n").Length == 3,
                $"different file ID with identical prefix and creation time invalidates preview ({replaced.Status}; {reopened.Status})");
            Console.WriteLine("STA concurrent read checks passed: append, rewrite with growth, truncate, same-size rewrite, file replacement");
        }
        finally
        {
            File.Delete(replacement);
            File.Delete(previous);
        }
    }

    private static void Check(bool success, string label)
    {
        if (!success) throw new InvalidOperationException($"STA increment check failed: {label}");
    }
}
