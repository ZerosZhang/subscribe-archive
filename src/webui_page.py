#!/usr/bin/env python3
"""
订阅归档网页版 —— 单页 HTML（HTML/CSS/JS 全部内联，无任何外部依赖）

被 webui.py 作为字符串常量引入，由 `GET /` 原样返回。
不使用任何 JS 图表库，热力图用纯 HTML/CSS 网格绘制。
"""

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>订阅归档 · 网页版</title>
<style>
*{box-sizing:border-box}
:root{--cell:12px;--gap:2px}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
     font-family:sans-serif;background:#f6f8fa;color:#24292f;font-size:14px}
.wrap{width:100%;max-width:1180px;margin:auto;padding:16px}
h1{font-size:20px;margin:10px 0 16px}
h1 .sub{font-size:12px;font-weight:normal;color:#57606a;border:1px solid #d0d7de;
        border-radius:10px;padding:1px 8px;margin-left:8px;vertical-align:middle}
.card{background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:12px 14px;margin-bottom:14px}
.layout{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:14px;align-items:start}
.layout > .card{margin-bottom:0}
@media (max-width:900px){
  .layout{grid-template-columns:1fr}
  .layout > .card{margin-bottom:14px}
}
.card h2{font-size:15px;margin:0 0 10px}
button{font-family:inherit;font-size:14px;padding:7px 16px;border:1px solid #d0d7de;
       border-radius:6px;background:#f6f8fa;cursor:pointer;color:#24292f}
button:hover:not(:disabled){background:#eef1f4}
button:disabled{opacity:.5;cursor:not-allowed}
button.primary{background:#1f883d;border-color:#1f883d;color:#fff}
button.primary:hover:not(:disabled){background:#1a7f37}
button.danger{color:#cf222e;padding:6px 12px;font-size:13px;white-space:nowrap}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
input[type=text]{font-family:inherit;font-size:14px;padding:7px 10px;border:1px solid #d0d7de;border-radius:6px}
.steps{display:flex;flex-direction:column;gap:8px;margin-bottom:10px}
.steps label{font-size:13px;cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px}
.skip-ai{display:flex;align-items:center;gap:6px;font-size:13px;color:#57606a;margin:2px 0 10px;cursor:pointer}
.bar{height:14px;background:#eaeef2;border-radius:7px;overflow:hidden;margin:10px 0}
.bar > div{height:100%;width:0;background:#1f883d;transition:width .3s ease}
#status{font-size:13px;color:#57606a}
.step-times{font-size:12px;color:#57606a;white-space:pre-wrap;
            font-family:monospace;margin-top:4px}
/* ---------- 阅读状态日历 ---------- */
.heat-overview{font-size:12px;color:#57606a;margin-bottom:10px;text-align:center}
.cal{max-width:460px;margin:0 auto}
.cal-head{display:flex;align-items:center;justify-content:center;gap:10px;margin:2px 0 12px}
.cal-head button{width:36px;height:36px;padding:0;font-size:18px;line-height:1;
                display:flex;align-items:center;justify-content:center}
.cal-head button#cal-today{width:auto;padding:0 14px;font-size:14px}
.cal-title{min-width:140px;text-align:center;font-size:15px;font-weight:600}
.cal-weekdays{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-bottom:6px;
              font-size:12px;color:#57606a;text-align:center}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.cal-cell{position:relative;aspect-ratio:1/0.92;border-radius:6px;display:flex;
          align-items:center;justify-content:center;font-size:12px;color:#57606a;
          background:#f2f4f6}
.cal-cell.blank{background:transparent}
.cal-cell.none{background:#f2f4f6}
.cal-cell.unread{background:#dafbe1;color:#1a7f37}
.cal-cell.read{background:#ddf4ff;color:#0969da}
.cal-cell.future{opacity:.4}
.cal-cell.today{box-shadow:inset 0 0 0 2px #8c959f}
.cal-cell.clickable{cursor:pointer}
.cal-cell.clickable:hover{outline:1px solid #8c959f}
.cal-cell .count{position:absolute;top:2px;right:5px;font-size:10px;font-weight:600;opacity:.75}
.heat-legend{display:flex;align-items:center;gap:6px;font-size:11px;color:#57606a;
             margin-top:12px;justify-content:center;flex-wrap:wrap}
.heat-legend .dot{width:12px;height:12px;border-radius:3px;display:inline-block}
.heat-legend .gap{width:8px}
.heat-hint{font-size:11px;color:#57606a;text-align:center;margin-top:6px}
/* ---------- 常驻定时说明 ---------- */
.sched-line{font-size:12px;color:#57606a;margin:-8px 0 14px;padding-left:2px}
/* ---------- 顶部工具入口 ---------- */
.linkbtn{float:right;font-size:14px;font-weight:normal;color:#0969da;text-decoration:none;
         border:1px solid #d0d7de;border-radius:8px;padding:9px 18px;background:#fff;line-height:1.2}
.linkbtn:hover{background:#f3f4f6}
.linkbtn + .linkbtn{margin-right:12px}
.last-line{color:#1f883d}
.last-line.err-line{color:#cf222e}
.err-line{color:#cf222e}
</style>
</head>
<body>
<div class="wrap">
  <h1>订阅归档<span class="sub">网页版</span>
    <a class="linkbtn gap" href="/logs">📜 执行日志</a>
    <a class="linkbtn" href="/config">⚙ 订阅配置</a>
  </h1>
  <p class="sched-line" id="sched-line">每天 08:00 自动归档</p>
  <p class="sched-line last-line" id="last-line">上次运行：暂无记录</p>
  <p class="sched-line err-line" id="feed-alert" style="display:none"></p>

  <div class="layout">
  <section class="card">
    <h2>归档日历</h2>
    <div class="heat-overview" id="heat-overview">加载中…</div>
    <div class="cal">
      <div class="cal-head">
        <button id="cal-prev" title="上个月">‹</button>
        <div class="cal-title" id="cal-title"></div>
        <button id="cal-next" title="下个月">›</button>
        <button id="cal-today">今天</button>
      </div>
      <div class="cal-weekdays" id="cal-weekdays"></div>
      <div class="cal-grid" id="cal-grid"></div>
    </div>
    <div class="heat-legend">
      <span class="dot" style="background:#f2f4f6"></span><span>无归档</span>
      <span class="gap"></span>
      <span class="dot" style="background:#dafbe1"></span><span>未读</span>
      <span class="gap"></span>
      <span class="dot" style="background:#ddf4ff"></span><span>已读</span>
    </div>
    <div class="heat-hint">单击日期：在新标签页打开当天总览并标记为已读；Shift/Alt + 单击：只切换已读状态。</div>
  </section>

  <section class="card">
    <h2>手动执行</h2>
    <div class="steps" id="steps"></div>
    <label class="skip-ai"><input type="checkbox" id="skip-ai"> 跳过 AI 摘要（只生成索引页，不消耗 API）</label>
    <div class="row">
      <button id="start" class="primary">开始执行</button>
      <button id="stop" disabled>停止</button>
      <span id="status">就绪</span>
    </div>
    <div class="bar"><div id="bar"></div></div>
    <div class="step-times" id="step-times"></div>
  </section>
  </div>
</div>

<script>
(function(){
  "use strict";
  var stepsRendered = false;
  var lastRunning = false;

  function el(id){ return document.getElementById(id); }
  function pad(n){ return (n < 10 ? "0" : "") + n; }
  function dateKey(d){ return d.getFullYear() + "年" + pad(d.getMonth()+1) + "月" + pad(d.getDate()) + "日"; }
  function escapeHtml(t){
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function fmtDur(s){
    s = Number(s) || 0;
    if(s < 60) return s.toFixed(1) + "秒";
    if(s < 3600){ var m = Math.floor(s/60); return m + "分" + (s - m*60).toFixed(1) + "秒"; }
    var h = Math.floor(s/3600), mm = Math.floor((s - h*3600)/60), ss = s - h*3600 - mm*60;
    return h + "时" + mm + "分" + ss.toFixed(1) + "秒";
  }

  /* ---------------- 日志（完整日志在 /logs 页面） ---------------- */
  var logEl = null;               // 主页不再显示日志，addLog 仅作兜底不输出
  function addLog(){ /* 日志见 /logs */ }

  /* ---------------- 归档日历（月视图） ---------------- */
  var WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"];
  var calDays = {};                 // 日期 -> {count, read}
  var calYear = 0, calMonth = 0;    // 当前显示的月份（month 从 0 开始）

  function initWeekdays(){
    var html = "";
    for(var i = 0; i < 7; i++){ html += "<div>" + WEEKDAY_LABELS[i] + "</div>"; }
    el("cal-weekdays").innerHTML = html;
  }

  // 把某天标记为已读/未读，成功后立即刷新日历让格子变色
  function postRead(key, read){
    return fetch("/api/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: key, read: read })
    }).then(function(r){ return r.json(); }).then(function(d){
      if(!d || !d.ok){ addLog("[WebUI] 已读状态更新失败: " + ((d && d.error) || "未知错误")); }
      refreshCalendar();
    }).catch(function(){});
  }

  function openDay(key){
    window.open("/archive/" + encodeURIComponent(key) + "/" + encodeURIComponent(key) + ".html",
                "_blank", "noopener");
  }

  function makeDayCell(day, info, today){
    var key = dateKey(day);
    var count = info ? (Number(info.count) || 0) : 0;
    var read = info ? !!info.read : false;
    var cell = document.createElement("div");
    cell.className = "cal-cell " + (count > 0 ? (read ? "read" : "unread") : "none");
    if(day > today){ cell.classList.add("future"); }
    if(dateKey(today) === key){ cell.classList.add("today"); }

    var num = document.createElement("span");
    num.textContent = String(day.getDate());
    cell.appendChild(num);
    if(count > 0){
      var badge = document.createElement("span");
      badge.className = "count";
      badge.textContent = String(count);
      cell.appendChild(badge);
      cell.classList.add("clickable");
      cell.title = key + " · " + count + " 篇 · " + (read ? "已读" : "未读");
      cell.addEventListener("click", function(ev){
        ev.preventDefault();
        if(ev.shiftKey || ev.altKey){ postRead(key, !read); return; }   // 只切换已读状态
        postRead(key, true);                                            // 打开即视为已读
        openDay(key);
      });
    } else {
      cell.title = key + " · 无归档";
    }
    return cell;
  }

  function renderCalendar(){
    var today = new Date(); today.setHours(0, 0, 0, 0);
    el("cal-title").textContent = calYear + " 年 " + (calMonth + 1) + " 月";

    var grid = el("cal-grid");
    grid.innerHTML = "";
    var first = new Date(calYear, calMonth, 1);
    var offset = (first.getDay() + 6) % 7;              // 周一 = 0
    var daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();

    for(var i = 0; i < offset; i++){
      var blank = document.createElement("div");
      blank.className = "cal-cell blank";
      grid.appendChild(blank);
    }
    for(var d = 1; d <= daysInMonth; d++){
      var day = new Date(calYear, calMonth, d);
      grid.appendChild(makeDayCell(day, calDays[dateKey(day)], today));
    }
    // 固定 6 行（42 格），切换月份时高度不跳
    for(var tail = offset + daysInMonth; tail < 42; tail++){
      var pad = document.createElement("div");
      pad.className = "cal-cell blank";
      grid.appendChild(pad);
    }
  }

  function renderOverview(total, recent30, readDays){
    el("heat-overview").textContent =
      "共归档 " + total + " 篇 · 最近 30 天 " + recent30 + " 篇 · 已读 " + readDays + " 天";
  }

  function refreshCalendar(){
    fetch("/api/heatmap").then(function(r){ return r.json(); }).then(function(d){
      calDays = d.days || {};
      renderOverview(d.total || 0, d.recent30 || 0, d.read_days || 0);
      renderCalendar();
    }).catch(function(){});
  }

  function shiftMonth(delta){
    var base = new Date(calYear, calMonth + delta, 1);
    calYear = base.getFullYear();
    calMonth = base.getMonth();
    renderCalendar();
  }

  /* ---------------- 步骤复选框 ---------------- */
  function renderSteps(steps){
    var box = el("steps"); box.innerHTML = "";
    (steps || []).forEach(function(s){
      var lab = document.createElement("label");
      var cb = document.createElement("input");
      cb.type = "checkbox"; cb.value = String(s.num); cb.checked = true;
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + s.num + ". " + s.desc));
      box.appendChild(lab);
    });
    stepsRendered = true;
  }
  function selectedSteps(){
    var out = [];
    var cbs = el("steps").querySelectorAll("input[type=checkbox]");
    for(var i = 0; i < cbs.length; i++){ if(cbs[i].checked){ out.push(Number(cbs[i].value)); } }
    return out;
  }

  /* ---------------- 状态呈现 ---------------- */
  function applyState(st){
    if(!stepsRendered && st.steps){ renderSteps(st.steps); }

    el("start").disabled = !!st.running;
    el("stop").disabled = !st.running;
    el("bar").style.width = (Number(st.progress) || 0) + "%";
    el("status").textContent = st.progress_text || (st.running ? "运行中…" : "就绪");

    var times = st.step_times || {};
    var keys = Object.keys(times);
    if(keys.length){
      var desc = {};
      (st.steps || []).forEach(function(s){ desc[s.num] = s.desc; });
      keys.sort(function(a, b){ return Number(a) - Number(b); });
      el("step-times").textContent = keys.map(function(k){
        return "步骤 " + k + "（" + (desc[k] || "") + "）: " + fmtDur(times[k]);
      }).join("\n");
    }

    if(st.schedule){ renderSchedule(st.schedule); }

    if(lastRunning && !st.running){ refreshCalendar(); refreshSchedule(true); refreshLast(); refreshHealth(); }
    lastRunning = !!st.running;
  }

  function poll(){
    fetch("/api/state").then(function(r){ return r.json(); }).then(function(st){
      applyState(st);
    }).catch(function(){
      el("status").textContent = "连接中断，重试中…";
    });
  }

  /* ---------------- 上次运行摘要 ---------------- */
  function sumTimes(times){
    var total = 0;
    Object.keys(times || {}).forEach(function(k){ total += Number(times[k]) || 0; });
    return total;
  }
  function renderLast(d){
    var line = el("last-line");
    d = d || {};
    if(!d.finished_at){
      line.textContent = "上次运行：暂无记录";
      line.className = "sched-line last-line";
      return;
    }
    var text = "上次运行 " + d.finished_at + " · " + (d.date || "") +
               " · 新增 " + (Number(d.articles) || 0) + " 篇";
    var seconds = sumTimes(d.step_times);
    if(seconds > 0){ text += " · 用时 " + fmtDur(seconds); }
    var bad = !!d.error || (d.failures && d.failures.length);
    if(bad){ text += " · 有 " + ((d.failures || []).length || 1) + " 项失败"; }
    line.textContent = text;
    line.className = "sched-line last-line" + (bad ? " err-line" : "");
  }
  function refreshHealth(){
    fetch("/api/health").then(function(r){ return r.json(); }).then(function(d){
      var node = el("feed-alert");
      var bad = (d && d.failures) || [];
      if(!bad.length){ node.style.display = "none"; node.textContent = ""; return; }
      var names = bad.map(function(x){ return x.name || x.url; }).slice(0, 6);
      var more = bad.length > names.length ? " 等 " + bad.length + " 个" : "";
      node.style.display = "";
      node.innerHTML = "⚠️ 订阅链接异常：" + names.map(escapeHtml).join("、") + more +
        ' · <a href="/config">查看订阅配置</a>';
    }).catch(function(){});
  }

  function refreshLast(){
    fetch("/api/last").then(function(r){ return r.json(); }).then(renderLast).catch(function(){});
  }

  /* ---------------- 常驻定时（一行说明） ---------------- */
  var SCHED_LINES = {
    webui: "常驻定时：每天 {time} 自动归档（由本进程负责）",
    external: "常驻定时：每天 {time} 自动归档（由外部调度器负责）",
    disabled: "常驻定时未启用（config.json 里 schedule.enabled=false）"
  };
  function renderSchedule(s){
    s = s || {};
    var owner = s.owner || (s.running ? "external" : "disabled");
    var text = SCHED_LINES[owner] || SCHED_LINES.disabled;
    el("sched-line").textContent = text.replace("{time}", s.time || "08:00");
  }
  function refreshSchedule(force){
    fetch("/api/schedule" + (force ? "?refresh=1" : ""))
      .then(function(r){ return r.json(); })
      .then(renderSchedule)
      .catch(function(){});
  }

  /* ---------------- 事件绑定 ---------------- */
  el("cal-prev").addEventListener("click", function(){ shiftMonth(-1); });
  el("cal-next").addEventListener("click", function(){ shiftMonth(1); });
  el("cal-today").addEventListener("click", function(){
    var now = new Date();
    calYear = now.getFullYear(); calMonth = now.getMonth();
    renderCalendar();
  });

  el("start").addEventListener("click", function(){
    var payload = { steps: selectedSteps(), skip_ai: el("skip-ai").checked };
    fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function(r){ return r.json(); }).then(function(d){
      if(!d.ok){ addLog("[WebUI] 无法启动: " + (d.error || "未知错误")); }
    }).catch(function(e){ addLog("[WebUI] 启动请求失败: " + e); });
  });

  el("stop").addEventListener("click", function(){
    fetch("/api/stop", { method: "POST" })
      .then(function(r){ return r.json(); })
      .catch(function(){});
  });

  /* ---------------- 启动轮询 ---------------- */
  var now0 = new Date();
  calYear = now0.getFullYear(); calMonth = now0.getMonth();
  initWeekdays();
  refreshCalendar();
  refreshSchedule(false);
  refreshLast();
  refreshHealth();
  poll();
  setInterval(poll, 1000);
  setInterval(function(){ refreshSchedule(false); }, 30000);
})();
</script>
</body>
</html>
"""

# =============================================================================
# 订阅配置页（GET /config）
# =============================================================================
CONFIG_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>订阅配置 · 文章归档</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
     font-family:sans-serif;background:#f6f8fa;color:#24292f;font-size:14px}
.wrap{width:100%;max-width:1180px;margin:auto;padding:16px}
h1{font-size:20px;margin:10px 0 8px}
h1 .sub{font-size:12px;font-weight:normal;color:#57606a;border:1px solid #d0d7de;
        border-radius:10px;padding:1px 8px;margin-left:8px;vertical-align:middle}
.linkbtn{float:right;font-size:14px;font-weight:normal;color:#0969da;text-decoration:none;
         border:1px solid #d0d7de;border-radius:8px;padding:9px 18px;background:#fff;line-height:1.2}
.linkbtn:hover{background:#f3f4f6}
.card{background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:12px 14px;margin-bottom:14px}
.layout{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:14px;align-items:start}
.layout > .card{margin-bottom:0}
@media (max-width:900px){
  .layout{grid-template-columns:1fr}
  .layout > .card{margin-bottom:14px}
}
.card h2{font-size:15px;margin:0 0 10px}
button{font-family:inherit;font-size:14px;padding:7px 16px;border:1px solid #d0d7de;
       border-radius:6px;background:#f6f8fa;cursor:pointer;color:#24292f}
button:hover:not(:disabled){background:#eef1f4}
button:disabled{opacity:.5;cursor:not-allowed}
button.primary{background:#1f883d;border-color:#1f883d;color:#fff}
button.primary:hover:not(:disabled){background:#1a7f37}
button.danger{color:#cf222e;padding:6px 12px;font-size:13px}
input[type=text]{font-family:inherit;font-size:14px;padding:7px 10px;border:1px solid #d0d7de;
                 border-radius:6px;width:100%;max-width:460px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
.hint{font-size:12px;color:#57606a;margin-top:6px}
.muted{color:#57606a}
table.feeds{width:100%;border-collapse:collapse;font-size:13px}
table.feeds th{text-align:left;font-weight:normal;color:#57606a;font-size:12px;
               border-bottom:1px solid #d0d7de;padding:6px 8px;white-space:nowrap}
table.feeds td{border-bottom:1px solid #eaeef2;padding:8px;vertical-align:middle}
table.feeds tr:last-child td{border-bottom:none}
table.feeds .name{font-weight:600;white-space:nowrap}
table.feeds .url{font-family:monospace;font-size:12px;
                 word-break:break-all;color:#57606a;min-width:220px}
.table-scroll{overflow-x:auto}
.badge{display:inline-block;font-size:11px;border-radius:10px;padding:1px 8px;margin-left:6px;white-space:nowrap}
.badge.ok{background:#dafbe1;color:#1a7f37}
.badge.bad{background:#ffebe9;color:#cf222e}
.badge.own{background:#ddf4ff;color:#0969da;margin-left:0}
.status-cell{font-size:12px}
.status-line{white-space:nowrap}
button.danger{white-space:nowrap}
.err{color:#cf222e;font-size:12px}
#msg{font-size:12px}
h2 .validate{float:right;font-size:12px;padding:4px 10px;font-weight:normal}
.probe{margin-top:4px;font-size:12px;white-space:nowrap}
.probe.ok{color:#1a7f37}
.probe.bad{color:#cf222e;white-space:normal}
.cand{display:flex;gap:10px;align-items:center;justify-content:space-between;
      border:1px solid #eaeef2;border-radius:6px;padding:8px 10px;margin-top:8px}
.cand-main{min-width:0}
.cand-title{font-weight:600;font-size:13px}
.cand .url{font-family:monospace;font-size:12px;
           color:#57606a;word-break:break-all}
</style>
</head>
<body>
<div class="wrap">
  <h1>订阅配置<a class="linkbtn" href="/">← 返回归档</a></h1>
  <p class="hint">当前列表来源：本地订阅检查 —— 这里添加的源会在下次归档时自动检查</p>

  <section class="card">
    <h2>已添加的订阅源
      <button id="validate-btn" class="validate">检测链接</button>
    </h2>
    <div class="table-scroll">
      <table class="feeds">
        <thead><tr><th>名称</th><th>地址</th><th>策略</th><th>状态</th><th></th></tr></thead>
        <tbody id="feeds-body"><tr><td colspan="5" class="muted">加载中…</td></tr></tbody>
      </table>
    </div>
  </section>

  <section class="card">
    <h2>添加订阅</h2>
    <div class="row">
      <input type="text" id="new-url" placeholder="粘贴任意网址：博客首页、文章页或 feed 地址">
      <button id="add-btn" class="primary">查找</button>
      <span id="msg" class="muted"></span>
    </div>
    <div id="candidates"></div>
    <div class="hint">自动识别网页里声明的 RSS / Atom，或尝试 /feed、/rss 等常见地址。
      站点本身没有 RSS 时，可用 RSSHub 生成后再粘贴。</div>
  </section>
</div>

<script>
(function(){
  "use strict";
  function el(id){ return document.getElementById(id); }
  function esc(t){
    return String(t === null || t === undefined ? "" : t)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderSource(){ /* 来源固定为本地订阅检查，无需切换 */ }

  function statusCell(feed){
    var parts = [];
    parts.push("已记录 " + (feed.entries || 0) + " 条");
    if(feed.last_check){ parts.push("上次检查 " + esc(feed.last_check)); }
    var html = '<div class="status-line">' + parts.join(" · ") + "</div>";
    if(feed.last_error){
      html += '<div class="err">最近失败：' + esc(feed.last_error) +
              (feed.fail_count ? "（连续 " + feed.fail_count + " 次）" : "") + "</div>";
    }
    return html;
  }

  function renderFeeds(data){
    renderSource(data);
    var body = el("feeds-body");
    var feeds = data.feeds || [];
    if(!feeds.length){
      body.innerHTML = '<tr><td colspan="5" class="muted">还没有订阅源，在下面添加一个。</td></tr>';
      return;
    }
    body.innerHTML = "";
    feeds.forEach(function(feed){
      var tr = document.createElement("tr");
      var strategy = feed.strategy
        ? '<span class="badge own">' + esc(feed.strategy) + '</span>'
        : '<span class="muted">通用</span>';
      tr.innerHTML =
        '<td class="name">' + esc(feed.name) +
          (feed.last_error ? '<span class="badge bad">异常</span>'
                           : '<span class="badge ok">正常</span>') + '</td>' +
        '<td class="url">' + esc(feed.url) + '</td>' +
        '<td>' + strategy + '</td>' +
        '<td class="status-cell">' + statusCell(feed) + '</td>' +
        '<td><button class="danger" data-url="' + esc(feed.url) + '">删除</button></td>';
      body.appendChild(tr);
    });
    body.querySelectorAll("button[data-url]").forEach(function(btn){
      btn.addEventListener("click", function(){
        var url = btn.getAttribute("data-url");
        if(!confirm("确定删除这个订阅？\n" + url)){ return; }
        post({ action: "remove", url: url });
      });
    });
  }

  function load(){
    fetch("/api/feeds").then(function(r){ return r.json(); }).then(function(data){
      if(data && data.ok === false && data.error){ el("msg").textContent = data.error; }
      renderFeeds(data || {});
    }).catch(function(e){
      el("feeds-body").innerHTML = '<tr><td colspan="4" class="err">加载失败：' + esc(e) + "</td></tr>";
    });
  }

  function post(payload){
    el("msg").textContent = "处理中…";
    fetch("/api/feeds", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function(r){ return r.json(); }).then(function(data){
      el("msg").textContent = data.message || (data.ok ? "完成" : "失败");
      if(data.feeds){ renderFeeds({ feeds: data.feeds }); }
      else { load(); }
    }).catch(function(e){ el("msg").textContent = "请求失败：" + e; });
  }

  el("validate-btn").addEventListener("click", function(){ validateAll(); });

  function validateAll(){
    var btn = el("validate-btn");
    btn.disabled = true;
    var old = btn.textContent;
    btn.textContent = "检测中…";
    el("msg").textContent = "正在逐条检测订阅链接，可能需要几十秒";
    fetch("/api/validate", { method: "POST" }).then(function(r){ return r.json(); }).then(function(d){
      var map = {};
      (d.results || []).forEach(function(x){ map[x.url] = x; });
      document.querySelectorAll("#feeds-body tr").forEach(function(tr){
        var del = tr.querySelector("button[data-url]");
        var url = del ? del.getAttribute("data-url") : "";
        var cell = tr.children[3];
        if(!cell){ return; }
        var prev = cell.querySelector(".probe");
        if(prev){ prev.remove(); }
        var x = map[url];
        if(!x){ return; }
        var line = document.createElement("div");
        line.className = "probe " + (x.ok ? "ok" : "bad");
        line.textContent = x.ok
          ? "链接正常 · " + x.entries + " 条 · " + x.seconds + "s"
          : "链接异常：" + x.error;
        cell.appendChild(line);
      });
      el("msg").textContent = "检测完成";
    }).catch(function(e){
      el("msg").textContent = "检测失败：" + e;
    }).then(function(){
      btn.disabled = false;
      btn.textContent = old;
    });
  }

  el("add-btn").addEventListener("click", function(){ findFeeds(); });
  el("new-url").addEventListener("keydown", function(ev){ if(ev.key === "Enter"){ findFeeds(); } });

  function findFeeds(){
    var url = el("new-url").value.trim();
    if(!url){ el("msg").textContent = "请先填写网址"; return; }
    el("msg").textContent = "查找中…";
    el("candidates").innerHTML = "";
    fetch("/api/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url })
    }).then(function(r){ return r.json(); }).then(function(data){
      if(!data || !data.ok){
        el("msg").textContent = (data && data.error) || "没找到可用的 feed";
        return;
      }
      el("msg").textContent = "找到 " + data.candidates.length + " 个候选，点「添加」订阅";
      renderCandidates(data.candidates || []);
    }).catch(function(e){ el("msg").textContent = "查找失败：" + e; });
  }

  function renderCandidates(list){
    var box = el("candidates");
    box.innerHTML = "";
    list.forEach(function(c){
      var row = document.createElement("div");
      row.className = "cand";
      row.innerHTML =
        '<div class="cand-main"><div class="cand-title">' + esc(c.title) + '</div>' +
        '<div class="url">' + esc(c.url) + '</div></div>' +
        '<button class="primary" data-add="' + esc(c.url) + '">添加</button>';
      box.appendChild(row);
    });
    box.querySelectorAll("button[data-add]").forEach(function(btn){
      btn.addEventListener("click", function(){
        post({ action: "add", url: btn.getAttribute("data-add") });
        box.innerHTML = "";
        el("new-url").value = "";
      });
    });
  }

  load();
})();
</script>
</body>
</html>
"""

# =============================================================================
# 执行日志页（GET /logs）
# =============================================================================
LOGS_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>执行日志 · 订阅归档</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
     font-family:sans-serif;background:#f6f8fa;color:#24292f;font-size:14px}
.wrap{width:100%;max-width:1180px;margin:auto;padding:16px}
h1{font-size:20px;margin:10px 0 8px}
.linkbtn{float:right;font-size:14px;font-weight:normal;color:#0969da;text-decoration:none;
         border:1px solid #d0d7de;border-radius:8px;padding:9px 18px;background:#fff;line-height:1.2}
.linkbtn:hover{background:#f3f4f6}
.hint{font-size:12px;color:#57606a;margin:0 0 10px}
.hint .err{color:#cf222e}
.log{height:calc(100vh - 140px);min-height:320px;overflow:auto;background:#0d1117;color:#c9d1d9;
     padding:10px 12px;border-radius:8px;font-family:monospace;
     font-size:12.5px;line-height:1.6;white-space:pre-wrap;word-break:break-all}
.logline.err{color:#ff7b72}
.logline.warn{color:#d29922}
</style>
</head>
<body>
<div class="wrap">
  <h1>执行日志<a class="linkbtn" href="/">← 返回归档</a></h1>
  <p class="hint"><span id="status">加载中…</span> · 默认自动滚到最新，向上滚动会暂停自动跟随</p>
  <div class="log" id="log"></div>
</div>

<script>
(function(){
  "use strict";
  var since = 0;
  var auto = true;
  var box = document.getElementById("log");

  box.addEventListener("scroll", function(){
    auto = box.scrollHeight - box.scrollTop - box.clientHeight < 48;
  });

  function addLine(line){
    line = (line === null || line === undefined) ? "" : String(line);
    var div = document.createElement("div");
    var cls = "logline";
    if(line.indexOf("✗") >= 0 || line.indexOf("❌") >= 0 || line.indexOf("失败") >= 0){ cls += " err"; }
    else if(line.indexOf("⚠️") >= 0){ cls += " warn"; }
    div.className = cls;
    div.textContent = (line === "") ? "\u00a0" : line;
    box.appendChild(div);
    while(box.childElementCount > 2000){ box.removeChild(box.firstChild); }
  }

  function fetchLogs(){
    fetch("/api/logs?since=" + since).then(function(r){ return r.json(); }).then(function(d){
      var lines = d.lines || [];
      lines.forEach(addLine);
      if(typeof d.next === "number"){ since = d.next; }
      if(lines.length && auto){ box.scrollTop = box.scrollHeight; }
    }).catch(function(){});
  }

  function fetchStatus(){
    fetch("/api/state").then(function(r){ return r.json(); }).then(function(st){
      var text = st.running ? ("运行中：" + (st.progress_text || "")) : "就绪";
      var node = document.getElementById("status");
      node.textContent = text;
    }).catch(function(){
      document.getElementById("status").textContent = "连接中断，重试中…";
    });
  }

  fetchLogs();
  fetchStatus();
  setInterval(fetchLogs, 1000);
  setInterval(fetchStatus, 2000);
})();
</script>
</body>
</html>
"""


