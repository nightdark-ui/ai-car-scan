# -*- coding: utf-8 -*-
"""从 index.html 生成网页真识别版 docs/index.html"""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(ROOT, "index.html")
dst_dir = os.path.join(ROOT, "docs")
os.makedirs(dst_dir, exist_ok=True)

html = open(src, encoding="utf-8").read()


def rep(old, new, required=True):
    global html
    if old not in html:
        if required:
            raise SystemExit("NOT FOUND:\n" + old[:160])
        return
    html = html.replace(old, new, 1)


# 1) 模式标志
rep("  var NATIVE = location.search.indexOf('native=1') >= 0;",
    "  var NATIVE = false;\n  var LIVE = true;")

# 2) busy 元素样式
rep("/* 原生相机模式：WebView 透明，相机画面来自底层 PreviewView */",
    """#busy{position:absolute;left:50%;top:52%;transform:translate(-50%,-50%);
  font-size:13px;letter-spacing:.08em;color:var(--cyan);text-align:center;
  max-width:82vw;line-height:1.8;pointer-events:none;transition:opacity .3s;text-shadow:0 0 18px rgba(0,0,0,.9)}

/* 原生相机模式：WebView 透明，相机画面来自底层 PreviewView */""")

# 3) busy DOM
rep('  <div class="vignette"></div>',
    '  <div id="busy"></div>\n  <div class="vignette"></div>')

# 4) 锁定判定
rep("    if (NATIVE && !nativeTarget) { showToast('未锁定目标'); return; }",
    "    if ((NATIVE || LIVE) && !nativeTarget) { showToast('未锁定目标'); return; }")

rep("""    var showBox = NATIVE
      ? (!!nativeTarget && next !== 'result')
      : (next === 'scanning' || next === 'locked');""",
    """    var showBox = (NATIVE || LIVE)
      ? (!!nativeTarget && next !== 'result')
      : (next === 'scanning' || next === 'locked');""")

# 5) finishScan 增加 LIVE 分支
rep("    if (NATIVE){\n      // 交回原生层",
    """    if (LIVE){
      setMode('result');
      sfx('stop');
      liveCapture();
      return;
    }

    if (NATIVE){
      // 交回原生层""")

# 6) 桥接守卫
rep("  function onNativeDetect(boxes){\n    if (!NATIVE) return;",
    "  function onNativeDetect(boxes){\n    if (!NATIVE && !LIVE) return;")
rep("  function onNativeResult(res){\n    if (!NATIVE) return;",
    "  function onNativeResult(res){\n    if (!NATIVE && !LIVE) return;")

# 7) 指针
rep("    if (!NATIVE) moveTo(p.x, p.y);",
    "    if (!NATIVE && !LIVE) moveTo(p.x, p.y);")
rep("    if (!scanArmed || mode === 'idle' || NATIVE) return;",
    "    if (!scanArmed || mode === 'idle' || NATIVE || LIVE) return;")

# 8) 开场按钮
rep("""  document.getElementById('enter').addEventListener('click', function(){
    intro.classList.add('hide');
    startCamera().catch(function(){
      showToast('未获得相机权限 · 使用演示背景');
    });
  });""",
    """  document.getElementById('enter').addEventListener('click', function(){
    intro.classList.add('hide');
    startLive();
  });""")

# 9) 标题
rep("<title>AI 爽窥 · 现实版 HUD 原型</title>",
    "<title>AI 车扫 · 现实版 GTA 扫描</title>")

LIVE_JS = r"""
  /* ---------------- 网页真识别（MediaPipe Tasks / WASM） ---------------- */
  var mpDetector = null;
  var MAPPING = [];
  var lastDet = 0;

  function setBusy(t){
    var el = document.getElementById('busy');
    if (!el) return;
    el.textContent = t || '';
    el.style.opacity = t ? '1' : '0';
  }

  function parseMapping(txt){
    var lines = txt.replace(/^\uFEFF/, '').split(/\r?\n/);
    var out = [];
    for (var i = 1; i < lines.length; i++){
      if (!lines[i].trim()) continue;
      var f = lines[i].split(',');
      if (f.length < 9) continue;
      var v = parseInt(f[7], 10);
      if (isNaN(v)) continue;
      out.push({ brand: f[0].trim(), body: f[1].trim(), display: f[2].trim(), value: v });
    }
    return out;
  }

  function pickRow(body, seed){
    var list = MAPPING.filter(function(r){ return r.body === body && r.brand !== '*'; });
    if (!list.length) list = MAPPING.filter(function(r){ return r.body === body; });
    if (!list.length) list = MAPPING.filter(function(r){ return r.display; });
    if (!list.length) return null;
    return list[Math.abs(seed) % list.length];
  }

  function bodyFromLabel(label){
    if (label === 'truck') return '皮卡';
    if (label === 'bus') return 'MPV';
    if (label === 'motorcycle') return '摩托';
    return '轿车';
  }

  function feeOf(v){ return Math.max(100, Math.round(v * 0.01 / 50) * 50); }
  function moneyOf(n){ return '$' + n.toLocaleString('en-US'); }

  var PALETTE = [
    ['珍珠白', [238,238,236]], ['厂矿银', [176,180,185]], ['石墨灰', [116,120,124]],
    ['曜石黑', [28,30,34]], ['竞速红', [186,32,44]], ['深海蓝', [28,70,150]],
    ['竞速黄', [226,190,44]], ['森林绿', [34,128,82]]
  ];

  function sampleColor(box){
    try {
      var vw = video.videoWidth, vh = video.videoHeight;
      var c = document.createElement('canvas');
      c.width = vw; c.height = vh;
      var g = c.getContext('2d');
      g.drawImage(video, 0, 0, vw, vh);
      var l = box.l * vw, t = box.t * vh, r = box.r * vw, b = box.b * vh;
      var R = 0, G = 0, B = 0, n = 0;
      for (var i = 1; i <= 4; i++){
        for (var j = 1; j <= 4; j++){
          var x = Math.floor(l + (r - l) * i / 5);
          var y = Math.floor(t + (b - t) * j / 5);
          if (x < 0 || y < 0 || x >= vw || y >= vh) continue;
          var px = g.getImageData(x, y, 1, 1).data;
          R += px[0]; G += px[1]; B += px[2]; n++;
        }
      }
      if (!n) return '未知';
      R /= n; G /= n; B /= n;
      var best = '未知', bd = 1e9;
      for (var k = 0; k < PALETTE.length; k++){
        var p = PALETTE[k][1];
        var dr = R - p[0], dg = G - p[1], db = B - p[2];
        var d = dr * dr * 0.3 + dg * dg * 0.6 + db * db * 0.1;
        if (d < bd){ bd = d; best = PALETTE[k][0]; }
      }
      return best;
    } catch (e) { return '未知'; }
  }

  function liveCapture(){
    var t = nativeTarget;
    if (!t){ onNativeResult({ ok: false, reason: 'no_target' }); return; }
    var body = bodyFromLabel(t.label);
    var color = sampleColor(t);
    var seed = Math.floor(performance.now());
    var row = pickRow(body, seed);
    onNativeResult({
      ok: true,
      kind: 'VEHICLE · SCANNED',
      title: row ? row.display : '未知',
      sub: 'SCAN ' + (1000 + (seed % 9000)) + ' · 置信度 ' + Math.round((t.s || 0) * 100) + '%',
      rows: [
        ['车身形式', body],
        ['车牌', '网页版暂不支持'],
        ['车身颜色', color],
        ['车辆价值', row ? moneyOf(row.value) : '—', 'money'],
        ['登记费', row ? moneyOf(feeOf(row.value)) : '—'],
        ['防盗系统', '无法获取'],
        ['车主信息', '未知']
      ]
    });
  }

  function liveLoop(){
    if (!mpDetector || !video.videoWidth){ requestAnimationFrame(liveLoop); return; }
    var now = performance.now();
    if (now - lastDet > 110){
      lastDet = now;
      try {
        var res = mpDetector.detectForVideo(video, now);
        var boxes = [];
        var list = res.detections || [];
        for (var i = 0; i < list.length && boxes.length < 3; i++){
          var d = list[i];
          var cat = d.categories && d.categories[0];
          if (!cat) continue;
          var name = String(cat.categoryName || '').toLowerCase();
          if (['car','truck','bus','motorcycle','vehicle'].indexOf(name) < 0) continue;
          var bb = d.boundingBox;
          boxes.push({
            l: bb.originX / video.videoWidth,
            t: bb.originY / video.videoHeight,
            r: (bb.originX + bb.width) / video.videoWidth,
            b: (bb.originY + bb.height) / video.videoHeight,
            label: (name === 'vehicle') ? 'car' : name,
            s: cat.score
          });
        }
        onNativeDetect(boxes);
      } catch (e) {}
    }
    requestAnimationFrame(liveLoop);
  }

  function createDetector(){
      return import('./vendor/vision_bundle.mjs')
      .then(function(mod){
        return mod.FilesetResolver
          .forVisionTasks('./vendor/wasm')
          .then(function(fs){ return { mod: mod, fs: fs }; });
      })
      .then(function(ctx){
        var opts = {
          baseOptions: { modelAssetPath: 'efficientdet_lite0.tflite', delegate: 'CPU' },
          runningMode: 'VIDEO',
          scoreThreshold: 0.3,
          maxResults: 5
        };
        return ctx.mod.ObjectDetector.createFromOptions(ctx.fs, opts);
      });
  }

  function startLive(){
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
      setBusy('此浏览器不支持摄像头调用');
      return;
    }
    setBusy('正在打开摄像头…');
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } },
      audio: false
    }).then(function(stream){
      video.srcObject = stream;
      return video.play();
    }).then(function(){
      video.classList.add('on');
      document.body.classList.add('live');
      setBusy('加载识别模型（首次约 3–8 秒）…');
      return fetch('mapping.csv').then(function(r){ return r.text(); }).then(function(t){
        MAPPING = parseMapping(t);
      });
    }).then(createDetector).then(function(det){
      mpDetector = det;
      setBusy('');
      requestAnimationFrame(liveLoop);
    }).catch(function(e){
      var msg = (e && e.message) ? e.message : String(e);
      setBusy('启动失败：' + msg + '\n（需 HTTPS 且浏览器支持摄像头）');
    });
  }
"""

# 10) 注入 LIVE 代码
idx = html.rfind("})();")
html = html[:idx] + LIVE_JS + "\n" + html[idx:]

# 11) live 模式下画面铺满
html = html.replace("</style>", """
/* 网页真识别模式 */
body.live #stage{background:#000}
body.live #fallback{display:none}
</style>""")


# 12) 诊断模式：?probe=1 直接对内置图跑一次检测
html = html.replace("  function createDetector(){",
                    "  function createDetector(mode){", 1)
html = html.replace("runningMode: 'VIDEO',",
                    "runningMode: mode || 'VIDEO',", 1)

PROBE_JS = r"""
  function runProbe(){
    setBusy('PROBE 加载中…');
    fetch('selfcheck.jpg').then(function(r){ return r.blob(); })
      .then(function(b){ return createImageBitmap(b); })
      .then(function(bmp){
        return createDetector('IMAGE').then(function(det){
          var res = det.detect(bmp);
          var list = res.detections || [];
          var names = list.slice(0, 3).map(function(d){
            var c = d.categories[0];
            return c.categoryName + ':' + c.score.toFixed(2);
          }).join('  ');
          setBusy('PROBE DET ' + list.length + (names ? '\n' + names : ''));
          document.title = 'PROBE n=' + list.length;
        });
      })
      .catch(function(e){
        setBusy('PROBE FAIL: ' + ((e && e.message) || e));
        document.title = 'PROBE FAIL';
      });
  }
  if (location.search.indexOf('probe=1') >= 0) runProbe();
"""
html = html.replace("  function startLive(){", PROBE_JS + "\n  function startLive(){", 1)

open(os.path.join(dst_dir, "index.html"), "w", encoding="utf-8").write(html)
print("docs/index.html", len(html), "bytes")
