using AbaqusTools.WinUI.Services;

static class OdbRegionExtractionMethodsChecks
{
    public static void Run()
    {
        var checks = 0;
        void Check(bool condition, string message)
        {
            checks++;
            if (!condition) throw new InvalidOperationException(message);
        }
        static OdbRegionDescriptor Region(params string[] types) => new()
        {
            Kind = "element_set", ElementCount = types.Length,
            ElementTypes = types.GroupBy(type => type).ToDictionary(group => group.Key, group => group.Count()),
        };

        foreach (var (key, types) in new[]
        {
            ("beam_sections", new[] { "B21", "B22", "B23", "B31", "B32", "B33", "B31H", "B31OS", "B32OSH", "PIPE21", "PIPE22", "PIPE31", "PIPE32H" }),
            ("truss_reference_area", new[] { "T2D2", "T2D3", "T3D2", "T3D3", "T3D2H", "T3D2T" }),
            ("solid_section", new[] { "C3D4", "C3D6", "C3D8", "C3D8R", "C3D8RH", "C3D10", "C3D10M", "C3D15", "C3D20R", "C3D27" }),
        })
        {
            foreach (var type in types)
            {
                var eligible = OdbRegionExtractionMethods.Evaluate(Region(type));
                Check(eligible.CanExtract && eligible.Method?.Key == key,
                    $"Supported {type} must use {key}");
            }
            Check(OdbRegionExtractionMethods.IsAllowed(Region(types), key),
                $"Different supported element types in one {key} family must remain selectable");
        }

        foreach (var type in new[] { "S4R", "CAX4R", "COH3D8", "T2D4", "T3D", "T3D2X", "T3D2\n", "C3D999", "C3D8+", "B31X", "B31\n", "PIPE41", "Unknown", "c3d8", "" })
        {
            var eligible = OdbRegionExtractionMethods.Evaluate(Region(type));
            Check(!eligible.CanExtract && eligible.Method is null && eligible.Message.Length > 0,
                $"Unsupported element {type} must be blocked with an explanation");
        }

        foreach (var types in new[] { new[] { "B31", "T3D2" }, new[] { "C3D8R", "T3D2" }, new[] { "C3D8R", "B31" }, new[] { "C3D8R", "S4R" } })
        {
            var eligible = OdbRegionExtractionMethods.Evaluate(Region(types));
            Check(!eligible.CanExtract && eligible.Method is null && eligible.Message.Length > 0,
                "Mixed families must not fall back to beam extraction");
        }

        foreach (var region in new OdbRegionDescriptor?[]
        {
            null,
            new() { Kind = "node_set", NodeCount = 2 },
            new() { Kind = "element_set", ElementCount = 0 },
            new() { Kind = "surface", ElementCount = 1, ElementTypes = new Dictionary<string, int> { ["C3D8R"] = 1 } },
            new() { Kind = "element_set", ElementCount = 1 },
            new() { Kind = "element_set", ElementCount = 1, ElementTypes = new Dictionary<string, int> { ["C3D8R"] = 0 } },
            new() { Kind = "element_set", ElementCount = 2, ElementTypes = new Dictionary<string, int> { ["C3D8R"] = 1 } },
        })
        {
            var eligible = OdbRegionExtractionMethods.Evaluate(region);
            Check(!eligible.CanExtract && eligible.Message.Length > 0, "Non-element or incomplete metadata must be explained and blocked");
        }

        var solidNamedBeam = new OdbRegionDescriptor
        {
            Kind = "instance", Name = "PIPE31钢管梁", Instance = "B31工字钢",
            ElementCount = 1, ElementTypes = new Dictionary<string, int> { ["C3D8R"] = 1 },
        };
        Check(OdbRegionExtractionMethods.IsAllowed(solidNamedBeam, "solid_section"),
            "Whole-instance geometry names must not override actual solid element types");
        Check(!OdbRegionExtractionMethods.IsAllowed(solidNamedBeam, "beam_sections"),
            "A stale or manually mismatched method must not submit");
        Check(!OdbRegionExtractionMethods.IsAllowed(Region("T3D2"), "solid_section"),
            "Changing object must not retain the former solid method");
        Check(!OdbRegionExtractionMethods.IsAllowed(Region("S4R"), "beam_sections"),
            "An unsupported object must never retain the former beam method");
        Check(!OdbRegionExtractionMethods.IsAllowed(Region("C3D8R"), null), "Missing method must not submit");
        Console.WriteLine($"{checks} region method eligibility checks passed");
    }
}
