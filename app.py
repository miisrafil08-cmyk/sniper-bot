import streamlit as st
import time
import math
import os
import re
import threading
import requests
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright

# ================= আপনার কনফিগারেশন =================
BOT_TOKEN  = "9227687123:AAHKLiLKx3D2OMoLbv6JAB8vrVYI1xdqfHk"
GAME_URL   = "https://hgnice.org/#/saasLottery/WinGo?gameType=WinGo_1M"
GAME_PHONE = "1608505867"  # অথবা 1868505867 (টেলিগ্রামে /login দিয়েও যেকোনো সময় বদলাতে পারবেন)
GAME_PASS  = "asdf4321"
# ====================================================

FILES = {
    "30s": {"sheet": "Sniper_V10_30Sec_Sheet.csv", "raw": "Sniper_V10_30Sec_Raw.csv", "screen": "screen_30s.png"},
    "1m":  {"sheet": "Sniper_V10_1Min_Sheet.csv",  "raw": "Sniper_V10_1Min_Raw.csv",  "screen": "screen_1m.png"}
}

st.set_page_config(page_title="SNIPER V10 DUAL (30s & 1m)", page_icon="⚖️", layout="centered")

for mode in ["30s", "1m"]:
    if not os.path.exists(FILES[mode]["sheet"]):
        pd.DataFrame(columns=[
            "Time", "Period", "Num", "Actual_Size", "Normal_Signal", "Engine",
            "Confidence", "Normal_Result", "Normal_Step",
            "High_Conf_Signal", "High_Conf_Result", "High_Conf_Step"
        ]).to_csv(FILES[mode]["sheet"], index=False)

def load_mode_data(mode):
    r_file, s_file = FILES[mode]["raw"], FILES[mode]["sheet"]
    raw = pd.read_csv(r_file).to_dict('records') if os.path.exists(r_file) else []
    sheet = pd.read_csv(s_file).fillna("").to_dict('records') if os.path.exists(s_file) else []
    return raw, sheet

def get_streaks(sheet_log):
    norm_l, vip_l = 0, 0
    for r in sheet_log:
        if r.get("Normal_Result") == "LOSS": norm_l += 1
        elif r.get("Normal_Result") == "WIN": break
    for r in sheet_log:
        if r.get("High_Conf_Result") == "LOSS": vip_l += 1
        elif r.get("High_Conf_Result") == "WIN": break
    return norm_l, vip_l

# --- 10-CORE V10 SUPREME ENGINE ---
def compute_10core(past, ls_cnt):
    L = len(past)
    if L < 5: return None
    s = [x['size'] for x in past]
    n = [int(x['num']) for x in past]
    ema = round(sum(n[-4:]) / min(4, L), 1)

    flips = sum(1 for i in range(1, min(8, L)) if s[-i] != s[-i-1])
    chaos = round((flips / max(1, min(8, L) - 1)) * 100)

    def e1(s, n):
        a3, a6 = sum(n[-3:])/3, sum(n[-6:])/min(6, len(n))
        return 'SMALL' if a3>=7.2 else ('BIG' if a3<=1.8 else ('BIG' if a3>=a6 else 'SMALL'))
    def e2(s, n):
        sl = n[-8:]; m = sum(sl)/len(sl)
        sd = math.sqrt(sum((x-m)**2 for x in sl)/len(sl)) or 1.5
        return 'SMALL' if n[-1]>m+1.3*sd else ('BIG' if n[-1]<m-1.3*sd else ('BIG' if m>=4.5 else 'SMALL'))
    def e3(s, n): return ('SMALL' if s[-1]=='BIG' else 'BIG') if n[-1] in [3,4,5,6] else s[-1]
    def e4(s, n):
        b = sum(3 for i in range(len(s)-3) if s[i:i+3]==s[-3:] and s[i+3]=='BIG')
        sm = sum(3 for i in range(len(s)-3) if s[i:i+3]==s[-3:] and s[i+3]=='SMALL')
        return 'BIG' if b>=sm else 'SMALL'
    def e5(s, n):
        b = sum(2 for i in range(len(n)-1) if n[i]==n[-1] and n[i+1]>=5)
        sm = sum(2 for i in range(len(n)-1) if n[i]==n[-1] and n[i+1]<5)
        return 'BIG' if b>=sm else 'SMALL'
    def e6(s, n): return s[-1] if s[-1]!=s[-2] else ('SMALL' if s[-1]=='BIG' else 'BIG')
    def e7(s, n): return s[-2] if (len(s)>=3 and s[-3]==s[-1] and s[-2]!=s[-1]) else s[-1]
    def e8(s, n):
        st_c = 1
        for i in range(len(s)-2, -1, -1):
            if s[i]==s[-1]: st_c+=1
            else: break
        return ('SMALL' if s[-1]=='BIG' else 'BIG') if st_c>=6 else s[-1]
    def e9(s, n): return 'SMALL' if s[-1]=='BIG' else 'BIG'

    engs = [("Dual EMA",e1),("Bollinger",e2),("Boundary 4↔5",e3),("5-Gram AI",e4),
            ("Markov 2nd",e5),("Twin Box",e6),("Wave 1-2-1",e7),("Dragon",e8),("ZigZag",e9)]
    w = [1.0]*len(engs)
    st_t = max(4, L-12)
    for t in range(st_t, L):
        ss, sn, act = s[:t], n[:t], s[t]
        bst = 1 + ((t - st_t)*0.4)
        for i, (_, fn) in enumerate(engs):
            w[i] = w[i] + bst if fn(ss, sn) == act else max(0.2, w[i] - 0.3)

    rk = sorted(list(enumerate(w)), key=lambda x: x[1], reverse=True)
    top_vote = engs[rk[0][0]][1](s, n)
    b_sc, s_sc, agree = 0.0, 0.0, 0
    for rank, (idx, wt) in enumerate(rk[:5]):
        m = 2.0 if rank==0 else (1.5 if rank==1 else 1.0)
        vt = engs[idx][1](s, n)
        if vt == top_vote: agree += 1
        if vt == 'BIG': b_sc += wt*m
        else: s_sc += wt*m

    ch = 'BIG' if b_sc>=s_sc else 'SMALL'
    b_nm = engs[rk[0][0]][0]
    cf = min(98, max(75, round((max(b_sc, s_sc)/max(1, b_sc+s_sc))*100)))
    if ls_cnt in [2, 3]:
        ch = 'SMALL' if ch=='BIG' else 'BIG'
        b_nm = "Anti-Trap Inverter"

    is_high_conf = (cf >= 86 and chaos <= 65 and agree >= 4 and ls_cnt <= 2)
    return {"sig": ch, "eng": b_nm, "conf": cf, "ema": ema, "chaos": chaos, "high": is_high_conf}

def format_mode_report(mode_key, title_label):
    raw, sheet = load_mode_data(mode_key)
    w = sum(1 for r in sheet if r.get("Normal_Result") == "WIN")
    l = sum(1 for r in sheet if r.get("Normal_Result") == "LOSS")
    vw = sum(1 for r in sheet if r.get("High_Conf_Result") == "WIN")
    vl = sum(1 for r in sheet if r.get("High_Conf_Result") == "LOSS")
    nl, vpl = get_streaks(sheet)
    nxt = compute_10core(raw, nl)
    sig_txt = f"{'💎 HIGH CONF: ' if nxt['high'] else '⚡ Normal: '}*{nxt['sig']}* ({nxt['conf']}% | Step {nl+1})" if nxt else f"⌛ COLD ({len(raw)}/5 Data)"
    return (
        f"⏱️ *{title_label}*\n"
        f"📊 সব সিগন্যাল: Win: {w} | Loss: {l} ({round(w/max(1,w+l)*100)}%)\n"
        f"💎 হাই-কনফার্ম: Win: {vw} | Loss: {vl} ({round(vw/max(1,vw+vl)*100)}%)\n"
        f"🎯 পরবর্তী সিগন্যাল: {sig_txt}"
    )

# --- SINGLETON BACKGROUND ENGINE (NO DUPLICATE THREADS) ---
@st.cache_resource
def start_dual_engine():
    worker_id = str(int(time.time() * 1000))
    with open("active_worker.lock", "w") as f:
        f.write(worker_id)

    state = {
        "worker_id": worker_id,
        "status_30s": "🔄 Starting 30s Reader...",
        "status_1m":  "🔄 Starting 1m Reader...",
        "phone": GAME_PHONE,
        "password": GAME_PASS,
        "action_queue": []
    }
    data_lock = threading.Lock()

    def is_current_worker():
        try:
            with open("active_worker.lock", "r") as f:
                return f.read().strip() == state["worker_id"]
        except Exception:
            return True

    def record_round(mode, num, period_str):
        with data_lock:
            try:
                num = int(num)
            except Exception:
                return False
            if num < 0 or num > 9: return False

            clean_p = ''.join(filter(str.isdigit, str(period_str)))
            if len(clean_p) < 8: return False

            raw_history, sheet_log = load_mode_data(mode)
            if any(str(x.get('period')) == clean_p for x in raw_history):
                return False

            existing_periods = [str(x.get('period')) for x in raw_history if str(x.get('period')).isdigit()]
            if existing_periods:
                max_p = max(existing_periods)
                if len(clean_p) == len(max_p) and clean_p <= max_p:
                    return False

            norm_l, vip_l = get_streaks(sheet_log)
            prev_sig = compute_10core(raw_history, norm_l)
            act_size = 'BIG' if num >= 5 else 'SMALL'
            now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if prev_sig:
                is_win = (act_size == prev_sig['sig'])
                vip_sig_col = prev_sig['sig'] if prev_sig['high'] else ""
                vip_res_col = ("WIN" if is_win else "LOSS") if prev_sig['high'] else ""
                vip_stp_col = f"VIP-Step {vip_l + 1}" if prev_sig['high'] else ""

                row = {
                    "Time": now_str,
                    "Period": clean_p,
                    "Num": num,
                    "Actual_Size": act_size,
                    "Normal_Signal": prev_sig['sig'],
                    "Engine": prev_sig['eng'],
                    "Confidence": f"{prev_sig['conf']}%",
                    "Normal_Result": "WIN" if is_win else "LOSS",
                    "Normal_Step": f"Step {norm_l + 1}",
                    "High_Conf_Signal": vip_sig_col,
                    "High_Conf_Result": vip_res_col,
                    "High_Conf_Step": vip_stp_col
                }
                sheet_log.insert(0, row)
                if len(sheet_log) > 1000: sheet_log.pop()
                pd.DataFrame(sheet_log).to_csv(FILES[mode]["sheet"], index=False)

            raw_history.append({"num": num, "size": act_size, "period": clean_p})
            if len(raw_history) > 150: raw_history.pop(0)
            pd.DataFrame(raw_history).to_csv(FILES[mode]["raw"], index=False)

            state[f"status_{mode}"] = f"🟢 {mode.upper()} Active | #{clean_p[-4:]} -> {num} ({act_size})"
            return True

    def extract_json_recursively(obj, found_list):
        if isinstance(obj, dict):
            per = obj.get("issueNumber") or obj.get("period") or obj.get("issue") or obj.get("planId")
            num = obj.get("number") if "number" in obj else (obj.get("num") if "num" in obj else obj.get("result"))
            if per is not None and num is not None:
                p_str = str(per).strip()
                n_str = str(num).strip()
                if len(p_str) >= 8 and n_str.isdigit() and len(n_str) == 1:
                    found_list.append((p_str, int(n_str)))
            for v in obj.values():
                extract_json_recursively(v, found_list)
        elif isinstance(obj, list):
            for item in obj:
                extract_json_recursively(item, found_list)

    # Fixed Login: Uses Enter key + exact button click & waits for token without premature reload
    def perform_human_login(page, ph_raw, pw_raw):
        clean_ph = str(ph_raw).strip()
        if clean_ph.startswith("+880"): clean_ph = clean_ph[4:]
        elif clean_ph.startswith("880"): clean_ph = clean_ph[3:]
        if clean_ph.startswith("0"): clean_ph = clean_ph[1:]

        state["status_1m"] = f"🔐 Logging in ({clean_ph})..."

        ph_box = page.locator('input[placeholder*="enter the phone" i], input[placeholder*="phone number" i], input[name="userNumber"]')
        if ph_box.count() == 0:
            all_inp = page.locator('input:not([type="password"]):not([type="checkbox"])')
            ph_box = all_inp.nth(1) if all_inp.count() >= 2 else all_inp.first
        else:
            ph_box = ph_box.first

        pw_box = page.locator('input[type="password"]').first

        if ph_box.count() > 0 and pw_box.count() > 0:
            ph_box.click(force=True)
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            ph_box.press_sequentially(clean_ph, delay=50)
            time.sleep(0.4)

            pw_box.click(force=True)
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            pw_box.press_sequentially(str(pw_raw).strip(), delay=50)
            time.sleep(0.6)

            # Click exact button tag OR press Enter
            btn = page.locator('button:has-text("Log in")')
            if btn.count() > 0:
                btn.first.click(force=True)
            else:
                page.keyboard.press("Enter")

            # Wait up to 8 seconds for login page to disappear naturally (DO NOT force goto immediately!)
            for _ in range(8):
                time.sleep(1)
                if page.locator('input[type="password"]').count() == 0:
                    break

            # Close any welcome popups
            for pop_text in ["Confirm", "OK", "Close", "I know", "Receive"]:
                pop_btn = page.locator(f'button:has-text("{pop_text}"), div.van-dialog__confirm:has-text("{pop_text}")')
                if pop_btn.count() > 0 and pop_btn.first.is_visible():
                    pop_btn.first.click(force=True)
                    time.sleep(0.5)

            page.screenshot(path=FILES["1m"]["screen"])
            return page.locator('input[type="password"]').count() == 0
        return False

    def switch_tab_mode(page, target_mode):
        try:
            # Close popups first
            for pop_text in ["Confirm", "OK", "Close", "I know", "Receive"]:
                pop_btn = page.locator(f'button:has-text("{pop_text}"), div.van-dialog__confirm:has-text("{pop_text}")')
                if pop_btn.count() > 0 and pop_btn.first.is_visible():
                    pop_btn.first.click(force=True)
                    time.sleep(0.5)

            # If on home lobby, click WinGo
            if "wingo" not in page.url.lower():
                wg = page.locator('text=/WinGo/i')
                if wg.count() > 0:
                    wg.first.click(force=True)
                    time.sleep(3)
                else:
                    page.goto(GAME_URL, timeout=45000)
                    time.sleep(4)

            # Click 30sec or 1Min tab inside WinGo page
            if target_mode == "30s":
                tab = page.locator('div:has-text("WinGo 30sec"), span:has-text("30sec"), div:has-text("30s")')
                if tab.count() > 0:
                    tab.last.click(force=True)
                    time.sleep(2)
            else:
                tab = page.locator('div:has-text("WinGo 1Min"), div:has-text("WinGo 1 Min"), span:has-text("1Min")')
                if tab.count() > 0:
                    tab.last.click(force=True)
                    time.sleep(2)
        except Exception:
            pass

    def telegram_listener():
        offset = 0
        while is_current_worker():
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=20"
                res = requests.get(url, timeout=25).json()
                for item in res.get("result", []):
                    offset = item["update_id"] + 1
                    msg = item.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    text_raw = msg.get("text", "").strip()
                    text = text_raw.lower()
                    if not chat_id: continue

                    if text.startswith("/login"):
                        parts = text_raw.split()
                        if len(parts) >= 3:
                            state["phone"] = parts[1]
                            state["password"] = " ".join(parts[2:])
                            state["action_queue"].append({"type": "login", "chat_id": chat_id})
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": "🔐 লগইন ও Dual-Tab (30s + 1m) সেটআপ শুরু হয়েছে! ১২ সেকেন্ড পর স্ক্রিনশট আসছে..."})
                        else:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": "⚠️ এভাবে লিখুন:\n`/login 1608505867 asdf4321`", "parse_mode": "Markdown"})
                        continue

                    if text in ["/30s", "30s", "/status30"]:
                        rep = (
                            f"⚖️ *SNIPER V10 • 30 SEC MODE*\n"
                            f"📡 `{state['status_30s']}`\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{format_mode_report('30s', 'WinGo 30Sec Live')}\n\n"
                            f"📥 শিট পেতে `/sheet30` লিখুন।"
                        )
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                      json={"chat_id": chat_id, "text": rep, "parse_mode": "Markdown"})

                    elif text in ["/1m", "1m", "/status1m"]:
                        rep = (
                            f"⚖️ *SNIPER V10 • 1 MIN MODE*\n"
                            f"📡 `{state['status_1m']}`\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{format_mode_report('1m', 'WinGo 1Min Live')}\n\n"
                            f"📥 শিট পেতে `/sheet1m` লিখুন।"
                        )
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                      json={"chat_id": chat_id, "text": rep, "parse_mode": "Markdown"})

                    elif text in ["/start", "/status", "status"]:
                        rep = (
                            f"⚖️ *SNIPER V10 DUAL CLOUD (30s & 1m)*\n"
                            f"📡 30s: `{state['status_30s']}`\n"
                            f"📡 1m: `{state['status_1m']}`\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{format_mode_report('30s', 'WinGo 30Sec (৩০ সেকেন্ড)')}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{format_mode_report('1m', 'WinGo 1Min (১ মিনিট)')}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"📌 *কমান্ড সমূহ:*\n"
                            f"• `/30s` বা `/1m` — আলাদা সিগন্যাল দেখতে\n"
                            f"• `/sheet30` বা `/sheet1m` — আলাদা এক্সেল শিট পেতে\n"
                            f"• `/screen` — লাইভ ব্রাউজার স্ক্রিন দেখতে"
                        )
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                      json={"chat_id": chat_id, "text": rep, "parse_mode": "Markdown"})

                    elif text in ["/sheet30", "sheet30"]:
                        with open(FILES["30s"]["sheet"], "rb") as f:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                                          data={"chat_id": chat_id, "caption": "📊 WinGo 30Sec Master Sheet (💎 VIP কলামসহ)"},
                                          files={"document": f})

                    elif text in ["/sheet1m", "sheet1m", "/sheet", "sheet"]:
                        with open(FILES["1m"]["sheet"], "rb") as f:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                                          data={"chat_id": chat_id, "caption": "📊 WinGo 1Min Master Sheet (💎 VIP কলামসহ)"},
                                          files={"document": f})
                        if text in ["/sheet", "sheet"]:
                            with open(FILES["30s"]["sheet"], "rb") as f2:
                                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                                              data={"chat_id": chat_id, "caption": "📊 WinGo 30Sec Master Sheet (💎 VIP কলামসহ)"},
                                              files={"document": f2})

                    elif text in ["/screen", "screen"]:
                        sent_any = False
                        for m_key, m_label in [("30s", "WinGo 30Sec Tab"), ("1m", "WinGo 1Min Tab")]:
                            sc_file = FILES[m_key]["screen"]
                            if os.path.exists(sc_file):
                                sent_any = True
                                with open(sc_file, "rb") as f:
                                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                                  data={"chat_id": chat_id, "caption": f"🖥️ {m_label}\n{state['status_' + m_key]}"},
                                                  files={"photo": f})
                        if not sent_any:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": "⌛ ব্রাউজার লোড হচ্ছে, ১০ সেকেন্ড পর আবার `/screen` দিন।"})
            except Exception:
                time.sleep(3)

    def auto_reader_worker():
        while is_current_worker():
            try:
                with sync_playwright() as p:
                    exec_path = "/usr/bin/chromium" if os.path.exists("/usr/bin/chromium") else None
                    launch_args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                    if exec_path:
                        browser = p.chromium.launch_persistent_context(
                            user_data_dir="./dual_session_v10",
                            executable_path=exec_path,
                            headless=True,
                            viewport={"width": 412, "height": 915},
                            args=launch_args
                        )
                    else:
                        os.system("playwright install chromium")
                        browser = p.chromium.launch_persistent_context(
                            user_data_dir="./dual_session_v10",
                            headless=True,
                            viewport={"width": 412, "height": 915},
                            args=launch_args
                        )

                    # Create two dedicated tabs: page_1m and page_30s
                    page_1m = browser.pages[0] if browser.pages else browser.new_page()
                    page_30s = browser.new_page()

                    def attach_json_listener(page_obj, mode_str):
                        def handle_resp(response):
                            try:
                                if "json" in response.headers.get("content-type", "").lower():
                                    data = response.json()
                                    found = []
                                    extract_json_recursively(data, found)
                                    if found:
                                        found.sort(key=lambda x: x[0])
                                        for per_id, digit in found:
                                            record_round(mode_str, digit, per_id)
                            except Exception:
                                pass
                        page_obj.on("response", handle_resp)

                    attach_json_listener(page_1m, "1m")
                    attach_json_listener(page_30s, "30s")

                    page_1m.goto(GAME_URL, timeout=60000)
                    time.sleep(5)

                    # Initial login check on Tab 1
                    if "login" in page_1m.url.lower() or page_1m.locator('input[type="password"]').count() > 0:
                        perform_human_login(page_1m, state["phone"], state["password"])

                    # Setup Tab 1 as 1Min & Tab 2 as 30Sec
                    switch_tab_mode(page_1m, "1m")
                    page_30s.goto(GAME_URL, timeout=60000)
                    time.sleep(4)
                    switch_tab_mode(page_30s, "30s")

                    last_tab_sync = time.time()

                    while is_current_worker():
                        try:
                            # Process Manual Login Queue
                            while state["action_queue"]:
                                act = state["action_queue"].pop(0)
                                if act["type"] == "login":
                                    page_1m.goto("https://hgnice.org/#/login", timeout=45000)
                                    time.sleep(3)
                                    ok = perform_human_login(page_1m, state["phone"], state["password"])
                                    switch_tab_mode(page_1m, "1m")
                                    page_30s.goto(GAME_URL, timeout=45000)
                                    time.sleep(3)
                                    switch_tab_mode(page_30s, "30s")
                                    page_1m.screenshot(path=FILES["1m"]["screen"])
                                    page_30s.screenshot(path=FILES["30s"]["screen"])
                                    if act.get("chat_id"):
                                        msg_txt = "✅ লগইন সফল! 30s ও 1m দুটি ট্যাবই চালু হয়েছে।" if ok else "⚠️ লগইন পেজ এখনো আছে, নাম্বার/পাসওয়ার্ড চেক করুন।"
                                        with open(FILES["1m"]["screen"], "rb") as f:
                                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                                          data={"chat_id": act["chat_id"], "caption": msg_txt},
                                                          files={"photo": f})

                            # Scan both pages every 2.5 seconds
                            for m_key, pg in [("30s", page_30s), ("1m", page_1m)]:
                                if "login" in pg.url.lower() or pg.locator('input[type="password"]').count() > 0:
                                    state[f"status_{m_key}"] = "🔐 Needs Login (/login PHONE PASS)"
                                    perform_human_login(pg, state["phone"], state["password"])
                                    switch_tab_mode(pg, m_key)

                                body_txt = pg.inner_text("body")
                                matches = re.findall(r'(202\d{9,16})\s+([0-9])\b', body_txt)
                                if matches:
                                    matches.sort(key=lambda x: x[0])
                                    for per_id, digit in matches:
                                        record_round(m_key, int(digit), per_id)

                                pg.screenshot(path=FILES[m_key]["screen"])

                            # Re-verify tabs every 5 minutes
                            if time.time() - last_tab_sync > 300:
                                switch_tab_mode(page_1m, "1m")
                                switch_tab_mode(page_30s, "30s")
                                last_tab_sync = time.time()

                        except Exception as e:
                            state["status_1m"] = f"⚠️ Scanning ({str(e)[:18]})"
                        time.sleep(2.5)
            except Exception as e:
                state["status_1m"] = f"🔄 Restarting ({str(e)[:18]})"
                time.sleep(5)

    threading.Thread(target=telegram_listener, daemon=True).start()
    threading.Thread(target=auto_reader_worker, daemon=True).start()
    return state

bg_state = start_dual_engine()

# --- STREAMLIT DUAL DASHBOARD UI ---
st.title("⚖️ SIZE SNIPER V10 • DUAL (30s & 1m)")

with st.expander("🔐 ম্যানুয়াল লগইন (Manual Login Control)", expanded=False):
    cp, cw = st.columns(2)
    in_ph = cp.text_input("Phone (0 ছাড়া)", value=bg_state["phone"])
    in_pw = cw.text_input("Password", value=bg_state["password"], type="password")
    if st.button("🚀 Login & Sync Both Modes (30s + 1m)", use_container_width=True):
        bg_state["phone"] = in_ph
        bg_state["password"] = in_pw
        bg_state["action_queue"].append({"type": "login"})
        st.success("✅ লগইন কমান্ড পাঠানো হয়েছে! ১২ সেকেন্ড পর Refresh চাপুন।")

if st.button("🔄 Refresh Live Data", use_container_width=True):
    st.rerun()

tab_30s, tab_1m = st.tabs(["⚡ WinGo 30Sec Mode", "⏱️ WinGo 1Min Mode"])

for mode_key, tab_obj, label in [("30s", tab_30s, "WinGo 30Sec"), ("1m", tab_1m, "WinGo 1Min")]:
    with tab_obj:
        st.caption(f"📡 **Status:** `{bg_state['status_' + mode_key]}`")
        raw, sheet = load_mode_data(mode_key)
        w = sum(1 for r in sheet if r.get("Normal_Result") == "WIN")
        l = sum(1 for r in sheet if r.get("Normal_Result") == "LOSS")
        vw = sum(1 for r in sheet if r.get("High_Conf_Result") == "WIN")
        vl = sum(1 for r in sheet if r.get("High_Conf_Result") == "LOSS")
        nl, vpl = get_streaks(sheet)
        nxt = compute_10core(raw, nl)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("All W/L", f"{w}/{l}")
        c2.metric("All Rate", f"{round(w/max(1,w+l)*100)}%")
        c3.metric("💎 VIP W/L", f"{vw}/{vl}")
        c4.metric("💎 VIP Rate", f"{round(vw/max(1,vw+vl)*100)}%")

        if nxt:
            st.success(f"🎯 **{label} NEXT SIGNAL:** {'💎 HIGH CONF: ' if nxt['high'] else '⚡ Normal: '}**{nxt['sig']}** ({nxt['conf']}% | Step {nl+1})")
        else:
            st.warning(f"⌛ **COLD ({len(raw)}/5 Data):** ডেটা রিড হচ্ছে...")

        if os.path.exists(FILES[mode_key]["sheet"]):
            with open(FILES[mode_key]["sheet"], "rb") as f:
                st.download_button(f"📥 Download {label} CSV Sheet", data=f, file_name=FILES[mode_key]["sheet"], mime="text/csv", key=f"dl_{mode_key}")

        if sheet:
            st.dataframe(pd.DataFrame(sheet), use_container_width=True)

        if os.path.exists(FILES[mode_key]["screen"]):
            st.image(FILES[mode_key]["screen"], caption=f"{label} Live Screen", width=300)
