using AbaqusTools.WinUI.Services;

internal static class PostprocessResultLocationChecks
{
    public static void Run()
    {
        // This regression needs directory layout only. No ODB or Abaqus invocation is required.
        var temp = Directory.CreateTempSubdirectory("postprocess-results-").FullName;
        try
        {
            var root = Directory.CreateDirectory(Path.Combine(temp, "项目")).FullName;
            var other = Directory.CreateDirectory(Path.Combine(temp, "新项目")).FullName;
            var sourceA = Path.Combine(root, "模型甲", "same.odb");
            var sourceB = Path.Combine(root, "模型乙", "same.odb");
            const string name = "AbaqusODBPostProcessor_Results";
            var a = Path.Combine(root, "模型甲", name);
            var b = Path.Combine(root, "模型乙", name);
            var top = Path.Combine(root, name);
            var outputA = Directory.CreateDirectory(Path.Combine(a, "组", "批", "模型甲")).FullName;
            var outputB = Directory.CreateDirectory(Path.Combine(b, "组", "批", "模型乙")).FullName;
            var region = Directory.CreateDirectory(Path.Combine(top, "通用对象提取", "批", "对象")).FullName;
            var unrelated = Directory.CreateDirectory(Path.Combine(other, name)).FullName;
            var locations = new OdbPostprocessResultLocations();
            string[] Discover() => [sourceA, sourceB];
            string[] Resolve(params string[] selected) => locations.Resolve(root, root, selected, Discover()).ToArray();

            void Equal(string[] actual, params string[] expected)
            {
                if (!actual.SequenceEqual(expected)) throw new InvalidOperationException(string.Join(", ", actual));
            }
            void Missing(Action action)
            {
                try { action(); }
                catch (InvalidOperationException) { return; }
                throw new InvalidOperationException("Unexpected result destination");
            }
            OdbPostprocessOperationSnapshot Snapshot(string id, string status, string[] roots, params string[] outputs) => new()
            {
                Request = new() { ClientRequestId = id, Root = root }, Status = status,
                Result = new() { ResultRoots = roots, Outputs = outputs, OutputCount = outputs.Length }
            };
            Equal(Resolve(sourceB), b, top);
            Equal(Resolve(), a, b, top);
            locations.Begin("one", "odb.postprocess.run", root);
            locations.Complete(Snapshot("one", "succeeded", [b], outputB));
            Equal(Resolve(), b);
            locations.Begin("two", "odb.postprocess.run", root);
            Missing(() => Resolve());
            locations.Complete(Snapshot("one", "succeeded", [a], outputA));
            Missing(() => Resolve());
            locations.Complete(Snapshot("two", "succeeded", [a, b, b, unrelated], outputA, outputB));
            Equal(Resolve(), a, b);
            Equal(Resolve(sourceB), b);
            Equal(Resolve(sourceA, sourceB), a, b);
            locations.Begin("region", "odb.postprocess.region", root);
            locations.Complete(Snapshot("region", "succeeded", [top], region));
            Equal(Resolve(sourceA), top);
            locations.SetGroupQueueResult("queue", root, new OdbPostprocessResult
                { ResultRoots = [a, b], Outputs = [outputA, outputB], OutputCount = 2 });
            Equal(Resolve(), a, b);
            Equal(Resolve(sourceB), b);
            locations.SetGroupQueueResult("empty-queue", root, new OdbPostprocessResult());
            Missing(() => Resolve());
            foreach (var state in new[] { "failed", "cancelled" })
            {
                locations.Begin(state, "odb.postprocess.run", root);
                locations.Complete(Snapshot(state, state, [a], outputA));
                Missing(() => Resolve());
            }
            locations.Begin("empty", "odb.postprocess.region", root);
            locations.Complete(Snapshot("empty", "succeeded", [a]));
            Missing(() => Resolve());
            locations.Begin("moved", "odb.postprocess.run", root);
            locations.Complete(Snapshot("moved", "succeeded", [a], Path.Combine(b, "missing")));
            Missing(() => Resolve());
            locations.InputChanged(other);
            Missing(() => locations.Resolve(other, root, [sourceA], Discover()));
            Equal(locations.Resolve(other, other, [sourceA], []).ToArray(), unrelated);
            Equal(Resolve(sourceA), a, top);
            Console.WriteLine("Postprocess result routing checks passed (nested roots, selection, generic extraction, stale requests and existing results)");
        }
        finally { Directory.Delete(temp, recursive: true); }
    }
}
