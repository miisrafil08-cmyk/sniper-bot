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
BOT_TOKEN  = "9227687123:AAHKLiLKx3D20MoLbv6JAB8vrVYI1xdqfHk"
GAME_URL   = "https://hgnice.org/#/saasLottery/WinGo?gameType=WinGo_30S"
GAME_PHONE = "1608505867"
GAME_PASS  = "asdf4321"
# ====================================================

SHEET_CSV   = "Size_Sniper_V9_Master_Sheet.csv"
RAW_CSV     = "Size_Sniper_V9_Raw.csv"
SCREEN_PATH = "live_screen.png"

st.set_page_config(page_title="SIZE SNIPER V9 CLOUD", page_icon="⚖️", layout="centered")

if not os.path.exists(SHEET_CSV):
    pd.DataFrame(columns=[
        "Time", "Period", "Num", "Actual_Size", "Normal_Signal", "Engine",
        "Confidence", "Normal_Result", "Normal_Step",
        "High_Conf_Signal", "High_Conf_Result", "High_Conf_Step"
    ]).to_csv(SHEET_CSV, index=False)

def load_state():
    raw = pd.read_csv(RAW_CSV).to_dict('records') if os.path.exists(RAW_CSV) else []
    sheet = pd.read_csv(SHEET_CSV).fillna("").to_dict('records') if os.path.exists(SHEET_CSV) else []
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

# --- 10-CORE V9 SUPREME ENGINE ---
def compute_10core_v9(past, ls_cnt):
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

# --- SHARED BACKGROUND STATE & MANUAL QUEUE ---
@st.cache_resource
def start_background_services():
    state = {
        "status": "🔄 Starting Cloud Browser...",
        "phone": GAME_PHONE,
        "password": GAME_PASS,
        "force_login": True,
        "action_queue": []
    }
    lock = threading.Lock()

    def record_round(num, period_str):
        with lock:
            try:
                num = int(num)
            except Exception:
                return False
            if num < 0 or num > 9: return False

            clean_p = ''.join(filter(str.isdigit, str(period_str)))
            if len(clean_p) < 8: return False

            raw_history, sheet_log = load_state()
            if any(str(x.get('period')) == clean_p for x in raw_history):
                return False

            existing_periods = [str(x.get('period')) for x in raw_history if str(x.get('period')).isdigit()]
            if existing_periods:
                max_p = max(existing_periods)
                if len(clean_p) == len(max_p) and clean_p <= max_p:
                    return False

            norm_l, vip_l = get_streaks(sheet_log)
            prev_sig = compute_10core_v9(raw_history, norm_l)
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
                pd.DataFrame(sheet_log).to_csv(SHEET_CSV, index=False)

            raw_history.append({"num": num, "size": act_size, "period": clean_p})
            if len(raw_history) > 150: raw_history.pop(0)
            pd.DataFrame(raw_history).to_csv(RAW_CSV, index=False)
            state["status"] = f"🟢 Active | Last: #{clean_p[-4:]} -> {num} ({act_size})"
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

    # Human-like Manual/Auto Login Function (Skips +880 box accurately)
    def perform_human_login(page, ph_raw, pw_raw):
        if not ph_raw or not pw_raw or "এখানে" in pw_raw:
            state["status"] = "⚠️ Password not set! Send /login PHONE PASS in Telegram"
            return False

        clean_ph = str(ph_raw).strip()
        if clean_ph.startswith("+880"): clean_ph = clean_ph[4:]
        elif clean_ph.startswith("880"): clean_ph = clean_ph[3:]
        if clean_ph.startswith("0"): clean_ph = clean_ph[1:]

        state["status"] = f"🔐 Typing login for {clean_ph}..."

        # Target exact 'Please enter the phone number' box (skipping +880 dropdown)
        ph_box = page.locator('input[placeholder*="enter the phone" i], input[placeholder*="phone number" i], input[name="userNumber"]')
        if ph_box.count() == 0:
            # Fallback: take the 2nd text/tel input on page (1st is +880)
            all_inp = page.locator('input:not([type="password"]):not([type="checkbox"])')
            ph_box = all_inp.nth(1) if all_inp.count() >= 2 else all_inp.first
        else:
            ph_box = ph_box.first

        pw_box = page.locator('input[type="password"], input[placeholder*="Password" i]').first

        if ph_box.count() > 0 and pw_box.count() > 0:
            ph_box.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            ph_box.press_sequentially(clean_ph, delay=60)
            time.sleep(0.5)

            pw_box.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            pw_box.press_sequentially(str(pw_raw).strip(), delay=60)
            time.sleep(1)

            # Click Log in button
            lg_btn = page.locator('button:has-text("Log in"), div:has-text("Log in")').first
            lg_btn.click(force=True)
            time.sleep(6)
            page.goto(GAME_URL, timeout=60000)
            time.sleep(4)
            page.screenshot(path=SCREEN_PATH)
            return True
        return False

    def telegram_listener():
        offset = 0
        while True:
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

                    # Manual Login Command from Telegram: /login 1868505867 mypassword
                    if text.startswith("/login"):
                        parts = text_raw.split()
                        if len(parts) >= 3:
                            state["phone"] = parts[1]
                            state["password"] = " ".join(parts[2:])
                            state["force_login"] = True
                            state["action_queue"].append({"type": "login", "chat_id": chat_id})
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": "🔐 ম্যানুয়াল লগইন শুরু হয়েছে! ১০ সেকেন্ড পর অটোমেটিক স্ক্রিনশট আসছে..."})
                        else:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": "⚠️ লগইন করতে এভাবে লিখুন:\n`/login 1868505867 আপনার_পাসওয়ার্ড`", "parse_mode": "Markdown"})
                        continue

                    # Manual Click Command from Telegram: /click Confirm
                    if text.startswith("/click"):
                        btn_name = text_raw[6:].strip() or "Confirm"
                        state["action_queue"].append({"type": "click_text", "target": btn_name, "chat_id": chat_id})
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                      json={"chat_id": chat_id, "text": f"👆 `{btn_name}` বাটনে ক্লিক করা হচ্ছে..."})
                        continue

                    raw_history, sheet_log = load_state()
                    w = sum(1 for r in sheet_log if r.get("Normal_Result") == "WIN")
                    l = sum(1 for r in sheet_log if r.get("Normal_Result") == "LOSS")
                    vw = sum(1 for r in sheet_log if r.get("High_Conf_Result") == "WIN")
                    vl = sum(1 for r in sheet_log if r.get("High_Conf_Result") == "LOSS")
                    nl, vpl = get_streaks(sheet_log)
                    nxt = compute_10core_v9(raw_history, nl)

                    if text in ["/start", "/status", "status"]:
                        sig_txt = f"{'💎 HIGH CONF: ' if nxt['high'] else '⚡ Normal: '}{nxt['sig']} ({nxt['conf']}% | Step {nl+1})" if nxt else f"⌛ COLD ({len(raw_history)}/5 Data)"
                        reply = (
                            f"⚖️ *SIZE SNIPER V9 (24/7 CLOUD)*\n"
                            f"📡 *Status:* `{state['status']}`\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"📊 *সব সিগন্যাল:* Win: {w} | Loss: {l} ({round(w/max(1,w+l)*100)}%)\n"
                            f"💎 *শুধু হাই-কনফার্মেশন:* Win: {vw} | Loss: {vl} ({round(vw/max(1,vw+vl)*100)}%)\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🎯 *পরবর্তী সিগন্যাল:* *{sig_txt}*\n\n"
                            f"🔐 ম্যানুয়ালি লগইন করতে:\n`/login 1868505867 পাসওয়ার্ড`\n"
                            f"📥 শিট পেতে `/sheet` ও স্ক্রিন দেখতে `/screen` লিখুন।"
                        )
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                      json={"chat_id": chat_id, "text": reply, "parse_mode": "Markdown"})

                    elif text in ["/sheet", "sheet"]:
                        with open(SHEET_CSV, "rb") as f:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                                          data={"chat_id": chat_id, "caption": f"📊 Master Sheet | Total: {w+l} (💎 VIP Wins: {vw}, Losses: {vl})"},
                                          files={"document": f})

                    elif text in ["/screen", "screen"]:
                        if os.path.exists(SCREEN_PATH):
                            with open(SCREEN_PATH, "rb") as f:
                                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                              data={"chat_id": chat_id, "caption": f"🖥️ Live Cloud Browser\n{state['status']}"},
                                              files={"photo": f})
                        else:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": "⌛ ব্রাউজার লোড হচ্ছে, ১০ সেকেন্ড পর আবার `/screen` দিন।"})
            except Exception:
                time.sleep(3)

    def auto_reader_worker():
        while True:
            try:
                with sync_playwright() as p:
                    exec_path = "/usr/bin/chromium" if os.path.exists("/usr/bin/chromium") else None
                    if exec_path:
                        browser = p.chromium.launch_persistent_context(
                            user_data_dir="./cloud_session",
                            executable_path=exec_path,
                            headless=True,
                            viewport={"width": 412, "height": 915},
                            args=["--no-sandbox", "--disable-dev-shm-usage"]
                        )
                    else:
                        os.system("playwright install chromium")
                        browser = p.chromium.launch_persistent_context(
                            user_data_dir="./cloud_session",
                            headless=True,
                            viewport={"width": 412, "height": 915},
                            args=["--no-sandbox", "--disable-dev-shm-usage"]
                        )

                    page = browser.pages[0] if browser.pages else browser.new_page()

                    def handle_response(response):
                        try:
                            if "json" in response.headers.get("content-type", "").lower():
                                data = response.json()
                                found = []
                                extract_json_recursively(data, found)
                                if found:
                                    found.sort(key=lambda x: x[0])
                                    for per_id, digit in found:
                                        record_round(digit, per_id)
                        except Exception:
                            pass

                    page.on("response", handle_response)
                    page.goto(GAME_URL, timeout=60000)
                    time.sleep(5)

                    last_reload = time.time()
                    last_login_try = 0

                    while True:
                        try:
                            # Process manual actions from Telegram or Web UI
                            while state["action_queue"]:
                                act = state["action_queue"].pop(0)
                                if act["type"] == "login":
                                    perform_human_login(page, state["phone"], state["password"])
                                    if act.get("chat_id") and os.path.exists(SCREEN_PATH):
                                        with open(SCREEN_PATH, "rb") as f:
                                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                                          data={"chat_id": act["chat_id"], "caption": f"✅ ম্যানুয়াল লগইন সম্পন্ন!\n{state['status']}"},
                                                          files={"photo": f})
                                elif act["type"] == "click_text":
                                    t_btn = page.locator(f'text="{act["target"]}"').first
                                    if t_btn.count() > 0:
                                        t_btn.click(force=True)
                                        time.sleep(3)
                                        page.screenshot(path=SCREEN_PATH)

                            # Auto-Login if on login screen (throttled to once every 25s)
                            if ("login" in page.url.lower() or page.locator('input[type="password"]').count() > 0) and (time.time() - last_login_try > 25):
                                last_login_try = time.time()
                                perform_human_login(page, state["phone"], state["password"])

                            # Close Popups/Dialogs automatically
                            for pop_text in ["Confirm", "OK", "Close", "I know", "Receive"]:
                                pop_btn = page.locator(f'button:has-text("{pop_text}"), div.van-dialog__confirm:has-text("{pop_text}")')
                                if pop_btn.count() > 0 and pop_btn.first.is_visible():
                                    pop_btn.first.click(force=True)
                                    time.sleep(1)

                            # Scan Page Text for Period + Number
                            body_text = page.inner_text("body")
                            matches = re.findall(r'(202\d{9,16})\s+([0-9])\b', body_text)
                            if matches:
                                matches.sort(key=lambda x: x[0])
                                for per_id, digit in matches:
                                    record_round(int(digit), per_id)

                            page.screenshot(path=SCREEN_PATH)

                            if time.time() - last_reload > 600:
                                page.goto(GAME_URL, timeout=60000)
                                last_reload = time.time()

                        except Exception as e:
                            state["status"] = f"⚠️ Scanning ({str(e)[:25]})"
                        time.sleep(3)
            except Exception as e:
                state["status"] = f"🔄 Restarting ({str(e)[:20]})"
                time.sleep(5)

    threading.Thread(target=telegram_listener, daemon=True).start()
    threading.Thread(target=auto_reader_worker, daemon=True).start()
    return state

bg_state = start_background_services()

# --- STREAMLIT LIVE WEB DASHBOARD & MANUAL LOGIN PANEL ---
st.title("⚖️ SIZE SNIPER V9 • 24/7 CLOUD")
st.caption(f"📡 **Live Reader Status:** `{bg_state['status']}`")

with st.expander("🔐 ম্যানুয়ালি লগইন করুন (Manual Login & Remote Control)", expanded=True):
    col_p, col_w = st.columns(2)
    in_phone = col_p.text_input("Phone Number (0 ছাড়া)", value=bg_state["phone"])
    in_pass  = col_w.text_input("Password", value="" if "এখানে" in bg_state["password"] else bg_state["password"], type="password")
    if st.button("🚀 ক্লাউড ব্রাউজারে এখনই ম্যানুয়াল লগইন করুন", use_container_width=True):
        bg_state["phone"] = in_phone
        bg_state["password"] = in_pass
        bg_state["action_queue"].append({"type": "login"})
        st.success("✅ লগইন কমান্ড পাঠানো হয়েছে! ১০ সেকেন্ড পর নিচে Refresh চাপুন অথবা টেলিগ্রামে /screen দিন।")

raw_history, sheet_log = load_state()
w = sum(1 for r in sheet_log if r.get("Normal_Result") == "WIN")
l = sum(1 for r in sheet_log if r.get("Normal_Result") == "LOSS")
vw = sum(1 for r in sheet_log if r.get("High_Conf_Result") == "WIN")
vl = sum(1 for r in sheet_log if r.get("High_Conf_Result") == "LOSS")
nl, vpl = get_streaks(sheet_log)
nxt = compute_10core_v9(raw_history, nl)

c1, c2, c3, c4 = st.columns(4)
c1.metric("All Win/Loss", f"{w} / {l}")
c2.metric("All Win Rate", f"{round(w/max(1,w+l)*100)}%")
c3.metric("💎 VIP Win/Loss", f"{vw} / {vl}")
c4.metric("💎 VIP Win Rate", f"{round(vw/max(1,vw+vl)*100)}%")

if nxt:
    st.success(f"🎯 **NEXT SIGNAL:** {'💎 HIGH CONF: ' if nxt['high'] else '⚡ Normal: '}**{nxt['sig']}** ({nxt['conf']}% | Step {nl+1}) — Engine: `{nxt['eng']}`")
else:
    st.warning(f"⌛ **ENGINE COLD ({len(raw_history)}/5 Data):** লগইন সম্পন্ন হলে প্রথম ৫টি রেজাল্ট অটো রিড হবে...")

if st.button("🔄 Refresh Dashboard & Screen"):
    st.rerun()

if os.path.exists(SCREEN_PATH):
    st.subheader("🖥️ Live Cloud Browser Screen")
    st.image(SCREEN_PATH, width=320)

if os.path.exists(SHEET_CSV):
    with open(SHEET_CSV, "rb") as f:
        st.download_button("📥 Download Master Excel/CSV Sheet", data=f, file_name="Size_Sniper_V9_Master_Sheet.csv", mime="text/csv")

st.subheader("📊 Live Master Sheet (হাই-কনফার্মেশন কলামসহ)")
if sheet_log:
    st.dataframe(pd.DataFrame(sheet_log), use_container_width=True)
