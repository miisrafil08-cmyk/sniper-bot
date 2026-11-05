import streamlit as st
import time
import math
import os
import re
import threading
import subprocess
import requests
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright

# ================= আপনার কনফিগারেশন =================
BOT_TOKEN  = "9227687123:AAH7LBsqnameh8Nz_qU0lDznqeANVHWTbHs"
LOGIN_URL  = "https://hgnice.org/#/login"
HOME_URL   = "https://hgnice.org/#/"
WINGO_URL  = "https://hgnice.org/#/saasLottery/WinGo?gameType=WinGo_1M"
DEF_PHONE  = "1608505867"
DEF_PASS   = "asdf4321"
# ====================================================

FILES = {
    "30s": {"sheet": "Sniper_V12_30Sec_Sheet.csv", "raw": "Sniper_V12_30Sec_Raw.csv"},
    "1m":  {"sheet": "Sniper_V12_1Min_Sheet.csv",  "raw": "Sniper_V12_1Min_Raw.csv"}
}
LIVE_SCREEN = "v12_live_screen.png"

st.set_page_config(page_title="SNIPER V12 MANUAL & AUTO-READER", page_icon="⚖️", layout="centered")

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

# --- 10-CORE V12 SUPREME ENGINE ---
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

# --- INTERACTIVE CLOUD BROWSER + AUTO-HEALING READER ---
@st.cache_resource
def init_v12_system():
    try:
        subprocess.run(["pkill", "-f", "chromium"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

    worker_id = str(int(time.time() * 1000))
    with open("v12_worker.lock", "w") as f:
        f.write(worker_id)

    state = {
        "worker_id": worker_id,
        "is_reading": True,            # Default ON so once inside WinGo it reads immediately!
        "active_tab": "30s",
        "both_modes_cycle": True,
        "phone": DEF_PHONE,
        "password": DEF_PASS,
        "status": "🔄 Starting Browser...",
        "last_30s": "Waiting...",
        "last_1m":  "Waiting...",
        "cmd_queue": []
    }
    data_lock = threading.Lock()

    def is_alive():
        try:
            with open("v12_worker.lock", "r") as f:
                return f.read().strip() == state["worker_id"]
        except Exception:
            return True

    def detect_mode_from_period(clean_p, fallback_mode):
        # HGNICE Period Format: YYYYMMDD10005xxxx = 30s, YYYYMMDD10001xxxx = 1m
        if len(clean_p) >= 13:
            code = clean_p[8:13]
            if code == "10005": return "30s"
            if code == "10001": return "1m"
        return fallback_mode

    def record_round(mode_hint, num, period_str):
        with data_lock:
            try:
                num = int(num)
            except Exception:
                return False
            if num < 0 or num > 9: return False

            clean_p = ''.join(filter(str.isdigit, str(period_str)))
            if len(clean_p) < 12: return False

            mode = detect_mode_from_period(clean_p, mode_hint)
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

            state[f"last_{mode}"] = f"#{clean_p[-4:]} -> {num} ({act_size})"
            state["status"] = f"🟢 Reading Active ({mode.upper()} Synced)"
            return True

    def extract_json_recursively(obj, found_list):
        if isinstance(obj, dict):
            per = obj.get("issueNumber") or obj.get("period") or obj.get("issue") or obj.get("planId")
            num = obj.get("number") if "number" in obj else (obj.get("num") if "num" in obj else obj.get("result"))
            if per is not None and num is not None:
                p_str = str(per).strip()
                n_str = str(num).strip()
                if len(p_str) >= 12 and n_str.isdigit() and len(n_str) == 1:
                    found_list.append((p_str, int(n_str)))
            for v in obj.values():
                extract_json_recursively(v, found_list)
        elif isinstance(obj, list):
            for item in obj:
                extract_json_recursively(item, found_list)

    # Helper: Perform Login + Dismiss 3 Popups + Click WinGo Card from Home Lobby
    def full_login_and_enter_wingo(page, ph_raw, pw_raw):
        try:
            state["status"] = "🔐 Step 1/3: Logging in..."
            page.goto(LOGIN_URL, timeout=45000)
            time.sleep(3)

            clean_ph = str(ph_raw).strip()
            for pfx in ["+880", "880", "0"]:
                if clean_ph.startswith(pfx):
                    clean_ph = clean_ph[len(pfx):]

            # Dismiss "Token has expired" toast if present
            page.mouse.click(206, 200)
            time.sleep(0.5)

            # Exact Phone Input Box Selector (First text/tel input on HGNICE login page)
            ph_box = page.locator('input[placeholder*="phone" i], input[name="userNumber"], input[type="tel"]').first
            if ph_box.count() == 0:
                ph_box = page.locator('input:not([type="password"]):not([type="checkbox"])').first

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

                lg_btn = page.locator('button:has-text("Log in"), div.login_btn, .van-button--danger')
                if lg_btn.count() > 0:
                    lg_btn.first.click(force=True)
                else:
                    page.keyboard.press("Enter")
                time.sleep(6)

            # Step 2: Dismiss up to 5 Confirm / Announcement popups on Home Lobby
            state["status"] = "✅ Step 2/3: Closing Popups..."
            for _ in range(5):
                clicked_pop = False
                for t in ["Confirm", "OK", "I know", "Close", "Receive"]:
                    b = page.locator(f'button:has-text("{t}"), div.van-dialog__confirm:has-text("{t}"), text="{t}"')
                    if b.count() > 0 and b.first.is_visible():
                        b.first.click(force=True)
                        clicked_pop = True
                        time.sleep(1.2)
                if not clicked_pop:
                    break

            # Step 3: Enter WinGo from Home Lobby Card
            state["status"] = "🎰 Step 3/3: Entering WinGo..."
            wg_card = page.locator('div:has-text("Win Go"):has-text("Guess Number"), text="Win Go", text="Guess Number"')
            if wg_card.count() > 0:
                wg_card.first.click(force=True)
                time.sleep(5)
            else:
                page.goto(WINGO_URL, timeout=45000)
                time.sleep(5)

            # Scroll down slightly so Game History rows are visible
            page.evaluate("window.scrollTo(0, 260)")
            time.sleep(1)
            page.screenshot(path=LIVE_SCREEN)
            state["status"] = "🟢 Ready inside WinGo! Reading Active."
        except Exception as e:
            state["status"] = f"⚠️ Setup Error: {str(e)[:25]}"

    def scan_page_history(page):
        added = 0
        try:
            # Layer A: Direct JS DOM Table Row Scanner
            rows = page.evaluate("""() => {
                let res = [];
                document.querySelectorAll('div, tr, li').forEach(el => {
                    if (el.children.length >= 2 && el.children.length <= 6) {
                        let tx = (el.innerText || '').trim();
                        if (tx.length >= 18 && tx.length <= 90) {
                            let m = tx.match(/(202\\d{10,16})\\s+([0-9])\\s+(Big|Small)/i);
                            if (m) res.push({p: m[1], n: parseInt(m[2])});
                        }
                    }
                });
                return res;
            }""")
            if rows:
                rows.sort(key=lambda x: x['p'])
                for r in rows:
                    if record_round(state["active_tab"], r['n'], r['p']):
                        added += 1

            # Layer B: Full Body Text Regex Backup
            body_txt = page.inner_text("body")
            matches = re.findall(r'(202\d{10,16})\s+([0-9])\s+(?:Big|Small)', body_txt, re.IGNORECASE)
            if not matches:
                matches = re.findall(r'(202\d{10,16})\s+([0-9])\b', body_txt)
            if matches:
                matches.sort(key=lambda x: x[0])
                for per_id, digit in matches:
                    if record_round(state["active_tab"], int(digit), per_id):
                        added += 1
        except Exception:
            pass
        return added

    def mark_click_dot(page, x, y):
        try:
            page.evaluate(f"""() => {{
                let old = document.getElementById('v12-click-dot');
                if (old) old.remove();
                let dot = document.createElement('div');
                dot.id = 'v12-click-dot';
                dot.style.cssText = 'position:fixed;left:{x-10}px;top:{y-10}px;width:20px;height:20px;background:rgba(255,0,0,0.75);border:2px solid yellow;border-radius:50%;z-index:2147483647;pointer-events:none;';
                document.body.appendChild(dot);
            }}""")
        except Exception:
            pass

    def telegram_listener():
        offset = 0
        while is_alive():
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
                        state["cmd_queue"].append({"type": "full_auto_setup", "chat_id": chat_id})
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                      json={"chat_id": chat_id, "text": "🚀 লগইন + পপ-আপ ক্লোজ + WinGo প্রবেশ শুরু হয়েছে! ১৫ সেকেন্ড পর স্ক্রিনশট আসছে..."})
                        continue

                    if text.startswith("/click "):
                        target_txt = text_raw[7:].strip()
                        state["cmd_queue"].append({"type": "text_click", "text": target_txt, "chat_id": chat_id})
                        continue

                    if text.startswith("/xy "):
                        pts = text_raw.split()
                        if len(pts) >= 3 and pts[1].isdigit() and pts[2].isdigit():
                            state["cmd_queue"].append({"type": "xy_click", "x": int(pts[1]), "y": int(pts[2]), "chat_id": chat_id})
                        continue

                    if text in ["/run", "/start_read"]:
                        state["is_reading"] = True
                        state["status"] = "🟢 AUTO-READING RUNNING"
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "🟢 অটো-রিডিং চালু হয়েছে!"})
                        continue

                    if text in ["/stop", "/stop_read"]:
                        state["is_reading"] = False
                        state["status"] = "🛑 AUTO-READING STOPPED"
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "🛑 অটো-রিডিং বন্ধ করা হয়েছে।"})
                        continue

                    if text in ["/30s", "30s", "/status30"]:
                        rep = f"⚖️ *SNIPER V12 (30 SEC)*\n📡 `{state['status']}`\nLast: `{state['last_30s']}`\n━━━━━━━━━━━━━━\n{format_mode_report('30s', 'WinGo 30Sec')}"
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": rep, "parse_mode": "Markdown"})

                    elif text in ["/1m", "1m", "/status1m"]:
                        rep = f"⚖️ *SNIPER V12 (1 MIN)*\n📡 `{state['status']}`\nLast: `{state['last_1m']}`\n━━━━━━━━━━━━━━\n{format_mode_report('1m', 'WinGo 1Min')}"
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": rep, "parse_mode": "Markdown"})

                    elif text in ["/start", "/status", "status"]:
                        rep = (
                            f"⚖️ *SNIPER V12 CONTROLLER*\n"
                            f"📡 `{state['status']}`\n"
                            f"⏱️ 30s Last: `{state['last_30s']}` | 1m Last: `{state['last_1m']}`\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{format_mode_report('30s', 'WinGo 30Sec (৩০ সেকেন্ড)')}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{format_mode_report('1m', 'WinGo 1Min (১ মিনিট)')}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"• `/30s` বা `/1m` — আলাদা সিগন্যাল\n"
                            f"• `/sheet30` বা `/sheet1m` — আলাদা শিট\n"
                            f"• `/login` — অটো লগইন ও WinGo সেটআপ\n"
                            f"• `/click Confirm` — যেকোনো বাটনে ক্লিক\n"
                            f"• `/xy 206 515` — নির্দিষ্ট পজিশনে ক্লিক\n"
                            f"• `/screen` — বর্তমান স্ক্রিনশট"
                        )
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": rep, "parse_mode": "Markdown"})

                    elif text in ["/sheet30", "sheet30"]:
                        with open(FILES["30s"]["sheet"], "rb") as f:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument", data={"chat_id": chat_id, "caption": "📊 WinGo 30Sec Sheet"}, files={"document": f})

                    elif text in ["/sheet1m", "sheet1m", "/sheet", "sheet"]:
                        with open(FILES["1m"]["sheet"], "rb") as f:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument", data={"chat_id": chat_id, "caption": "📊 WinGo 1Min Sheet"}, files={"document": f})
                        if text in ["/sheet", "sheet"]:
                            with open(FILES["30s"]["sheet"], "rb") as f2:
                                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument", data={"chat_id": chat_id, "caption": "📊 WinGo 30Sec Sheet"}, files={"document": f2})

                    elif text in ["/screen", "screen"]:
                        if os.path.exists(LIVE_SCREEN):
                            with open(LIVE_SCREEN, "rb") as f:
                                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={"chat_id": chat_id, "caption": f"🖥️ V12 Live Screen\n{state['status']}"}, files={"photo": f})
            except Exception:
                time.sleep(3)

    def browser_worker():
        while is_alive():
            try:
                with sync_playwright() as p:
                    exec_path = "/usr/bin/chromium" if os.path.exists("/usr/bin/chromium") else None
                    args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                    if exec_path:
                        browser = p.chromium.launch_persistent_context(user_data_dir="./v12_session", executable_path=exec_path, headless=True, viewport={"width": 412, "height": 880}, args=args)
                    else:
                        os.system("playwright install chromium")
                        browser = p.chromium.launch_persistent_context(user_data_dir="./v12_session", headless=True, viewport={"width": 412, "height": 880}, args=args)

                    page = browser.pages[0] if browser.pages else browser.new_page()

                    # Always capture backend JSON history responses
                    def on_response(response):
                        try:
                            if "json" in response.headers.get("content-type", "").lower():
                                data = response.json()
                                found = []
                                extract_json_recursively(data, found)
                                if found and state["is_reading"]:
                                    found.sort(key=lambda x: x[0])
                                    for per_id, digit in found:
                                        record_round(state["active_tab"], digit, per_id)
                        except Exception:
                            pass

                    page.on("response", on_response)

                    # Perform initial full setup automatically on startup
                    full_login_and_enter_wingo(page, state["phone"], state["password"])

                    last_cycle_switch = time.time()
                    stuck_zero_counter = 0

                    while is_alive():
                        try:
                            # 1. Process Manual Commands from Streamlit or Telegram
                            while state["cmd_queue"]:
                                cmd = state["cmd_queue"].pop(0)
                                ctype = cmd.get("type")

                                if ctype == "full_auto_setup":
                                    full_login_and_enter_wingo(page, state["phone"], state["password"])
                                    scan_page_history(page)

                                elif ctype == "goto_login":
                                    page.goto(LOGIN_URL, timeout=45000)
                                    time.sleep(3)

                                elif ctype == "goto_home":
                                    page.goto(HOME_URL, timeout=45000)
                                    time.sleep(3)

                                elif ctype == "fill_login":
                                    clean_ph = str(cmd["phone"]).strip()
                                    for pfx in ["+880", "880", "0"]:
                                        if clean_ph.startswith(pfx): clean_ph = clean_ph[len(pfx):]
                                    if "login" not in page.url.lower() and page.locator('input[type="password"]').count() == 0:
                                        page.goto(LOGIN_URL, timeout=45000)
                                        time.sleep(3)
                                    ph_box = page.locator('input[placeholder*="phone" i], input[name="userNumber"], input[type="tel"]').first
                                    if ph_box.count() == 0:
                                        ph_box = page.locator('input:not([type="password"]):not([type="checkbox"])').first
                                    pw_box = page.locator('input[type="password"]').first
                                    if ph_box.count() > 0 and pw_box.count() > 0:
                                        ph_box.click(force=True)
                                        page.keyboard.press("Control+A")
                                        page.keyboard.press("Backspace")
                                        ph_box.press_sequentially(clean_ph, delay=50)
                                        time.sleep(0.3)
                                        pw_box.click(force=True)
                                        page.keyboard.press("Control+A")
                                        page.keyboard.press("Backspace")
                                        pw_box.press_sequentially(str(cmd["pass"]).strip(), delay=50)
                                        time.sleep(0.5)
                                        lg_btn = page.locator('button:has-text("Log in"), div.login_btn, .van-button--danger')
                                        if lg_btn.count() > 0: lg_btn.first.click(force=True)
                                        else: page.keyboard.press("Enter")
                                        time.sleep(5)

                                elif ctype == "click_confirm":
                                    for _ in range(4):
                                        for t in ["Confirm", "OK", "Close", "I know", "Receive"]:
                                            b = page.locator(f'button:has-text("{t}"), div.van-dialog__confirm:has-text("{t}"), text="{t}"')
                                            if b.count() > 0 and b.first.is_visible():
                                                b.first.click(force=True)
                                                time.sleep(1)

                                elif ctype == "click_wingo_card":
                                    wg = page.locator('div:has-text("Win Go"):has-text("Guess Number"), text="Win Go", text="Guess Number"')
                                    if wg.count() > 0:
                                        wg.first.click(force=True)
                                        time.sleep(4)
                                    else:
                                        page.goto(WINGO_URL, timeout=45000)
                                        time.sleep(4)
                                    page.evaluate("window.scrollTo(0, 260)")

                                elif ctype == "switch_mode":
                                    m = cmd["mode"]
                                    state["active_tab"] = m
                                    if m == "30s":
                                        t30 = page.locator('text=/30\\s*sec/i')
                                        if t30.count() > 0: t30.first.click(force=True)
                                        else: page.mouse.click(65, 310)
                                    else:
                                        t1m = page.locator('text=/1\\s*Min/i')
                                        if t1m.count() > 0: t1m.first.click(force=True)
                                        else: page.mouse.click(160, 310)
                                    time.sleep(2)
                                    scan_page_history(page)

                                elif ctype == "text_click":
                                    target = cmd["text"]
                                    el = page.locator(f'text="{target}"')
                                    if el.count() == 0:
                                        el = page.locator(f':has-text("{target}")')
                                    if el.count() > 0:
                                        el.last.click(force=True)
                                        time.sleep(2)

                                elif ctype == "xy_click":
                                    cx, cy = int(cmd["x"]), int(cmd["y"])
                                    page.mouse.click(cx, cy)
                                    mark_click_dot(page, cx, cy)
                                    time.sleep(2)

                                elif ctype == "scroll":
                                    dy = int(cmd["dy"])
                                    page.evaluate(f"window.scrollBy(0, {dy})")
                                    time.sleep(1)

                                elif ctype == "reload":
                                    page.reload(timeout=45000)
                                    time.sleep(4)

                                page.screenshot(path=LIVE_SCREEN)
                                if cmd.get("chat_id") and os.path.exists(LIVE_SCREEN):
                                    with open(LIVE_SCREEN, "rb") as f:
                                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                                      data={"chat_id": cmd["chat_id"], "caption": f"✅ কমান্ড সম্পন্ন!\n{state['status']}"},
                                                      files={"photo": f})

                            # 2. Active Reading & Stuck '0 0' Self-Healer
                            if state["is_reading"]:
                                scan_page_history(page)

                                # Check if stuck on dead '৳0.00' + 'No data' screen
                                body_txt = page.inner_text("body")
                                if ("৳0.00" in body_txt and "No data" in body_txt) or ("Token has expired" in body_txt):
                                    stuck_zero_counter += 1
                                    if stuck_zero_counter >= 6:
                                        stuck_zero_counter = 0
                                        full_login_and_enter_wingo(page, state["phone"], state["password"])
                                else:
                                    stuck_zero_counter = 0

                                # Alternate between 30s and 1m tabs every 8 seconds
                                if state["both_modes_cycle"] and (time.time() - last_cycle_switch > 8):
                                    next_m = "1m" if state["active_tab"] == "30s" else "30s"
                                    state["active_tab"] = next_m
                                    if next_m == "30s":
                                        t30 = page.locator('text=/30\\s*sec/i')
                                        if t30.count() > 0: t30.first.click(force=True)
                                    else:
                                        t1m = page.locator('text=/1\\s*Min/i')
                                        if t1m.count() > 0: t1m.first.click(force=True)
                                    last_cycle_switch = time.time()
                                    time.sleep(1.5)
                                    scan_page_history(page)

                            page.screenshot(path=LIVE_SCREEN)
                        except Exception:
                            pass
                        time.sleep(2)
            except Exception as e:
                state["status"] = f"🔄 Restarting ({str(e)[:20]})"
                time.sleep(4)

    threading.Thread(target=telegram_listener, daemon=True).start()
    threading.Thread(target=browser_worker, daemon=True).start()
    return state

sys_state = init_v12_system()

# ================= STREAMLIT UI (MANUAL + AUTO CONTROL PAD) =================
st.title("⚖️ SIZE SNIPER V12 • AUTO & MANUAL CONTROL")
st.info(f"📡 **Status:** `{sys_state['status']}`  |  **30s Last:** `{sys_state['last_30s']}`  |  **1m Last:** `{sys_state['last_1m']}`")

# --- MASTER ONE-CLICK SETUP & START/STOP ---
if st.button("🚀 ১-ক্লিকে অটো লগইন + পপ-আপ ক্লোজ + WinGo গেমে প্রবেশ (Fix 00 Stuck)", use_container_width=True, type="primary"):
    sys_state["cmd_queue"].append({"type": "full_auto_setup"})
    st.toast("🚀 লগইন ও WinGo সেটআপ শুরু হয়েছে! ১০ সেকেন্ড পর স্ক্রিন রিফ্রেশ করুন।")
    time.sleep(4)
    st.rerun()

c_run, c_stop, c_ref = st.columns(3)
if c_run.button("🟢 START AUTO-READ", use_container_width=True):
    sys_state["is_reading"] = True
    sys_state["status"] = "🟢 AUTO-READING RUNNING"
    st.rerun()

if c_stop.button("🛑 STOP READING", use_container_width=True):
    sys_state["is_reading"] = False
    sys_state["status"] = "🛑 STOPPED BY USER"
    st.rerun()

if c_ref.button("🔄 স্ক্রিন রিফ্রেশ করুন", use_container_width=True):
    st.rerun()

sys_state["both_modes_cycle"] = st.checkbox("🔄 30s এবং 1m দুটি মোডই একসাথে অটো-রিড করুন", value=sys_state["both_modes_cycle"])

# --- LIVE SCREEN & MANUAL CLICK CONTROLLER ---
st.subheader("🖥️ ১. লাইভ ব্রাউজার ও ম্যানুয়াল ক্লিক কন্ট্রোলার")
col_img, col_ctrl = st.columns([1.15, 1])

with col_img:
    if os.path.exists(LIVE_SCREEN):
        st.image(LIVE_SCREEN, caption=f"Live Screen (Width: 412, Height: 880 | Tab: {sys_state['active_tab']})", use_container_width=True)
    else:
        st.warning("⌛ ব্রাউজার ওপেন হচ্ছে... কিছুক্ষণ পর রিফ্রেশ চাপুন।")

    s_up, s_dn, s_rl = st.columns(3)
    if s_dn.button("⬇️ নিচে স্ক্রল", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "scroll", "dy": 280})
        time.sleep(1.5); st.rerun()
    if s_up.button("⬆️ ওপরে স্ক্রল", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "scroll", "dy": -280})
        time.sleep(1.5); st.rerun()
    if s_rl.button("🔃 Reload", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "reload"})
        time.sleep(3); st.rerun()

with col_ctrl:
    st.markdown("**👆 ম্যানুয়াল স্টেপ-বাই-স্টেপ বাটন:**")
    b_lg_pg, b_hm_pg = st.columns(2)
    if b_lg_pg.button("🔗 Login পেজে যান", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "goto_login"})
        time.sleep(3); st.rerun()
    if b_hm_pg.button("🏠 Home পেজে যান", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "goto_home"})
        time.sleep(3); st.rerun()

    m_ph = st.text_input("Phone (0 ছাড়া)", value=sys_state["phone"])
    m_pw = st.text_input("Password", value=sys_state["password"], type="password")
    if st.button("🔑 নাম্বার ও পাসওয়ার্ড বসিয়ে Log in চাপুন", use_container_width=True):
        sys_state["phone"] = m_ph
        sys_state["password"] = m_pw
        sys_state["cmd_queue"].append({"type": "fill_login", "phone": m_ph, "pass": m_pw})
        time.sleep(5); st.rerun()

    if st.button("✅ Confirm / পপ-আপ কাটুন", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "click_confirm"})
        time.sleep(2.5); st.rerun()

    if st.button("🎰 Home থেকে WinGo কার্ডে ক্লিক করুন", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "click_wingo_card"})
        time.sleep(4); st.rerun()

    t30_b, t1m_b = st.columns(2)
    if t30_b.button("⚡ WinGo 30sec ক্লিক", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "switch_mode", "mode": "30s"})
        time.sleep(2.5); st.rerun()
    if t1m_b.button("⏱️ WinGo 1Min ক্লিক", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "switch_mode", "mode": "1m"})
        time.sleep(2.5); st.rerun()

    st.markdown("---")
    st.markdown("**🖱️ সরাসরি ম্যানুয়াল ক্লিক (Text বা X,Y পজিশন):**")
    txt_target = st.text_input("যেকোনো বাটনের লেখা (যেমন: Confirm, Win Go, Log in)", value="Confirm")
    if st.button("👆 এই লেখার ওপর ক্লিক করুন", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "text_click", "text": txt_target})
        time.sleep(2.5); st.rerun()

    cx, cy = st.columns(2)
    x_pos = cx.number_input("X বাম-ডান (0-412)", value=206, min_value=0, max_value=412, step=10)
    y_pos = cy.number_input("Y ওপর-নিচ (0-880)", value=580, min_value=0, max_value=880, step=20)
    if st.button("🎯 এই (X, Y) পজিশনে ক্লিক করুন (🔴 চিহ্ন দেখাবে)", use_container_width=True):
        sys_state["cmd_queue"].append({"type": "xy_click", "x": x_pos, "y": y_pos})
        time.sleep(2.5); st.rerun()

st.markdown("---")

# --- LIVE SIGNALS & SHEETS FOR 30S AND 1M ---
st.subheader("📊 ২. লাইভ সিগন্যাল ও স্থায়ী শিট (30s & 1m)")
tab_30s, tab_1m = st.tabs(["⚡ WinGo 30Sec ডাটা ও শিট", "⏱️ WinGo 1Min ডাটা ও শিট"])

for mode_key, tab_obj, label in [("30s", tab_30s, "WinGo 30Sec"), ("1m", tab_1m, "WinGo 1Min")]:
    with tab_obj:
        raw, sheet = load_mode_data(mode_key)
        w = sum(1 for r in sheet if r.get("Normal_Result") == "WIN")
        l = sum(1 for r in sheet if r.get("Normal_Result") == "LOSS")
        vw = sum(1 for r in sheet if r.get("High_Conf_Result") == "WIN")
        vl = sum(1 for r in sheet if r.get("High_Conf_Result") == "LOSS")
        nl, vpl = get_streaks(sheet)
        nxt = compute_10core(raw, nl)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("All W/L", f"{w}/{l}")
        c1.metric("All Rate", f"{round(w/max(1,w+l)*100)}%")
        c3.metric("💎 VIP W/L", f"{vw}/{vl}")
        c4.metric("💎 VIP Rate", f"{round(vw/max(1,vw+vl)*100)}%")

        if nxt:
            st.success(f"🎯 **{label} NEXT SIGNAL:** {'💎 HIGH CONF: ' if nxt['high'] else '⚡ Normal: '}**{nxt['sig']}** ({nxt['conf']}% | Step {nl+1}) — Engine: `{nxt['eng']}`")
        else:
            st.warning(f"⌛ **COLD ({len(raw)}/5 Data):** হিস্ট্রি টেবিল স্ক্রিনে আসলেই একসাথে ১০টি ডেটা অটো-রিড হয়ে সিগন্যাল চালু হবে।")

        if os.path.exists(FILES[mode_key]["sheet"]):
            with open(FILES[mode_key]["sheet"], "rb") as f:
                st.download_button(f"📥 Download {label} CSV Sheet", data=f, file_name=FILES[mode_key]["sheet"], mime="text/csv", key=f"dl_{mode_key}")

        if sheet:
            st.dataframe(pd.DataFrame(sheet), use_container_width=True)
