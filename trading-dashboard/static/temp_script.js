
function $(id){return document.getElementById(id)}
function fmt(n){return (n||0).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}
function getToday(){return new Date().toISOString().slice(0,10);}

// 生成外部跳转链接 (东方财富)
function stockLink(sym, name){
  if(!sym) return name;
  var url = 'https://quote.eastmoney.com/' + sym + '.html';
  return '<a href="'+url+'" target="_blank" class="link-stock" title="打开 '+name+' 详情">'+name+'</a>';
}

function render(d){
  try {
    if(!d) return;
    var idx=d.idx||{}, pf=d.pf||{}, pos=pf.pos||{}, news=d.news||[];
    var sectors=d.sectors||[], sent=d.sent||{}, lu=d.lu||[];
    var gainers=d.gainers||[], turnovers=d.turnover||[], watch=pf.watch||[];
    var aiLog=pf.ai_log||[], tx=pf.tx||[];
    var today = getToday();
    var stocks = d.stocks || {};

  // ★ 关键:用实时行情更新持仓现价
  for(var sym in pos){
    if(stocks[sym] && stocks[sym].price > 0){
      pos[sym].current_price = stocks[sym].price;
      pos[sym].change_pct = stocks[sym].change_pct || 0;
      var cost = pos[sym].cost_price || 0;
      pos[sym].pnl = (pos[sym].current_price - cost) * pos[sym].qty;
    }
  }

  // 顶部状态
  if(d.sys&&d.sys.time){
    var timeStr = d.sys.time || '';
    var phase = d.sys.phase || '未知';
    $('phase').textContent = phase + ' ' + timeStr;
  }
  $('modelInfo').textContent=pf.ai_model||'未配置';
  $('researchModelInfo').textContent=pf.research_model||'未配置';

  // 1. 指数
  var idxArr=Array.isArray(idx)?idx:Object.values(idx), iH='';
  for(var i=0;i<idxArr.length;i++){var v=idxArr[i];if(!v||!v.price)continue;var c=v.change_pct>=0?'up':'dn';
    iH+='<div class="idx-item"><div class="idx-name">'+(v.name||'')+'</div><div class="idx-val '+c+'">'+(v.price||0).toFixed(2)+'</div><div class="idx-chg '+c+'">'+(v.change_pct>=0?'+':'')+(v.change_pct||0).toFixed(2)+'%</div></div>';}
  $('idxBar').innerHTML=iH||'<div style="padding:8px;color:var(--text3)">无数据</div>';

  // 渲染列表数据(涨停池、涨幅榜、换手率榜)
  renderList('luList', lu || [], 50, 'lu');
  renderList('gainerList', gainers || [], 50, 'gain');
  renderList('turnoverList', turnovers || [], 50, 'turnover');

  // 2. 账户
  var pnl=pf.pnl||0;
  $('acctGrid').innerHTML=
    '<div class="mi"><div class="l">总资产</div><div class="v">'+fmt(pf.total)+'</div></div>'+
    '<div class="mi"><div class="l">现金</div><div class="v" style="color:var(--blue)">'+fmt(pf.cash)+'</div></div>'+
    '<div class="mi"><div class="l">盈亏</div><div class="v '+(pnl>=0?'up':'dn')+'">'+(pnl>=0?'+':'')+fmt(pnl)+'</div></div>'+
    '<div class="mi"><div class="l">仓位</div><div class="v">'+(pf.pos_pct||0).toFixed(0)+'%</div></div>';
  $('posRatio').textContent=Object.keys(pos).length+'只持仓';

  // 3. 持仓 (增加 T+1 状态判断)
  var pKeys=Object.keys(pos); $('posCnt').textContent=pKeys.length+'只';
  var pH='';
  for(var i=0;i<pKeys.length;i++){
    var s=pKeys[i],p=pos[s];if(!p)continue;
    // ★ 关键防御:防止 pnl/cost/price 为 undefined 导致 toFixed 崩溃
    var cur_pnl = (typeof p.pnl === 'number') ? p.pnl : 0;
    var cur_cost = (typeof p.cost_price === 'number') ? p.cost_price : 0;
    var cur_price = (typeof p.current_price === 'number') ? p.current_price : 0;
    var cur_qty = (typeof p.qty === 'number') ? p.qty : 0;

    var loss=cur_pnl<0;
    // T+1 判断逻辑:如果买入日期不是今天,则可以卖出
    var buyDate = p.buy_date || '';
    // 兼容不同格式的日期,只比较前 10 位
    var isLocked = (buyDate.substring(0,10) === today);
    var statusHtml = isLocked ? '<span class="pos-status status-lock">🔒 T+1 锁定</span>' : '<span class="pos-status status-ok">✅ 可卖出</span>';

    pH+='<div class="pos-card'+(loss?' loss':'')+'">';
    pH+='<div class="pos-top"><span class="pos-name">'+stockLink(s,p.name)+'</span><span class="pos-pnl '+(!loss?'up':'dn')+'">'+(cur_pnl>=0?'+':'')+cur_pnl.toFixed(2)+'</span></div>';
    pH+='<div class="pos-row"><span>成本:'+cur_cost.toFixed(2)+'</span><span>现价:'+cur_price.toFixed(2)+'</span><span>'+cur_qty+'股</span></div>';
    pH+='<div class="pos-row" style="justify-content:space-between;align-items:center"><span>买入:'+buyDate+'</span>'+statusHtml+'</div>';
    pH+='</div>';
  }
  $('posList').innerHTML=pH||'<div style="text-align:center;color:var(--text3);padding:16px">空仓</div>';

  // 4. 关注池
  $('watchCnt').textContent=watch.length+'只';
  var wH='';
  for(var i=0;i<watch.length;i++){var w=watch[i];if(!w)continue;
    var w_chg = (typeof w.change_pct === 'number') ? w.change_pct : 0;
    wH+='<div class="watch-item"><div><div class="watch-name">'+stockLink(w.symbol,w.name)+'</div>'+(w.reason?'<div class="watch-reason">'+w.reason+'</div>':'')+'</div><span class="'+(w_chg>=0?'up':'dn')+'" style="font-weight:700;font-size:11px">'+(w_chg>=0?'+':'')+w_chg.toFixed(2)+'%</span></div>';}
  $('watchList').innerHTML=wH||'<div style="text-align:center;color:var(--text3);padding:16px">暂无</div>';

  // 5. 热点板块 (显示详情)
  $('sectorCnt').textContent=sectors.length+'个';
  var sH='';
  for(var i=0;i<sectors.length;i++){
    var s=sectors[i];if(!s)continue;
    var sId='sec_'+i;
    var stocksHtml = '';
    if(s.stocks && s.stocks.length > 0){
      stocksHtml = '<div class="sector-detail" id="'+sId+'">';
      for(var j=0;j<s.stocks.length;j++){
        var stk = s.stocks[j];
        stocksHtml += '<div class="sector-stock">'+stockLink(stk.symbol, stk.name)+' <span style="color:'+(stk.change_pct>=0?'var(--green)':'var(--red)')+'">'+stk.change_pct.toFixed(2)+'%</span></div>';
      }
      stocksHtml += '</div>';
    }
    sH+='<span class="sector-chip" onclick="document.getElementById(\''+sId+'\').classList.toggle(\'show\')">'+s.name+'<span class="pct '+((s.change_pct||0)>=0?'up':'dn')+'">'+((s.change_pct||0)>=0?'+':'')+s.change_pct+'%</span></span>'+stocksHtml;
  }
  $('sectorList').innerHTML=sH||'<div style="text-align:center;color:var(--text3);padding:12px">暂无</div>';

  // 6. 涨停/涨幅/换手(已在上方调用 renderList)

  // 7. 新闻
  $('newsCnt').textContent = news.length + '条';
  var nH = '';
  for (var i = 0; i < Math.min(news.length, 20); i++) {
    var n = news[i];
    if (!n) continue;
    var tag = n.tags ? '[' + (n.tags.type || '?') + ']' : '';
    var impact = n.tags ? '[' + (n.tags.impact_score || 0) + ']' : '';
    nH += '<div class="news-item">';
    nH += '<div class="news-title">' + (n.title || '') + '</div>';
    nH += '<div class="news-meta"><span>' + (n.source || '') + '</span><span>' + (n.time || '') + '</span>' + (tag ? '<span>' + tag + impact + '</span>' : '') + '</div>';
    nH += '</div>';
  }
  $('newsList').innerHTML = nH || '<div style="text-align:center;color:var(--text3);padding:12px">暂无新闻</div>';

  // 8. 市场情绪
  var sScore = sent.emotion_score || 0;
  var sPhase = sent.emotion_phase || '未知';
  var sColor = sScore >= 70 ? 'var(--green)' : (sScore <= 30 ? 'var(--red)' : 'var(--amber)');
  $('sentPanel').innerHTML =
    '<div class="sent-gauge">' +
    '<div class="sent-score" style="color:' + sColor + '">' + sScore + '</div>' +
    '<div class="sent-phase">' + sPhase + '</div>' +
    '<div class="sent-bar"><div class="sent-fill" style="width:' + sScore + '%;background:' + sColor + '"></div></div>' +
    '</div>' +
    '<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text3)">' +
    '<span>上涨 ' + (sent.up_count || 0) + '</span>' +
    '<span>下跌 ' + (sent.down_count || 0) + '</span>' +
    '<span>上涨比 ' + (sent.up_ratio || 0) + '%</span>' +
    '</div>';

  // 9. 交易记录 (优化：显示最新 20 条，卡片式美化)
  // 修正：后端已按时间倒序 (DESC)，前端直接截取即可，无需 reverse
  var txs = tx.slice(0, 20);
  var tH = '';
  
  $('txCnt').textContent = tx.length + '笔';
  
  if(txs.length === 0){
    tH = '<div style="text-align:center;color:var(--text3);padding:16px">暂无交易记录</div>';
  } else {
    for(var i=0; i<txs.length; i++){
      var t = txs[i];
      var isBuy = t.type === 'buy';
      var actionText = isBuy ? '买入' : '卖出';
      var actionColor = isBuy ? 'var(--green)' : 'var(--red)';
      var dot = isBuy ? '●' : '●';
      
      tH += '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px dashed var(--border)">';
      
      // 左侧：动作 + 名称 + 价格
      tH += '<div style="display:flex;flex-direction:column;gap:2px">';
      tH += '<div style="display:flex;align-items:center;gap:6px">';
      tH += '<span style="font-size:10px;color:'+actionColor+'">'+dot+'</span>';
      tH += '<span style="font-weight:600;color:var(--text);font-size:11px">' + (t.name || t.symbol) + '</span>';
      tH += '<span style="font-size:9px;padding:1px 4px;border-radius:3px;background:'+actionColor+'22;color:'+actionColor+'">'+actionText+'</span>';
      tH += '</div>';
      tH += '<div style="color:var(--text2);font-size:10px;margin-left:14px">'
           + '@ ' + (t.price || '--') 
           + ' × ' + (t.qty || '--') + '股'
           + '</div>';
      tH += '</div>';
      
      // 右侧：时间
      var timeStr = (t.time || '').replace('T', ' ').substring(5, 16); // MM-DD HH:MM
      tH += '<div style="text-align:right;color:var(--text3);font-size:10px">' + timeStr + '</div>';
      
      tH += '</div>';
    }
  }
  $('txList').innerHTML = tH;

  // 9.5 风控拒绝记录 (优化：卡片式美化，与交易记录风格统一)
  var riskLogs = d.pf && d.pf.risk_logs ? d.pf.risk_logs : [];
  $('riskCnt').textContent = riskLogs.length + '笔';
  
  // 只显示最新的 10 条 (修正：取最后 10 条并反转，确保最新的显示在列表最上方)
  var recentRisks = riskLogs.slice(-10).reverse();
  var nH = '';
  
  if(recentRisks.length === 0){
    nH = '<div style="text-align:center;color:var(--text3);padding:12px">暂无风控拦截</div>';
  } else {
    for (var i = 0; i < recentRisks.length; i++) {
      var r = recentRisks[i];
      
      nH += '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px dashed var(--border)">';
      
      // 左侧：股票名 + 拦截标签 + 原因
      nH += '<div style="display:flex;flex-direction:column;gap:2px">';
      nH += '<div style="display:flex;align-items:center;gap:6px">';
      nH += '<span style="font-size:10px;color:var(--red)">⚠️</span>'; // 警告图标
      nH += '<span style="font-weight:600;color:var(--text);font-size:11px">' + (r.name || r.symbol) + '</span>';
      nH += '<span style="font-size:9px;padding:1px 4px;border-radius:3px;background:rgba(248,113,113,0.15);color:var(--red)">风控拦截</span>';
      nH += '</div>';
      
      // 原因摘要 (截断防溢出)
      var reason = (r.reason || '').substring(0, 30) + ((r.reason||'').length > 30 ? '...' : '');
      nH += '<div style="color:var(--text2);font-size:10px;margin-left:14px">' + reason + '</div>';
      nH += '</div>';
      
      // 右侧：时间
      var timeStr = (r.time || '').substring(5, 16);
      nH += '<div style="text-align:right;color:var(--text3);font-size:10px">' + timeStr + '</div>';
      
      nH += '</div>';
    }
  }
  $('riskList').innerHTML = nH;

  // 10. AI 引擎控制台 - 显示最近 5 条分析记录
  var aiLog = d.pf && d.pf.ai_log ? d.pf.ai_log : [];
  console.log('[UI] AI log entries:', aiLog.length, 'last:', aiLog.length > 0 ? aiLog[aiLog.length-1].time : 'none');
  $('aiTag').textContent = aiLog.length + '次';
  if (aiLog.length > 0) {
    var lastAI = aiLog[aiLog.length - 1];
    var aiH = '<div class="ai-reasoning">' + (lastAI.reasoning || '分析中...') + '</div>';

    // 持仓分析
    if (lastAI.position_analysis && lastAI.position_analysis.length > 0) {
      aiH += '<div style="margin-top:8px"><b style="color:var(--text);font-size:10px">持仓建议:</b>';
      aiH += '<table style="margin-top:4px;width:100%;font-size:10px"><thead><tr><th>代码</th><th>动作</th><th>理由</th></tr></thead><tbody>';
      for (var i = 0; i < lastAI.position_analysis.length; i++) {
        var pa = lastAI.position_analysis[i];
        var actColor = pa.action === 'HOLD' ? 'var(--green)' : 'var(--red)';
        aiH += '<tr><td style="color:var(--blue)">' + (pa.symbol||'') + '</td>';
        aiH += '<td style="color:' + actColor + '">' + (pa.action||'') + '</td>';
        aiH += '<td style="color:var(--text2)">' + (pa.reason || '') + '</td></tr>';
      }
      aiH += '</tbody></table></div>';
    }

    // 交易信号 - 如果当前无信号，向上查找最近有信号的记录
    var sigs = lastAI.signals || [];
    var sigSource = '最新';
    if (sigs.length === 0 && aiLog.length > 1) {
      for (var k = aiLog.length - 2; k >= Math.max(0, aiLog.length - 5); k--) {
        if (aiLog[k].signals && aiLog[k].signals.length > 0) {
          sigs = aiLog[k].signals;
          sigSource = aiLog[k].time || '上一轮';
          break;
        }
      }
    }
    if (sigs.length > 0) {
      if (sigSource !== '最新') {
        aiH += '<div style="margin-top:6px;color:var(--amber);font-size:9px">信号来源: ' + sigSource + ' (本轮无新信号)</div>';
      }
      aiH += '<div style="margin-top:8px"><b style="color:var(--amber);font-size:10px">交易信号 (' + sigs.length + '):</b>';
      aiH += '<table style="margin-top:4px;width:100%;font-size:10px"><thead><tr><th>代码</th><th>名称</th><th>动作</th><th>逻辑/理由</th><th>风控</th></tr></thead><tbody>';
      for (var i = 0; i < Math.min(sigs.length, 5); i++) {
        var sig = sigs[i];
        var actionColor = sig.action === 'BUY' ? 'var(--green)' : (sig.action === 'SELL' ? 'var(--red)' : 'var(--amber)');
        aiH += '<tr><td style="color:var(--blue)">' + (sig.symbol || '') + '</td>';
        aiH += '<td>' + (sig.name || '') + '</td>';
        aiH += '<td style="color:' + actionColor + ';font-weight:600">' + (sig.action || '') + '</td>';
        aiH += '<td style="color:var(--text2)">' + (sig.thesis || sig.reason || '') + '</td>';
        var riskReason = sig.risk_result || '';
        var riskColor = riskReason.includes('拒绝') || riskReason.includes('不足') ? 'var(--red)' : (riskReason.includes('通过') ? 'var(--green)' : 'var(--text3)');
        aiH += '<td style="color:' + riskColor + ';font-size:9px">' + (riskReason || '--') + '</td></tr>';
      }
      aiH += '</tbody></table></div>';
    } else {
      aiH += '<div style="margin-top:8px;color:var(--text3);font-size:10px">本次无信号</div>';
    }
    $('aiEnginePanel').innerHTML = aiH;
  } else {
    $('aiEnginePanel').innerHTML = '<div style="text-align:center;color:var(--text3);padding:16px">等待AI分析...</div>';
  }

  } catch(e) {
    console.error('🚨 全局渲染崩溃:', e.message);
    console.error('堆栈:', e.stack);
    alert('前端渲染出错,请查看控制台 (F12) 获取详情。数据已损坏,正在尝试恢复...');
    location.reload();
  }
}

function renderList(elId, data, limit, type) {
    if(!data || data.length === 0) { $(elId).innerHTML='<div style="text-align:center;color:var(--text3);padding:12px">暂无</div>'; return; }
    var h = '<table><thead><tr><th>代码</th><th>名称</th>';
    if(type === 'lu' || type === 'gain') h += '<th>涨幅</th>';
    else if(type === 'turnover') h += '<th>换手率</th>';
    h += '</tr></thead><tbody>';

    var items = data.slice(0, limit);
    for(var i=0; i<items.length; i++) {
        var r = items[i];
        var sym = r.symbol || '';
        var nm = r.name || '';
        var val = '';
        if(type === 'lu' || type === 'gain') val = (r.change_pct||0).toFixed(2) + '%';
        else if(type === 'turnover') val = (r.turnover_rate||0).toFixed(1) + '%';

        var cls = (parseFloat(val) >= 0) ? 'up' : 'dn';

        // Build row safely
        h += '<tr>';
        h += '<td class="code-col" onclick="showKline(\'' + sym + '\',\'' + nm + '\')" style="cursor:pointer;color:var(--blue)">' + sym + '</td>';
        h += '<td>' + nm + '</td>';
        h += '<td class="' + cls + '">' + val + '</td>';
        h += '</tr>';
    }
    h += '</tbody></table>';
    $(elId).innerHTML = h;
    var cntId = elId.replace('List', 'Cnt');
    if($(cntId)) $(cntId).textContent = data.length + '只';
}


function loadHistory(){
  $('histList').innerHTML='<div style="text-align:center;color:var(--text3);padding:12px">正在从数据库加载...</div>';
  var s=$('history-start').value, e=$('history-end').value;
    var url='/api/history?limit=5000&table=ai_analysis';
    if(s) url+='&start='+s; if(e) url+='&end='+e;
    fetch(url).then(r=>r.json()).then(d=>{
    var rows=d.rows||[];
     // 过滤掉空信号记录（只显示有实际信号或有持仓分析的）
     rows = rows.filter(function(r) {
       return (r.signals_count && r.signals_count > 0) || (r.reasoning && r.reasoning.length > 5);
     });
     if(rows.length===0){$('histList').innerHTML='<div style="text-align:center;color:var(--text3);padding:12px">数据库暂无有效记录</div>';return;}
     // 只显示最近 50 条，防止页面卡顿
     if(rows.length > 50) rows = rows.slice(0, 50);
    var h='<table class="db-table"><thead><tr><th style="width:140px">时间</th><th>市场观点</th><th>信号/执行</th><th>详情</th></tr></thead><tbody>';
    for(var i=0;i<rows.length;i++){
      var r=rows[i];
      var detailId = 'hd_'+i;
      h+='<tr><td style="color:var(--text2);font-size:10px">'+r.timestamp+'</td>';
      h+='<td style="max-width:200px;color:var(--text2)">'+((r.market_view||r.reasoning||'').substring(0,40))+'</td>';
      h+='<td style="text-align:center">'+(r.signals_count||0)+' 信号 / '+(r.executed||0)+' 笔</td>';
      h+='<td><button class="btn btn-ghost btn-mini" onclick="document.getElementById(\''+detailId+'\').classList.toggle(\'show\')">查看</button></td></tr>';

      // 详情面板
      h+='<tr><td colspan="4" style="padding:0 0 10px 0;border-bottom:2px solid var(--border)"><div class="detail-panel" id="'+detailId+'">';

      if(r.reasoning) h+='<div style="margin-bottom:8px"><b style="color:var(--text)">分析逻辑:</b><div style="margin-top:4px;color:var(--text2);line-height:1.4">'+r.reasoning+'</div></div>';

      if(r.signals_json){
        h+='<div><b style="color:var(--text)">交易信号列表:</b><table style="margin-top:4px"><thead><tr><th>代码</th><th>名称</th><th>动作</th><th>逻辑/理由</th><th>风控</th></tr></thead><tbody>';
        try{
          var sigs = typeof r.signals === 'object' ? r.signals : JSON.parse(r.signals_json);
          if(Array.isArray(sigs)){
            for(var j=0;j<sigs.length;j++){
              var s=sigs[j];
              var actionColor = s.action==='BUY'?'var(--green)':(s.action==='SELL'?'var(--red)':'var(--amber)');
              h+='<tr><td>'+stockLink(s.symbol,s.name)+'</td><td>'+(s.name||'')+'</td><td style="color:'+actionColor+'">'+s.action+'</td><td style="color:var(--text2)">'+(s.reason||s.thesis||'')+'</td>';
              var riskReason = s.risk_result || '';
              var riskColor = riskReason.includes('拒绝') || riskReason.includes('不足') ? 'var(--red)' : (riskReason.includes('通过') ? 'var(--green)' : 'var(--text2)');
              h+='<td style="color:'+riskColor+';font-size:9px">'+(riskReason || '--')+'</td></tr>';
            }
          }
        }catch(e){ h+='<tr><td colspan="5" style="color:var(--red)">解析信号失败: '+e.message+'</td></tr>'; }
        h+='</tbody></table></div>';
      }

      if(r.risk_control) h+='<div style="margin-top:8px"><b style="color:var(--text)">风控结果:</b> '+r.risk_control+'</div>';

      h+='</div></td></tr>';
    }
    h+='</tbody></table>';
    $('histList').innerHTML=h;
  }).catch(()=>{$('histList').innerHTML='<div style="text-align:center;color:var(--red);padding:12px">查询失败</div>';});
}

function updateStatus(){
  fetch('/api/analysis/status').then(r=>r.json()).then(d=>{
    if(d&&d.running){$('btnAnalyze').textContent='停止分析';$('btnAnalyze').className='btn btn-red';$('aiStatus').className='badge badge-run';$('statusDot').className='dot dot-on';$('aiStatus').innerHTML='<span class="dot dot-on"></span>运行中'}
    else{$('btnAnalyze').textContent='启动分析';$('btnAnalyze').className='btn btn-green';$('aiStatus').className='badge badge-idle';$('statusDot').className='dot dot-off';$('aiStatus').innerHTML='<span class="dot dot-off"></span>未连接'}
  }).catch(()=>{});
}
function toggleAnalysis(){
  console.log('[UI] toggleAnalysis clicked');
  fetch('/api/analysis/status')
    .then(function(r){ return r.json(); })
    .then(function(d){
      console.log('[UI] Current status:', d);
      var url = d && d.running ? '/api/analysis/stop' : '/api/analysis/start';
      console.log('[UI] Sending POST to:', url);
      fetch(url, {method:'POST'})
        .then(function(r){ return r.json(); })
        .then(function(resp){ console.log('[UI] Response:', resp); })
        .catch(function(e){ console.error('[UI] POST error:', e); });
      setTimeout(updateStatus, 1000);
    })
    .catch(function(e){ console.error('[UI] Status fetch error:', e); });
}

// AI 配置
function showAIConfig(){
  $('aiConfigModal').style.display='flex';
  // 加载交易 AI 配置
  fetch('/api/ai/config').then(r=>r.json()).then(d=>{
    $('aiApiUrl').value=d.api_url||'';
    $('aiApiKey').value=d.api_key||'';
    fillModelSelect(d.model||'', []); // 初始为空,等待测试后自动填充
  }).catch(()=>{})
  // 加载研究 AI 配置
  fetch('/api/ai/research_config').then(r=>r.json()).then(d=>{
    $('researchApiUrl').value=d.api_url||'';
    $('researchApiKey').value=d.api_key||'';
    fillModelSelect2(d.model||'', []); // 初始为空,等待测试后自动填充
  }).catch(()=>{})
}
function closeAIConfig(){$('aiConfigModal').style.display='none'}
function testAIConfig(){
  var u=$('aiApiUrl').value,k=$('aiApiKey').value;
  if(!u||!k)return alert('请填写 URL 和 Key');
  var el=$('aiConfigStatus');el.style.display='block';el.style.color='var(--blue)';el.textContent='🔄 测试连接中...';
  fetch('/api/ai/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_url:u,api_key:k})}).then(r=>r.json()).then(d=>{
    if(d.connected){
      el.style.color='var(--green)';
      el.textContent='✅ 连接成功 | 获取 '+((d.models||[]).length)+' 个模型';
      fillModelSelect(d.model||'', d.models); // 测试成功后自动填充模型
    }else{
      el.style.color='var(--red)';el.textContent='❌ 连接失败';
    }
  }).catch(()=>{el.style.color='var(--red)';el.textContent='❌ 网络错误'})
}
function saveAIConfig(){
  fetch('/api/ai/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_url:$('aiApiUrl').value,api_key:$('aiApiKey').value,model:$('aiModel').value})}).then(r=>r.json()).then(d=>{
    var e=$('aiConfigStatus');e.style.display='block';
    e.style.background=d.status==='ok'?'rgba(52,211,153,.1)':'rgba(248,113,113,.1)';
    e.style.color=d.status==='ok'?'var(--green)':'var(--red)';
    e.textContent=d.status==='ok'?'✅ 已保存':'❌ 保存失败'
  })
}

// 研究 AI 配置
function testResearchConfig(){
  var u=$('researchApiUrl').value,k=$('researchApiKey').value;
  if(!u||!k)return alert('请填写研究 AI 的 URL 和 Key');
  var el=$('researchConfigStatus');el.style.display='block';el.style.color='var(--blue)';el.textContent='🔄 测试连接中...';
  fetch('/api/ai/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_url:u,api_key:k})}).then(r=>r.json()).then(d=>{
    if(d.connected){
      el.style.color='var(--green)';
      el.textContent='✅ 连接成功 | 获取 '+((d.models||[]).length)+' 个模型';
      fillModelSelect2($('researchModel').value, d.models); // 测试成功后自动填充模型
    }else{
      el.style.color='var(--red)';el.textContent='❌ 连接失败';
    }
  }).catch(()=>{el.style.color='var(--red)';el.textContent='❌ 网络错误'})
}
function saveResearchConfig(){
  fetch('/api/ai/research_config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_url:$('researchApiUrl').value,api_key:$('researchApiKey').value,model:$('researchModel').value})}).then(r=>r.json()).then(d=>{
    var e=$('researchConfigStatus');e.style.display='block';
    e.style.background=d.status==='ok'?'rgba(52,211,153,.1)':'rgba(248,113,113,.1)';
    e.style.color=d.status==='ok'?'var(--green)':'var(--red)';
    e.textContent=d.status==='ok'?'✅ 已保存':'❌ 保存失败'
  })
}

var aiProviders={openai:{url:'https://api.openai.com',models:['gpt-4o']},qwen:{url:'dashscope',models:['qwen-plus']}};
function autoDetectProvider(url){for(var k in aiProviders)if(url.indexOf(aiProviders[k].url)>=0)return k;return 'custom'}
function fillModelSelect(curr,models){var s=$('aiModel');s.innerHTML='';(models||[]).forEach(m=>{var o=document.createElement('option');o.value=m;o.textContent=m;o.selected=(m==curr);s.appendChild(o)})}
function fillModelSelect2(curr, models){
  var s=$('researchModel');
  s.innerHTML='';
  var list = (models && models.length > 0) ? models : ['qwen-plus','qwen-max','gpt-4o','deepseek-chat'];
  list.forEach(m=>{
    var o=document.createElement('option');
    o.value=m;
    o.textContent=m;
    if(m==curr) o.selected=true;
    s.appendChild(o)
  })
}

// K线
let klineChartInst=null;
function showKline(s,n){if(typeof echarts==='undefined')return alert('图表库加载失败');$('klineModal').style.display='flex';$('klineTitle').textContent=n+' ('+s+') 日K线';fetch('/api/kline?symbol='+s).then(r=>r.json()).then(res=>{if(res.data&&res.data.length>0)renderKline(res.data);else alert('无K线数据')}).catch(()=>alert('获取失败'))}
function closeKline(){$('klineModal').style.display='none'}
function searchKline(){var v=$('klineInput').value.trim();if(!v)return;if(!v.startsWith('sh')&&!v.startsWith('sz'))v=(v.startsWith('6')?'sh':'sz')+v;showKline(v,'查询')}
function renderKline(data){var c=$('klineChart');if(klineChartInst)klineChartInst.dispose();klineChartInst=echarts.init(c,'dark');var dates=data.map(d=>d.day),vals=data.map(d=>[d.open,d.close,d.low,d.high]),vols=data.map((d,i)=>[i,d.volume,d.open>d.close?1:-1]);klineChartInst.setOption({backgroundColor:'transparent',tooltip:{trigger:'axis'},grid:[{top:10,right:10,bottom:'20%',left:10},{top:'75%',right:10,bottom:10,left:10}],xAxis:[{type:'category',data:dates,gridIndex:0,axisLabel:{show:false}},{type:'category',data:dates,gridIndex:1,axisLabel:{show:false}}],yAxis:[{scale:true,gridIndex:0},{scale:true,gridIndex:1,splitNumber:2,axisLabel:{show:false}}],series:[{type:'candlestick',data:vals,itemStyle:{color:'#f87171',color0:'#34d399',borderColor:'#f87171',borderColor0:'#34d399'}},{type:'bar',xAxisIndex:1,yAxisIndex:1,data:vols,itemStyle:{color:p=>p.value[2]>0?'#f87171':'#34d399'}}]})}

window.onload=function(){fetch('/api/all').then(r=>r.json()).then(render).catch(()=>{});updateStatus()}
setInterval(function(){fetch('/api/all').then(r=>r.json()).then(render).catch(()=>{})},5000);
setInterval(function(){updateStatus()},10000);
