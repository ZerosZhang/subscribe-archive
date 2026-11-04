#!/usr/bin/env python3
"""
Folo 网页版界面 —— 单页 HTML（HTML/CSS/JS 全部内联，无任何外部依赖）

被 webui.py 作为字符串常量引入，由 `GET /` 原样返回。
不使用任何 JS 图表库，热力图用纯 HTML/CSS 网格绘制。
"""

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Folo 文章归档 · 网页版</title>
<style>
*{box-sizing:border-box}
:root{--cell:12px;--gap:2px}
body{margin:0;font-family:"Microsoft YaHei","Segoe UI",system-ui,-apple-system,sans-serif;
     background:#f6f8fa;color:#24292f;font-size:14px}
.wrap{max-width:1040px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:10px 0 16px}
h1 .sub{font-size:12px;font-weight:normal;color:#57606a;border:1px solid #d0d7de;
        border-radius:10px;padding:1px 8px;margin-left:8px;vertical-align:middle}
.card{background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:12px 14px;margin-bottom:14px}
.card h2{font-size:15px;margin:0 0 10px}
button{font-family:inherit;font-size:13px;padding:5px 12px;border:1px solid #d0d7de;
       border-radius:6px;background:#f6f8fa;cursor:pointer;color:#24292f}
button:hover:not(:disabled){background:#eef1f4}
button:disabled{opacity:.5;cursor:not-allowed}
button.primary{background:#1f883d;border-color:#1f883d;color:#fff}
button.primary:hover:not(:disabled){background:#1a7f37}
button.danger{color:#cf222e}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
input[type=text]{font-family:inherit;font-size:13px;padding:5px 8px;border:1px solid #d0d7de;border-radius:6px}
.steps{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:4px}
.steps label{font-size:13px;cursor:pointer;user-select:none}
.bar{height:14px;background:#eaeef2;border-radius:7px;overflow:hidden;margin:10px 0}
.bar > div{height:100%;width:0;background:#1f883d;transition:width .3s ease}
#status{font-size:13px;color:#57606a}
.step-times{font-size:12px;color:#57606a;white-space:pre-wrap;
            font-family:Consolas,"Courier New",monospace;margin-top:4px}
/* ---------- 日志 ---------- */
.log{height:320px;overflow:auto;background:#0d1117;color:#c9d1d9;padding:8px 10px;border-radius:6px;
     font-family:Consolas,"Courier New",monospace;font-size:12px;line-height:1.55;
     white-space:pre-wrap;word-break:break-all}
.logline.err{color:#ff7b72}
.logline.warn{color:#d29922}
/* ---------- 热力图 ---------- */
.heat-overview{font-size:12px;color:#57606a;margin-bottom:8px}
.heat-scroll{overflow-x:auto;padding-bottom:4px}
.heat-body{display:flex;gap:6px;min-width:min-content}
.heat-left{display:flex;flex-direction:column}
.heat-left .spacer{height:14px}
.heat-weekdays{display:grid;grid-template-rows:repeat(7,var(--cell));gap:var(--gap);
               align-items:center;justify-items:end;width:28px;font-size:10px;color:#57606a}
.heat-right{display:flex;flex-direction:column}
.heat-months{display:grid;grid-auto-columns:var(--cell);gap:var(--gap);height:14px;
             font-size:10px;color:#57606a}
.heat-months .month-label{white-space:nowrap}
.heat-grid{display:grid;grid-template-rows:repeat(7,var(--cell));grid-auto-flow:column;
           grid-auto-columns:var(--cell);gap:var(--gap)}
.cell{width:var(--cell);height:var(--cell);border-radius:2px;background:#ebedf0}
.cell.none{background:#ebedf0}
.cell.unread{background:#2ea043}
.cell.read{background:#0969da}
.cell.clickable{cursor:pointer}
.cell.clickable:hover{outline:1px solid #57606a;outline-offset:1px}
.heat-legend{display:flex;align-items:center;gap:4px;font-size:10px;color:#57606a;
             margin-top:8px;justify-content:flex-end;flex-wrap:wrap}
.heat-legend .gap{width:8px}
.heat-hint{font-size:10px;color:#57606a;text-align:right;margin-top:4px}
/* ---------- 常驻定时说明 ---------- */
.sched-line{font-size:12px;color:#57606a;margin:-8px 0 14px;padding-left:2px}
</style>
</head>
<body>
<div class="wrap">
  <h1>Folo 文章归档<span class="sub">网页版</span></h1>
  <p class="sched-line" id="sched-line">每天 08:00 自动归档</p>

  <section class="card">
    <h2>归档进展</h2>
    <div class="heat-overview" id="heat-overview">加载中…</div>
    <div class="heat-scroll" id="heat-scroll">
      <div class="heat-body">
        <div class="heat-left">
          <div class="spacer"></div>
          <div class="heat-weekdays" id="heat-weekdays"></div>
        </div>
        <div class="heat-right">
          <div class="heat-months" id="heat-months"></div>
          <div class="heat-grid" id="heat-grid"></div>
        </div>
      </div>
    </div>
    <div class="heat-legend">
      <i class="cell none"></i><span>无归档</span>
      <span class="gap"></span>
      <i class="cell unread"></i><span>未读</span>
      <span class="gap"></span>
      <i class="cell read"></i><span>已读</span>
    </div>
    <div class="heat-hint">单击格子：在新标签页打开当天总览并标记为已读；Shift/Alt + 单击：只切换已读状态。</div>
  </section>

  <section class="card">
    <h2>手动执行</h2>
    <div class="steps" id="steps"></div>
    <div class="row">
      <label>日期 <input type="text" id="date" size="14" placeholder="YYYY年MM月DD日"></label>
      <button id="today-btn">今天</button>
    </div>
    <div class="row">
      <button id="start" class="primary">开始执行</button>
      <button id="stop" disabled>停止</button>
      <span id="status">就绪</span>
    </div>
    <div class="bar"><div id="bar"></div></div>
    <div class="step-times" id="step-times"></div>
  </section>

  <section class="card">
    <h2>执行日志</h2>
    <div class="log" id="log"></div>
  </section>
</div>

<script>
(function(){
  "use strict";
  var since = 0;
  var stepsRendered = false;
  var dateInited = false;
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

  /* ---------------- 日志 ---------------- */
  var logEl = el("log");
  function addLog(line){
    line = (line === null || line === undefined) ? "" : String(line);
    var nearBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 48;
    var div = document.createElement("div");
    var cls = "logline";
    if(line.indexOf("✗") >= 0 || line.indexOf("❌") >= 0 || line.indexOf("失败") >= 0) cls += " err";
    else if(line.indexOf("⚠️") >= 0) cls += " warn";
    div.className = cls;
    div.textContent = (line === "") ? "\u00a0" : line;
    logEl.appendChild(div);
    while(logEl.childElementCount > 2000){ logEl.removeChild(logEl.firstChild); }
    if(nearBottom){ logEl.scrollTop = logEl.scrollHeight; }
  }

  /* ---------------- 热力图（阅读状态日历） ---------------- */
  var WEEKDAY_LABELS = ["周一", "", "周三", "", "周五", "", ""];
  var heatData = null;
  var heatResizeTimer = 0;
  function initWeekdays(){
    var html = "";
    for(var i = 0; i < 7; i++){ html += "<div>" + WEEKDAY_LABELS[i] + "</div>"; }
    el("heat-weekdays").innerHTML = html;
  }

  // 把某天标记为已读/未读，成功后立即刷新热力图让格子变色
  function postRead(key, read){
    return fetch("/api/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: key, read: read })
    }).then(function(r){ return r.json(); }).then(function(d){
      if(!d || !d.ok){ addLog("[WebUI] 已读状态更新失败: " + ((d && d.error) || "未知错误")); }
      refreshHeatmap();
    }).catch(function(e){ addLog("[WebUI] 已读状态请求失败: " + e); });
  }

  function makeCell(key, day, info, today){
    var count = info ? (Number(info.count) || 0) : 0;
    var read = info ? !!info.read : false;
    var cell = document.createElement("div");
    cell.className = "cell " + (count > 0 ? (read ? "read" : "unread") : "none");

    if(count > 0){
      cell.classList.add("clickable");
      cell.title = key + " · " + count + " 篇 · " + (read ? "已读" : "未读");
      cell.addEventListener("click", function(ev){
        ev.preventDefault();
        if(ev.shiftKey || ev.altKey){ postRead(key, !read); return; }   // 只切换已读状态
        postRead(key, true);                                            // 打开即视为已读
        window.open("/archive/" + encodeURIComponent(key) + "/" + encodeURIComponent(key) + ".html",
                    "_blank", "noopener");
      });
    } else {
      cell.title = key + " · 无归档";
      cell.addEventListener("click", function(){ cell.title = key + " · 无归档（当天没有归档）"; });
    }

    if(day > today){ cell.style.visibility = "hidden"; }   // 未来日期不显示
    return cell;
  }

  function renderHeatmap(days, total, recent30, readDays){
    heatData = { days: days, total: total, recent30: recent30, readDays: readDays };
    el("heat-overview").textContent =
      "共归档 " + total + " 篇 · 最近 30 天 " + recent30 + " 篇 · 已读 " + readDays + " 天";

    // 按可用宽度决定格子和周数：桌面铺满 53 周，平板/手机只显示半年以内，避免横向滚动
    var cell = window.innerWidth <= 520 ? 10 : 12;
    var gap = 2;
    var avail = el("heat-scroll").clientWidth || (window.innerWidth - 60);
    var weeks = Math.floor((avail - 34 + gap) / (cell + gap));
    if(window.innerWidth < 900){ weeks = Math.min(weeks, 26); }
    weeks = Math.max(10, Math.min(53, weeks));

    document.documentElement.style.setProperty("--cell", cell + "px");
    document.documentElement.style.setProperty("--gap", gap + "px");

    var grid = el("heat-grid"), months = el("heat-months");
    grid.innerHTML = ""; months.innerHTML = "";
    months.style.gridTemplateColumns = "repeat(" + weeks + "," + cell + "px)";
    var today = new Date(); today.setHours(0,0,0,0);
    var dow = (today.getDay() + 6) % 7;                 // 周一 = 0
    var monday = new Date(today); monday.setDate(today.getDate() - dow);
    var start = new Date(monday); start.setDate(monday.getDate() - (weeks - 1)*7);
    var lastMonth = -1;
    var lastLabelCol = -99;
    for(var col = 0; col < weeks; col++){
      var cm = new Date(start); cm.setDate(start.getDate() + col*7);
      if(cm.getMonth() !== lastMonth){
        lastMonth = cm.getMonth();
        // 标签有宽度：太挤（<4 列）或贴近右边缘时不画，避免重叠和溢出
        if(col - lastLabelCol >= 4 && col <= weeks - 3){
          lastLabelCol = col;
          var lab = document.createElement("div");
          lab.className = "month-label";
          lab.style.gridColumn = String(col + 1);
          lab.textContent = (cm.getMonth() + 1) + "月";
          months.appendChild(lab);
        }
      }
      for(var row = 0; row < 7; row++){
        var d = new Date(cm); d.setDate(cm.getDate() + row);
        var key = dateKey(d);
        grid.appendChild(makeCell(key, d, days[key], today));
      }
    }
  }
  function refreshHeatmap(){
    fetch("/api/heatmap").then(function(r){ return r.json(); }).then(function(d){
      renderHeatmap(d.days || {}, d.total || 0, d.recent30 || 0, d.read_days || 0);
    }).catch(function(){});
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
    if(!dateInited && st.today){ el("date").value = st.today; dateInited = true; }

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

    if(lastRunning && !st.running){ refreshHeatmap(); refreshSchedule(true); }
    lastRunning = !!st.running;
  }

  function poll(){
    fetch("/api/state").then(function(r){ return r.json(); }).then(function(st){
      applyState(st);
      return fetch("/api/logs?since=" + since).then(function(r){ return r.json(); }).then(function(d){
        (d.lines || []).forEach(addLog);
        if(typeof d.next === "number"){ since = d.next; }
      });
    }).catch(function(){
      el("status").textContent = "连接中断，重试中…";
    });
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
  el("today-btn").addEventListener("click", function(){ el("date").value = dateKey(new Date()); });

  el("start").addEventListener("click", function(){
    var payload = { steps: selectedSteps(), date: el("date").value.trim() };
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

  /* ---------------- 窗口尺寸变化后按新宽度重排热力图 ---------------- */
  window.addEventListener("resize", function(){
    if(heatResizeTimer){ clearTimeout(heatResizeTimer); }
    heatResizeTimer = setTimeout(function(){
      if(heatData){ renderHeatmap(heatData.days, heatData.total, heatData.recent30, heatData.readDays); }
    }, 150);
  });

  /* ---------------- 启动轮询 ---------------- */
  initWeekdays();
  refreshHeatmap();
  refreshSchedule(false);
  poll();
  setInterval(poll, 1000);
  setInterval(function(){ refreshSchedule(false); }, 30000);
})();
</script>
</body>
</html>
"""
