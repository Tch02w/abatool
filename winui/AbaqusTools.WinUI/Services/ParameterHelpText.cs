namespace AbaqusTools.WinUI.Services;

/// <summary>Explanations grounded in the current command and extraction behavior.</summary>
internal static class ParameterHelpText
{
    public static string ForTopic(string topic) => topic switch
    {
        "cpu" => "单个求解作业使用的 CPU 数。0 表示不传 cpus 参数，由 Abaqus 使用自身默认配置，不代表使用全部 CPU。\n\n本机上限随 Abaqus 版本变化；与同时运行几个作业是两个设置。",
        "queue-parallel" => "允许同时运行的本机队列作业数。每个作业仍使用各自的 CPU 和内存设置；需要同时运行多个作业且机器资源足够时再增大。",
        "postprocess-parallel" => "同时处理 ODB 的工作数上限，用于并行读取结构和提取结果，上限为本机逻辑线程数。\n\n它不是单个求解作业的 CPU 数；每项工作另占内存，内存不足时应减少。",
        "rebar-count" => "用于核对各水平切面穿过的纵筋数量。0 表示按筛选后的纵筋单元连通关系自动识别。\n\n确认实际数量后可手动填写；此值只作数量核对，不会补加钢筋或改变力的求和。",
        "rebar-tolerance" => "判断纵筋单元是否穿过水平切面、以及切面处端点归属的微小坐标容差。默认 0.0001 mm，需与模型坐标单位一致。\n\n它不是切片厚度，也不是实体截面积分精度。仅在核实坐标误差后调整；过大可能改变参与计算的单元。",
        "image-size" => "像素模式直接指定 PNG 的像素宽高。毫米模式指定 Abaqus 视口尺寸，再按屏幕尺寸输出，不保证固定印刷 DPI。\n\n需要确定导出图片的像素数时，请使用像素模式。",
        "animation-fps" => "所有 GIF 按相同的目标帧率播放。设为 25 帧/秒时，100 个源帧播放 4 秒，50 个源帧播放 2 秒。",
        "animation-duration" => "所有 GIF 每轮播放相同的秒数，适合并排比较不同模型。设为 4 秒时，100 帧平均每秒播放 25 帧，40 帧平均每秒播放 10 帧。每个源帧至少需要 0.01 秒。",
        "rebar-diameter" => "单位为 mm。优先使用 ODB 中的钢筋截面面积；缺失时才按圆截面面积 πd²/4 回退计算轴力。\n\n请核对实际直径；多种直径的模型不能用同一个回退值代表所有钢筋。",
        "prefracture-frame" => "-1 表示按混凝土拉伸损伤与环向覆盖规则，自动选取首次断裂候选的前一帧；未识别到候选时不会自动生成该帧。\n\n手动值是所选起止分析步拼接后的总时程序号，从 0 开始，后续分析步首帧跳过。不是单个分析步内的帧号。",
        "reference-area" => "单位为模型长度单位的平方。留空时逐单元读取 ODB 截面面积；填写后覆盖所选全部桁架单元的面积。\n\n仅在已核实这些单元共用该面积时填写。计算为 S11×参考面积，不等于有限变形下按当前面积计算的轴力。",
        "queue-priority" => "保存作业的优先级标记。当前本机调度按队列顺序和依赖就绪状态启动；需要调整先后时，请移动队列顺序。数值越大不保证越先运行。",
        "ssh-port" => "服务器 SSH 服务监听的端口，通常为 22。只有服务器配置了其他端口时才修改；它不是 Abaqus 的计算端口。",
        _ => string.Empty,
    };
}
