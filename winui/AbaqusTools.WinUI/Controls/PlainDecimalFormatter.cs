using System.Globalization;
using Windows.Globalization.NumberFormatting;

namespace AbaqusTools.WinUI.Controls;

/// <summary>Direct decimal entry without exposing binary floating-point tails.</summary>
public sealed class PlainDecimalFormatter : INumberFormatter2, INumberParser
{
    public string FormatDouble(double value) => value.ToString("0.##########", CultureInfo.CurrentCulture);
    public string FormatInt(long value) => value.ToString(CultureInfo.CurrentCulture);
    public string FormatUInt(ulong value) => value.ToString(CultureInfo.CurrentCulture);
    public double? ParseDouble(string text) => double.TryParse(text, NumberStyles.Float,
        CultureInfo.CurrentCulture, out var value) && double.IsFinite(value) ? value : null;
    public long? ParseInt(string text) => long.TryParse(text, out var value) ? value : null;
    public ulong? ParseUInt(string text) => ulong.TryParse(text, out var value) ? value : null;
}
