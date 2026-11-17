using System.Text.RegularExpressions;

namespace AbaqusTools.WinUI.Services;

public sealed record OdbRegionExtractionMethod(string Key, string DisplayName);

public sealed record OdbRegionExtractionEligibility(OdbRegionExtractionMethod? Method, string Message)
{
    public bool CanExtract => Method is not null;
}

/// <summary>Matches the worker's accepted element families, never an object name or geometry.</summary>
public static class OdbRegionExtractionMethods
{
    public static readonly OdbRegionExtractionMethod Beam = new("beam_sections", "梁单元：已存储的 SF/SM 内力");
    public static readonly OdbRegionExtractionMethod Truss = new("truss_reference_area", "钢筋/桁架：S11 × 参考截面积（旧版约定）");
    public static readonly OdbRegionExtractionMethod Solid = new("solid_section", "实体：自由体截面轴力与弯矩");

    public static OdbRegionExtractionEligibility Evaluate(OdbRegionDescriptor? region)
    {
        if (region is null)
            return new(null, "请选择一个实例或单元集。");
        if (region.Kind == "node_set")
            return new(null, "节点集只供浏览。内力提取请选择含单元的实例或单元集。");
        if (region.Kind is not ("instance" or "element_set") || region.ElementCount <= 0)
            return new(null, "请选择含单元的实例或单元集；空对象不能提取内力。");
        if (region.ElementTypes.Count == 0 || region.ElementTypes.Any(pair => pair.Value <= 0)
            || region.ElementTypes.Sum(pair => (long)pair.Value) != region.ElementCount)
            return new(null, "对象的单元类型信息缺失或不完整，请勾选“本次强制重扫”后重新读取结构。");

        var families = region.ElementTypes.Keys.Select(MethodForElementType).ToArray();
        var unsupported = region.ElementTypes.Keys.Where(type => MethodForElementType(type) is null).ToArray();
        if (unsupported.Length > 0)
            return new(null, "当前不支持这些单元类型的内力提取：" + string.Join("、", unsupported)
                + "。请选择仅含支持的实体、桁架或梁单元的对象。");
        if (families.Distinct().Count() != 1)
            return new(null, "所选对象混合了实体、桁架或梁单元，请分别选择同一类单元的集合后提取。");

        var method = families[0]!;
        return new(method, "已按 ODB 实际单元类型确定提取方法。整帧输出不保证所选对象包含所需数据。");
    }

    public static bool IsAllowed(OdbRegionDescriptor? region, string? method) =>
        Evaluate(region).Method is { } available && available.Key == method;

    private static OdbRegionExtractionMethod? MethodForElementType(string type)
    {
        // Keep full-match patterns aligned with region_extract_core.py and region_solid_core.py.
        if (Regex.IsMatch(type, @"\A(?:B(?:21|22|23|31|32|33)(?:H|OS|OSH)?|PIPE(?:21|22|31|32)H?)\z"))
            return Beam;
        if (Regex.IsMatch(type, @"\AT[23]D[23](?:H|T)?\z"))
            return Truss;
        if (Regex.IsMatch(type, @"\AC3D(?:4|6|8|10|15|20|27)[A-Z]*\z"))
            return Solid;
        return null;
    }
}
