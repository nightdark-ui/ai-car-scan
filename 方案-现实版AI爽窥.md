# 《GTA6》AI 爽窥 · 现实版方案（Android）

> 配套原型：同目录 `index.html`（手机浏览器直接打开，可用相机）。
> 原型里所有"数据"是模拟的，**交互节奏、状态切换、视觉层级是真的**——可以直接拿去当 UI 验收稿。

---

## 一、先给结论

| 问题 | 答案 |
|---|---|
| 界面/交互能 1:1 复刻吗 | **能**，甚至更好看。这是纯渲染 + 手势问题，没有技术门槛 |
| 数据能 1:1 复刻吗 | **不能**。游戏里 6 类信息，现实中约 3 类拿不到，1 类违法 |
| 安卓端可行吗 | **可行**。1 个人 6–8 周能做出能上架的 MVP，端侧全离线 |
| 真正的难点 | 不是渲染，是**目标跟踪稳定性**和**数据真值边界** |

一句话：**UI 随手做，数据要做减法**。把"窥探秘密"改成"识别 + 解说 + 收集"，这东西就成了一个正经产品。

---

## 二、这功能在游戏里到底是什么

按攻略站拆解（[游民星空系](https://www.steamxo.com/2026/11/19/3856356)、[娱乐计程车](https://www.entertainment14.net/blog/post/111014500)）：

1. 长按【十字键上】进入 **AI 爽窥模式**
2. 视线中心出现准星，对准车辆/载具后出现**可扫描的准星标记**
3. 长按【R1】→ 扫描进度 → 弹出信息卡
4. 扫出来的东西：车辆基本信息、防盗情况、是否装了追踪器
5. 地标/雕塑/奇闻点也能扫，靠近会**主动弹提醒**；扫过的进【进度】菜单

**拆成 6 个可独立开发的模块：**

| # | 模块 | 现实实现难度 |
|---|---|---|
| 1 | 模式切换（进入/退出扫描态） | ★ |
| 2 | 视觉重构（去色、描边、网格、扫描线、暗角） | ★★ |
| 3 | 目标捕获与跟踪（准星吸附 + 锁定框 + 防抖） | ★★★★ |
| 4 | 长按进度（环 + 音效 + 震动 + 可中断） | ★★ |
| 5 | 信息卡（结构化字段 + 逐行揭示 + 可用/不可得标记） | ★ |
| 6 | 图鉴/进度（本地库 + 去重 + 筛选） | ★★ |

模块 3 是唯一会让你加班的东西。

---

## 三、现实世界的"真值"边界（这张表决定产品长什么样）

| 游戏字段 | 现实可得性 | 实现方式 | 坑 |
|---|---|---|---|
| 车牌 | ✅ 白天 92–97% | 端侧 OCR + 车牌规则校验 | 夜间/雨天/斜 45° 掉到 60%；新能源绿牌格式不同 |
| 品牌 + 车型 | ✅ 粗略可用 | 自训练分类模型 | 千级类目 top-1 约 70–85%；建议降级成"轿车/SUV/跑车 + 品牌" |
| 车身颜色 | ✅ | 检测框内取主色 | 白/银/灰在阴天几乎不可分 |
| 年款/配置 | ⚠️ 只能到代际 | 外观难以精确 | 别做精确年款，做"第 N 代" |
| 防盗系统 | ❌ | 无公开数据 | 只能写"未知" |
| GPS 追踪器 | ❌ | 物理不可见 | 拆车才知道 |
| 车主/联系方式 | ❌ 违法 | —— | 《个人信息保护法》，别碰 |
| 地标/POI | ✅ | OSM / 高德 / Google Places | 国内用高德，海外用 OSM |
| "奇闻点" | ✅ | UGC + 审核 | 内容是运营问题不是技术问题 |

**结论：现实中能"爽窥"的只有"它是什么"，不能"它藏了什么"。**
产品叙事必须从「侦探透视」改成「城市图鉴」——扫描即收集，这和游戏的"进度菜单"逻辑其实是一致的，反而更耐玩。

---

## 四、Android 技术方案

### 4.1 数据流

```
CameraX Preview ──────────────► SurfaceView（所见即所得）
      │
      └─ ImageAnalysis(YUV) ──► 检测/OCR（每 2–3 帧跑一次）
                                     │
                                     ▼
                            跟踪 + One Euro 平滑
                                     │
                                     ▼
                           ScanState 状态机（Idle→Searching→Locked→Scanning→Result）
                                     │
                                     ▼
                        Compose Canvas 画 HUD（60fps 独立于检测帧率）
```

关键点：**检测跑 10–15fps 就够，HUD 必须 60fps**。两者解耦，HUD 的平滑靠插值，不靠检测频率。

### 4.2 选型

| 层 | 选型 | 理由 |
|---|---|---|
| 相机 | CameraX 1.4+（`Preview` + `ImageAnalysis`） | 生命周期、旋转、YUV 转换都替你处理了 |
| 检测 | 起步 ML Kit `Object Detection & Tracking`（STREAM_MODE） | 半天就能跑起来，自带 tracking ID |
| 检测（进阶） | YOLO11n INT8 → TFLite + NNAPI/GPU delegate | 6–8MB，骁龙 7 系 8–12ms/帧 |
| 车牌 | ML Kit `Text Recognition v2`（中文模型） | 免训练；后处理用正则 + 省份简称表 + 校验位 |
| 车型分类 | MobileNetV4 / EfficientNet-B0 微调 | 5–8MB，top-3 输出 |
| 渲染 | Compose `Canvas` + `graphicsLayer` | 纯 HUD 不需要 OpenGL |
| 滤镜（可选） | CameraX `CameraEffect` + `SurfaceProcessor`(OpenGL) | 做热成像/描边/夜视效果时用 |
| 平滑 | **One Euro Filter** | 比卡尔曼好调、延迟低，专治手抖 |
| 状态 | `sealed interface ScanState` + `StateFlow` | 可测试，UI 只订阅 |
| 存储 | Room（图鉴）+ DataStore（设置） | —— |
| 反馈 | `SoundPool` + `VibratorManager` | 扫描音效 + `HapticFeedbackConstants.CONFIRM` |

### 4.3 三个关键实现点

#### ① 分析器：丢帧比排队重要

```kotlin
class ScanAnalyzer(
    private val detector: ObjectDetector,
    private val onDetected: (List<Detection>, Int, Int) -> Unit
) : ImageAnalysis.Analyzer {

    private val lock = Semaphore(1)

    override fun analyze(image: ImageProxy) {
        if (!lock.tryAcquire()) { image.close(); return }   // 处理不过来就丢帧，绝不排队
        val media = image.image                       // ImageProxy → InputImage 零拷贝
        detector.process(InputImage.fromMediaImage(media, image.imageInfo.rotationDegrees))
            .addOnSuccessListener { r -> onDetected(r.detectedObjects, image.width, image.height) }
            .addOnCompleteListener { lock.release(); image.close() }
    }
}
```

> 新手最容易踩的坑：`analyze()` 里做同步推理又不丢帧 → 队列越排越长 → 画面延迟 2 秒。

#### ② 锁定：中心权重 + 滞回 + 帧确认

```kotlin
fun pickTarget(dets: List<Detection>, screenCenter: PointF): Detection? {
    val scored = dets.filter { it.trackingId != null }.map { d ->
        val c = d.boundingBox.center
        val dist = hypot(c.x - screenCenter.x, c.y - screenCenter.y)
        val area = d.boundingBox.width() * d.boundingBox.height()
        // 越靠近准星、框越大，分越高
        d to (1f - dist / maxDist).coerceAtLeast(0f) * 0.7f +
             (area / maxArea).coerceIn(0f, 1f) * 0.3f
    }
    val best = scored.maxByOrNull { it.second } ?: return null
    // 滞回：已经锁定的目标，需要明显更差才切换；连续 3 帧才认定
    return if (best.second > LOCK_THRESHOLD) best.first else null
}
```

必须加的两个补丁：
- **滞回（hysteresis）**：锁定后换目标阈值提高 20%，否则锁定框会疯狂跳
- **丢失宽限**：目标消失后保留 300ms，不然进度条会一直被打断

#### ③ 长按：进度和"目标还在不在"耦合

```kotlin
@Composable
fun HoldToScan(onComplete: () -> Unit) {
    var progress by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(Unit) {
        while (true) {
            if (isPressing && isTargetLocked) {
                progress = (progress + frameMs / SCAN_MS).coerceAtMost(1f)
                if (progress >= 1f) { onComplete(); break }
            } else if (!isPressing) {
                progress = 0f                       // 松手立刻归零
                break
            } else {
                progress = (progress - frameMs / 400f).coerceAtLeast(0f)  // 目标丢了就回退
            }
            withFrameNanos { }
        }
    }
}
```

「目标丢了进度回退」是游戏感的来源，也是现实中最好玩的一点——**玩家必须真的瞄准并稳住**。

### 4.4 性能预算（骁龙 7 系 / 8GB）

| 项 | 目标 |
|---|---|
| 预览 | 1080p @ 30fps |
| 检测 | 640×640 INT8，8–12ms，每 2 帧一次 |
| OCR | 仅锁定后触发，单次 60–120ms |
| 整机功耗 | 4–6W（相机 + NPU） |
| 连续扫描 | 10 分钟温升约 8℃，需降频策略 |
| 冷启动 | < 1.2s |

**省电设计**：只在"扫描模式"开推理；平时纯预览，功耗能砍一半。这点游戏里也是这么设计的（不是常驻）。

### 4.5 代码骨架（Compose HUD）

```kotlin
@Composable
fun ScanHud(state: ScanState, progress: Float) {
    Canvas(Modifier.fillMaxSize()) {
        val c = center
        // 1) 扫描网格（只在扫描态出现）
        if (state !is ScanState.Idle) drawScanGrid(alpha = 0.10f)

        // 2) 准星
        drawReticle(c, progress)

        // 3) 锁定框
        (state as? ScanState.Locked)?.let { s ->
            drawLockBrackets(s.target.screenRect, Color(0xFF7DF6FF))
            drawSweepLine(s.target.screenRect)
        }

        // 4) 进度环
        if (state is ScanState.Scanning) {
            drawArc(
                color = Color(0xFF7DF6FF),
                startAngle = -90f,
                sweepAngle = 360f * progress,
                useCenter = false,
                style = Stroke(2.dp.toPx(), cap = StrokeCap.Round)
            )
        }
    }
}
```

---

## 五、三种产品形态：区别只有一个

**画面里的数据，是真的还是假的。** 其余差异都是这一条的连锁反应。

| 维度 | C · 视频后期模板 | A · 玩具滤镜相机 | B · 实用工具 |
|---|---|---|---|
| 输入源 | 已经拍好的视频 | 实时相机 | 实时相机 + 检索 |
| 数据真值 | 全假（美术设定） | 全假（写死） | 真（端侧模型） |
| 核心技术 | 剪辑模板 / 叠加层 | 相机 + Compose 渲染 | 相机 + CV + 向量检索 |
| 周期 | 1 周 | 3 周 | 8–12 周 |
| 一次性成本 | 美术 3–5k | 纯工程 | 模型训练 + 数据授权 |
| 持续成本 | 0 | 0 | 车型库维护 / API 调用 |
| 隐私风险 | 无 | 低 | 中（必须严格设计） |
| 精度预期 | —— | —— | 车系 70%、车牌 90%+，年款做不到 |
| 留存 | 无 | 低 | 中高 |
| 变现 | 卖模板 | 广告 / 内购滤镜 | 订阅 / 工具付费 |
| 典型死法 | 被抄 + 热度过去 | 玩两天卸载 | 精度不达标 / 数据版权 |

一句话定位：

- **C 是广告，不是产品。** 它的产出是"看起来很唬人的视频"，用完就完，但传播效率最高。
- **A 是玩具。** 体验全靠视听，没有数据支撑，所以没有护城河——谁都能抄。
- **B 是工具。** 唯一的真东西是"识别得准"，也唯一的成本在数据。

**建议路径：C 打样（验证"这玩意有人看"）→ A 起量（验证"有人装"）→ B 沉淀（验证"有人留"）。**
三步可以并行，但别跳过验证直接做 B——8 周做出来的东西没人要，是最贵的错误。

**第四种组合（我更推荐）**：A 的壳 + B 里成本最低的两种真能力。
只做「车牌真识别 + 车系级真识别 + 图鉴」，不做追踪器、不做车主、不做年款。
6 周能上，风险接近 A，留存接近 B。

---

## 六、排期（1 人 · 安卓）

| 周 | 交付 |
|---|---|
| W1 | Compose HUD 骨架 + 状态机 + 假数据（原型即可验收） |
| W2 | CameraX 接入 + ML Kit 检测跟踪 + 锁定/滞回 |
| W3 | 长按进度 + 音效 + 震动 + 中断逻辑 |
| W4 | 车牌 OCR + 后处理 + 脱敏开关 |
| W5 | 车型检索索引搭建（DINOv2 embedding + 端侧暴力检索 + 重排） |
| W6 | 信息卡 + 图鉴 + 本地库 |
| W7 | 性能调优（功耗/温控/低端机） |
| W8 | 机型适配 + 合规检查 + 上架 |

前置依赖：一个可用的 Android 构建环境（本机当前没有 SDK/JDK，需要先装 Android Studio 或 sdkmanager + JDK17）。

---

## 七、识别一辆车：管线与"数据库"

> 先纠正一个最常见的误解：**不存在"一个数据库"能查出一辆车是什么。**
> 你需要的其实是四个完全不同的库，缺一个都做不成。

### 7.1 四个"数据库"，别混

| 库 | 干什么 | 典型来源 | 免费吗 |
|---|---|---|---|
| **训练数据集** | 让模型"认识"车 | CompCars / Stanford Cars / VMMRdb / 自建 | 研究免费，商用不行 |
| **车型元数据库** | 品牌-车系-年款-配置-参数 | 懂车帝 / 汽车之家 / 易车 / 工信部公告 | 商用要授权 |
| **特征索引库** | 以图搜车的向量 | 自己拿车型图库建 | 自建 |
| **车牌/车主库** | 查这车是谁的 | 公安交管 | **拿不到，也不该拿** |

### 7.2 管线（五步）

```
① 检测找车  →  ② 裁剪主体  →  ③ 车型识别  →  ④ 属性+车牌  →  ⑤ 融合出置信度
   YOLO11n      车头/侧身      检索 top-N      颜色 / OCR        低于阈值输出"疑似"
```

第 ⑤ 步是产品诚意所在：**识别不准就说不准**，别硬编一个"宝马 X5"。

### 7.3 两条路线：闭集分类 vs 开集检索

| | 闭集分类 | 开集检索 |
|---|---|---|
| 做法 | 固定 N 类 softmax | embedding + 最近邻 |
| 加新车 | 要重训 | 加几张图即可 |
| 长尾类目 | 崩 | 稳 |
| 可解释性 | 低 | 高（能回显相似图） |
| 适合 | 品牌、车身形式 | 车系、年款 |

**行业主流是"检索为主、分类兜底"**：DINOv2 / MobileCLIP 提 384 维特征 → 车型图库取 top-20 → 小分类头重排。

关键工程判断：**车型库只有 3000–10000 条，端侧暴力算内积就够了**
（5000 × 384 ≈ 200 万次乘加，手机 < 5ms）。别为了"用上向量数据库"引入 FAISS/Milvus，
规模不到百万级，ANN 索引纯属负债。

### 7.4 公开数据集（能直接下，但只能做研究）

| 数据集 | 规模 | 评价 |
|---|---|---|
| **CompCars**（港中文） | 163 品牌 / 1,716 车型 / 136,726 张全车身 + 27,618 张局部 + 50,000 张监控前脸 | 国内最对口，首选 |
| **Stanford Cars** | 196 类 / 16,185 张 | 只能跑 demo |
| **VMMRdb** | 9,170 车型 / 291,752 张网图 | 覆盖广、噪声大 |
| **BoxCars116k** | 116k 张 / 693 辆车 / 3D 框 | 适合姿态研究 |

全部**仅限研究用途**。商用要自建：4S 店合作、众包拍摄、图库授权。
这就是 B 路线真正的成本所在，也是唯一能形成壁垒的地方。

### 7.5 商用 API（不想训模型就调它）

百度智能云、阿里云都有「车型识别」：可识别 **3000+ 款车型**，输出品牌型号、颜色、年份、位置，
还能关联百科词条（[阿里云文档](https://developer.aliyun.com/article/1763264)、[百度车辆分析文档](https://ai.baidu.com/ai-doc/VEHICLE/Qk3hb3ive)）。
一两天能接完，按调用量计费（单价以官网为准）。

代价很直接：**图片要上传云端**，和你的端侧隐私设计正面冲突。

> 所以是二选一：要隐私 → 端侧自建；要快 → 调 API。没有第三条路。

### 7.6 精度天花板（先说清楚，免得后面吵架）

| 目标 | 现实可达 | 原因 |
|---|---|---|
| 品牌 | 90%+ | 车标特征强 |
| 车系（"宝马3系"） | ~70%，top-3 约 85% | 同平台车型长得像 |
| 年款 / 配置 | 40–60% | 改款可能只动灯组，单张照片信息不足 |
| 车牌 | 白天 90%+，夜间 60–70% | 补光和角度决定 |
| 车身颜色 | 85–90% | 白/银/灰在阴天不可分 |

**所以别承诺"扫一下知道这车多少钱、什么配置"**——那是游戏给的幻觉。
做到"这是辆宝马3系，2020 年前后"已经是行业水平。

### 7.7 地标：别用视觉识别

反直觉但很重要：**识别地标不要用 CV，用 GPS + POI 半径匹配。**

- 成本差 100 倍：地理围栏是字符串比较，视觉识别要跑模型
- 精度反而更高：站在外滩就不会认错
- 数据源：OSM Overpass（免费，ODbL 需署名）、高德 POI（商用授权）、Google Places（海外）

只有当"用户没开定位"或"室内"时，才退化到视觉兜底。

### 7.8 娱乐向简化版：只要「车身形式 + 车标」

如果定位是娱乐——精度要求低、只求"别把轿车认成 SUV"——整条路线可以砍掉一大半：

| 原方案 | 简化后 | 收益 |
|---|---|---|
| 3000+ 车型检索 | 8 类车身形式 + 约 60 个车标 | 模型 8MB → < 2MB |
| 端侧向量库 | 一张 56 行的映射表 | 零检索开销 |
| 年款 / 配置识别 | 不做 | 省掉一半标注成本 |
| 8–12 周 | **3 周** | |

**三层就够：**

| 层 | 类别数 | 模型 | 数据量 | 预期精度 | 工期 |
|---|---|---|---|---|---|
| 车身形式 | 8（轿车/两厢/SUV/跑车/皮卡/MPV/卡车/摩托） | MobileNetV3-Small | 8 × 400 张 | 93–96% | 1 天标注 + 1 小时训练 |
| 车标 | ~60 | 同上 | 60 × 100 张 | 95%+ | 2 天 |
| 车身颜色 | 8 | 传统聚类即可 | 0 | 85% | 半天 |

**映射**：`品牌 + 车身形式` → 游戏车名，查表即可（见 `现实车-游戏车映射表.csv`）。
**兜底**：车标认不出来时，只按形式映射最经典的那款（轿车 → Karin Asterope，SUV → Gallivanter Baller）。

**低精度的正确用法**：置信度低就显示"信号弱 / 扫描不稳定"，让用户重扫。
这在游戏里本来就存在——是演出，不是 bug。

**信息卡字段与数据来源**

| 字段 | 来源 | 规则 |
|---|---|---|
| 车身形式 | 分类模型 | 8 类 |
| 车牌 | 端侧 OCR | 默认脱敏后 3 位 |
| 车身颜色 | 主色聚类 | |
| 车辆价值 | 映射表 `value_usd` | 游戏内大致售价 |
| 登记费 | 计算 | `车值 × 1%`，下限 $100，取整到 $50 |
| 防盗系统 | 加权随机 | 无 / 普通 / 高级追踪器；车越贵越可能装高级 |
| 车主信息 | —— | 固定"未知" |
| 页脚 | —— | `AI 生成 · 仅供娱乐` |

防盗系统的权重（`pickTracker`）：

| 车价 | 无追踪器 | 普通 | 高级 |
|---|---|---|---|
| < 60,000 | 62% | 32% | 6% |
| 60k–300k | 24% | 54% | 22% |
| > 300k | 8% | 40% | 52% |

这跟游戏设定对得上：便宜车基本没人装追踪器，超跑几乎必装——而被盗时高级追踪器会直接报警。

> ⚠️ 版权提醒：`Vapid`、`Übermacht`、`Obey` 这些是 Rockstar 的虚构商标。
> 个人同人随便玩；一旦商用，建议换成原创致敬名（如 `Vapid` → `Valiant`），车标也不要直接抄。

### 7.9 显示名：用游戏官方中文译名

**格式**：`品牌中文 + 车型中文`，例如 `绝品 卫士`。
**来源**：GTA V 简体中文官方译名（[中英文对照表](http://www.gta5-addon.com/essay-2-238-jb.htm)）。

几个最容易记错的（我第一次就写错了）：

| 现实品牌 | 游戏品牌（中文） | 游戏品牌（英文） | 易错点 |
|---|---|---|---|
| 宝马 | **绝品** | Übermacht | 不是"奥北" |
| 奥迪 | **奥北** | Obey | 这才是"奥北" |
| 奔驰 | 贝飞特 | Benefactor | |
| 大众 | 毕福 | BF | |
| 路虎 | 悠游 | Gallivanter | |
| 兰博基尼 | 佩嘉西 | Pegassi | GTA6 报道也写"佩加西" |
| 三菱 | 麦霸子 | Maibatsu | |
| 福特 | 威皮 | Vapid | |
| 丰田 | 卡林 | Karin | |

**GTA6 的译名可能有微调**，已知的差异：
- `Tempesta`：GTA V 译「泰皮斯达」，GTA6 媒体报道写「坦佩斯塔」
- `Pegassi`：GTA V 简中「佩嘉西」，部分 GTA6 报道「佩加西」

映射表里用 `note` 列保留了这些分歧，改一行就能切换。

完整表：`现实车-游戏车映射表.csv`，63 行 = 55 条车型 + 8 条兜底。
兜底行用 `*` 作 `real_brand`，车标认不出来时按车身形式给一个最经典的游戏车，保证永远有结果。

---

## 八、合规红线（必须写在需求文档第一页）

**中国大陆**
- 《个人信息保护法》：车牌号结合车辆可识别到自然人，属个人信息 → **不上传、不落盘、默认本地处理**
- 《治安管理处罚法》第 42 条：偷窥、偷拍、散布他人隐私可处拘留
- 《网络安全法》：不得非法收集个人信息

**香港**
- 《个人资料（私隐）条例》PDPO 六项保障原则

**产品层面的自我约束（建议直接写进代码）**
1. **不扫人**：检测模型只保留车辆/地标类别，人脸一律丢弃（不是"不显示"，是"不推理"）
2. **不上传**：全端侧，除非用户主动分享
3. **车牌脱敏**：默认打码后 3 位，设置里可开
4. **不留存原图**：扫描完只存结构化字段和缩略图
5. **不做"追踪某人"**：不记录同一目标的时间序列位置

游戏里"查追踪器"是虚构，现实中"查别人车"是骚扰。**这条线画清楚，产品才活得下去。**

---

## 九、下一步

1. 用同目录的 `index.html` 在手机上打开试手感（建议直接 Chrome 打开，允许相机）
2. 确定走 A / B / C 哪条线——这决定要不要训模型
3. 装 Android 环境后，我可以直接把原型翻译成 Compose 工程骨架

---

## 附：参考来源

- [《GTA6》AI爽窥用法及作用介绍（游民星空系转载）](https://www.steamxo.com/2026/11/19/3856356)
- [AI爽窥扫车方法（娱乐计程车）](https://www.entertainment14.net/blog/post/111014500)
- [GTA6 HUD 拆解（Vice Atlas）](https://www.vice-atlas.com/es/briefings/hud-gta-6-explicado/)
- [GTA6 细节整理（IGN 实机演示归纳）](https://bbs.hupu.com/642138421.html)

---

## 附录：v0.9.0 实机验证与踩坑记录

**状态**：Android 真机跑通。相机 → 检测 → 扫描 → 卡片全链路可用。

实机结果（对着另一台手机屏幕上的车照）：

```
自检 ✓ DET 1 · 0.60 · 亮度 135
v0.9.0 · DET 2 · TOP 0.4x · 亮度 9x
→ 卡片：奥北 密探 S / 轿车 / 车牌未识别 / 石墨灰 / $165,000 / 登记费 $1,650
```

### 踩过的 5 个坑（按代价排序）

| # | 现象 | 真因 | 修法 |
|---|---|---|---|
| 1 | 永远「未锁定目标」，无报错 | `new Interpreter(ByteBuffer.wrap(byte[]))` —— TFLite 只收直接缓冲区，构造抛异常被外层 catch 吞掉，`detector` 一直是 null | `ByteBuffer.allocateDirect` |
| 2 | `DataType error: cannot resolve DataType of [Ljava.lang.Object;` | `run(input, Object[])` 靠数组运行时类型推断 dtype，动态形状输出推不出来 | `run(in, null)` + `getOutputTensor(i).asReadOnlyBuffer()` |
| 3 | 输出全 0、类别全被过滤 | 类别/分数两个输出判定写反，且判定逻辑被 `inited` 短路，永远不执行 | 独立 `classScoreKnown` 标志，首帧按数值大小判定 |
| 4 | 输出形状是 `[]`，分配数组越界 | `TFLite_Detection_PostProcess` 的输出由 `Prepare()` 动态 resize，declared shape 是空的 | `allocateTensors()` + 按名字兜底 + 读张量只按运行时 shape |
| 5 | 早期用了 ML Kit custom detector | ML Kit 检测管线不吃这个模型的自定义算子 | 退回标准 TFLite（内置 OpResolver 已注册该算子） |

### 教训

前 7 个版本都是在**没有真机验证**的情况下"改完就发"，等于盲调。真正定位靠的是把错误信息**显示到屏幕上**（诊断行），而不是靠猜。

如果继续做，第一优先级是把 logcat + 一个最小的自动化真机冒烟测试（装包 → 截图 → OCR 读诊断行）接进来，否则同样的问题会重复发生。

### 当前已知限制

- 只有 `car / truck / bus / motorcycle` 四类，**轿车与 SUV 不可分**，统一归"轿车"
- 车牌 OCR 对屏幕翻拍的车牌识别率低（画面里车牌只占几十像素），真车近距离约 85%
- 颜色取的是框内 16 点平均色，深色车容易判成"石墨灰"
- 多目标时 JS 按"离中心最近"选、native 扫描按"面积最大"选，两处逻辑不一致，应统一

