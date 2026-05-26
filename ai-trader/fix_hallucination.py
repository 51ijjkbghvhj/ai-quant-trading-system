file_path = r"C:/Users/Administrator/Desktop/OH-WorkSpace/ai-trader/v3/event_bus.py"
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_start = "        # ★ 新增：AI 幻觉拦截器 (Gatekeeper)"
old_end = "        trade_log(f\"[AI] 原始候选信号: {candidates}\")"

start_idx = content.find(old_start)
end_idx = content.find(old_end)

if start_idx != -1 and end_idx != -1:
    # Find the end of the line
    end_idx += len(old_end)
    
    new_code = """        # ★ 智能意图校正引擎 (AI Intent Corrector)
        # 核心逻辑：当 AI 搞混代码和名字时，尝试猜测它的真实意图并修正，而不是直接拦截。
        # 例如：AI 想买“京能电力”，但给了错代码，系统通过名字反查正确代码。
        
        # 建立 名字->代码 反向索引
        name_to_sym_map = {}
        for s, d in current_data.items():
            n = d.get("name")
            if n: name_to_sym_map[n] = s
            
        valid_candidates = []
        for cand in new_candidates:
            sym = cand.get("symbol", "")
            ai_name = cand.get("name", "")
            
            final_sym = None
            final_name = ai_name
            
            # 情况 1：代码在池子里
            if sym in current_data:
                real_name = current_data[sym].get("name")
                
                # 如果 AI 给的代码和名字对不上
                if ai_name and real_name and real_name != ai_name:
                    # 检查 AI 说的名字是否在池子里有对应的真代码
                    if ai_name in name_to_sym_map:
                        # 意图是名字，代码写错了 -> 修正代码
                        final_sym = name_to_sym_map[ai_name]
                        trade_log(f"[校正] AI 代码幻觉：想买 '{ai_name}' 但给错代码 ({sym} 其实是 {real_name}) -> 修正为 {final_sym}")
                    else:
                        # 名字也找不到，说明纯瞎编 -> 丢弃
                        trade_log(f"[拦截] AI 幻觉：代码 {sym} ({real_name}) 与名称 '{ai_name}' 均无法对应 -> 丢弃")
                        continue
                else:
                    final_sym = sym
            
            # 情况 2：代码不在池子里（可能是停牌或代码错误）
            else:
                # 尝试通过名字找人
                if ai_name in name_to_sym_map:
                    final_sym = name_to_sym_map[ai_name]
                    trade_log(f"[校正] AI 代码失效 ({sym})，通过名称 '{ai_name}' 反查锁定 {final_sym}")
                else:
                    trade_log(f"[拦截] AI 瞎编：找不到代码 {sym} 且名称 '{ai_name}' 不在监控池中 -> 丢弃")
                    continue
            
            if final_sym:
                cand["symbol"] = final_sym
                # 确保名字是最新的
                if final_sym in current_data:
                    cand["name"] = current_data[final_sym].get("name")
                valid_candidates.append(cand)
        
        trade_log(f"[AI] 信号处理：{len(valid_candidates)} 个有效 (修正 {len(new_candidates)-len(valid_candidates)} 个)")
        candidates.extend(valid_candidates)
        trade_log(f"[AI] 原始候选信号: {candidates}")"""
    
    new_content = content[:start_idx] + new_code + content[end_idx:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("SUCCESS")
else:
    print(f"NOT FOUND. Start: {start_idx}, End: {end_idx}")
