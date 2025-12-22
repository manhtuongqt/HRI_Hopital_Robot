#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rospy
import actionlib
import speech_recognition as sr
import os
import sys
from gtts import gTTS
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal

# ====== GUI ======
import threading
import queue
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

# ====== LLM (requests) ======
import requests
import json
import re
from datetime import datetime

# ====== SQLITE ======
import sqlite3

# ==========================
# CÁC ĐỊA ĐIỂM DẪN ĐƯỜNG 
# ==========================
LOCATIONS = {
    "khoa nhi": {"x": 2.33, "y": 11.9, "w": -0.00143},
    "phòng thuốc": {"x": 8.39, "y": 14.5, "w": -0.00113},
    "khoa nội": {"x": -6.72, "y": 14.2, "w": -0.00143},
    "nhà vệ sinh": {"x": -14.0, "y": 5.64, "w": -0.00143},
    "trạm sạc": {"x": 11.3, "y": -14.8, "w": -0.000143},
    "quầy lễ tân": {"x": 10.0, "y": 0.0, "w": 1.0},
    "khoa tai mũi họng": {"x": -6.38, "y": -14.7, "w": -0.00143},
    "khoa sản": {"x": -6.38, "y": -14.7, "w": -0.00143},
    "khoa ngoại": {"x": 6.25, "y": -14.7, "w": -0.00143},
    "khoa hồi sức gây mê": {"x": -3.51, "y": -0.125, "w": -0.00143},
}

# ==========================
# SQLITE DB
# ==========================
DB_PATH = os.path.join(os.path.dirname(__file__), "hospital_demo.db")

def db_connect():
    """Mỗi lần query mở 1 connection riêng (an toàn thread)."""
    return sqlite3.connect(DB_PATH)

def db_get_insurance(insurance_id: str):
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT i.insurance_id, i.valid_from, i.valid_to, i.is_valid,
                   i.referral_required, i.referral_present,
                   p.patient_id, p.name, p.dob_year, p.phone
            FROM insurance i
            JOIN patients p ON i.patient_id = p.patient_id
            WHERE i.insurance_id = ?
        """, (insurance_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "insurance_id": row[0],
            "valid_from": row[1],
            "valid_to": row[2],
            "is_valid": bool(row[3]),
            "referral_required": bool(row[4]),
            "referral_present": bool(row[5]),
            "patient_id": row[6],
            "owner_name": row[7],
            "dob_year": int(row[8]),
            "phone": row[9],
        }
    except Exception as e:
        rospy.logerr(f"DB insurance error: {e}")
        return None

def db_get_patient_by_phone(phone: str):
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT patient_id, name, dob_year, phone
            FROM patients
            WHERE phone = ?
        """, (phone,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "patient_id": row[0],
            "name": row[1],
            "dob_year": int(row[2]),
            "phone": row[3],
        }
    except Exception as e:
        rospy.logerr(f"DB patient error: {e}")
        return None

def db_get_recent_visits(patient_id: str, limit: int = 2):
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT visit_time, department, chief_complaint, assessment, plan
            FROM visits
            WHERE patient_id = ?
            ORDER BY visit_time DESC
            LIMIT ?
        """, (patient_id, limit))
        rows = cur.fetchall()
        conn.close()

        visits = []
        for r in rows:
            visits.append({
                "visit_time": r[0],
                "department": r[1],
                "chief_complaint": r[2] or "",
                "assessment": r[3] or "",
                "plan": r[4] or "",
            })
        return visits
    except Exception as e:
        rospy.logerr(f"DB visits error: {e}")
        return []

# ==========================
# QUEUE: đẩy log hội thoại sang GUI
# ==========================
CHAT_Q = queue.Queue()

def gui_push(role, text):
    try:
        CHAT_Q.put((role, text))
    except Exception:
        pass

# ==========================
# QUEUE: GUI -> ROS/Dialog (NEW)
# ==========================
CMD_Q = queue.Queue()

def gui_send_command(cmd: str):
    """GUI gửi command sang ROS thread (thread-safe)."""
    if not cmd:
        return
    try:
        CMD_Q.put(cmd)
    except Exception:
        pass

def speak(text):
    rospy.loginfo(f"Robot nói: {text}")
    gui_push("robot", text)

    try:
        tts = gTTS(text=text, lang='vi')
        filename = "voice.mp3"
        tts.save(filename)
        os.system(f"mpg321 {filename}")
        if os.path.exists(filename):
            os.remove(filename)
    except Exception as e:
        rospy.logerr(f"Lỗi Google TTS: {e}. Chuyển sang espeak.")
        os.system(f"espeak -v vi '{text}'")

def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        rospy.loginfo("Đang lắng nghe... ")
        r.adjust_for_ambient_noise(source, duration=1)
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=6)
            rospy.loginfo("Đang nhận dạng...")

            command = r.recognize_google(audio, language="vi-VN").lower()
            rospy.loginfo(f"Nghe được: {command}")
            gui_push("user", command)
            return command
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            rospy.logwarn("Không nghe rõ câu lệnh.")
            return None
        except sr.RequestError:
            speak("Tôi bị mất kết nối internet.")
            return None

def move_to_goal(location_name, coords):
    client = actionlib.SimpleActionClient('move_base', MoveBaseAction)

    rospy.loginfo("Đang kết nối tới move_base server...")
    if not client.wait_for_server(rospy.Duration(5.0)):
        speak("Không thể kết nối tới hệ thống dẫn đường.")
        return

    goal = MoveBaseGoal()
    goal.target_pose.header.frame_id = "map"
    goal.target_pose.header.stamp = rospy.Time.now()

    goal.target_pose.pose.position.x = coords['x']
    goal.target_pose.pose.position.y = coords['y']
    goal.target_pose.pose.orientation.w = coords['w']

    if location_name == "trạm sạc":
        speak("Đang di chuyển về vị trí ban đầu")
    else:
        speak(f"Đang di chuyển đến {location_name}, xin mời di chuyển cùng tôi")

    client.send_goal(goal)
    wait = client.wait_for_result()

    if not wait:
        rospy.logerr("Action server không phản hồi!")
    else:
        speak(f"Đã đến {location_name}. Xin mời vào.")
        return client.get_result()

# ==========================
# TRI THỨC CỨNG 
# ==========================
FAQ = {
    "thủ tục khám": (
        "Thủ tục khám thường gồm: 1) đến quầy lễ tân/đăng ký, 2) lấy số và điền thông tin, "
        "3) nộp thẻ và giấy tờ cần thiết, 4) đóng phí nếu có, 5) chờ gọi vào phòng khám, "
        "6) nếu cần xét nghiệm/chụp chiếu thì làm theo chỉ định và quay lại bác sĩ."
    ),
    "bảo hiểm y tế": (
        "Với bảo hiểm y tế, bạn thường cần: thẻ BHYT còn hạn, giấy tờ tùy thân, "
        "và có thể cần giấy chuyển tuyến (tùy trường hợp). Khi đăng ký, bạn đưa thẻ BHYT "
        "để nhân viên kiểm tra quyền lợi và mức hưởng."
    ),
    "lấy số": (
        "Bạn có thể đến quầy lễ tân để lấy số thứ tự. Nếu có kiosk đăng ký tự động, "
        "bạn chọn chuyên khoa, nhập thông tin, rồi nhận số và chờ gọi."
    ),
    "giờ làm việc": (
        "Giờ làm việc tùy bệnh viện. Nếu bạn cho tôi biết tên bệnh viện/khoa, tôi có thể hướng dẫn "
        "cách hỏi đúng quầy hoặc nơi tra cứu tại bệnh viện."
    )
}

DANGER_SIGNS = [
    "đau ngực", "khó thở", "khó thở nhiều", "ngất", "co giật",
    "liệt", "méo miệng", "nói đớ", "chảy máu nhiều",
    "sốt cao", "lú lẫn", "đau bụng dữ dội"
]

def has_danger_signs(text: str) -> bool:
    if not text:
        return False
    for k in DANGER_SIGNS:
        if k in text:
            return True
    return False

def match_faq(text: str):
    if not text:
        return None
    rules = [
        (["thủ tục", "quy trình", "đăng ký khám", "khám bệnh"], "thủ tục khám"),
        (["bảo hiểm", "bảo hiểm y tế", "bhyt"], "bảo hiểm y tế"),
        (["lấy số", "số thứ tự", "xếp hàng"], "lấy số"),
        (["giờ", "mấy giờ", "làm việc", "mở cửa"], "giờ làm việc"),
    ]
    for keywords, faq_key in rules:
        for kw in keywords:
            if kw in text:
                return FAQ.get(faq_key)
    return None

def looks_like_navigation_request(text: str) -> bool:
    if not text:
        return False
    nav_keywords = ["dẫn", "đi đến", "tới", "đưa tôi", "chỉ đường", "hướng dẫn đường", "đường tới"]
    if any(k in text for k in nav_keywords):
        return True
    for place in LOCATIONS.keys():
        if place in text:
            return True
    return False

def normalize_place_from_text(text: str):
    if not text:
        return None
    for place in LOCATIONS.keys():
        if place in text:
            return place
    return None

def extract_digits(text: str) -> str:
    if not text:
        return ""
    return "".join(ch for ch in text if ch.isdigit())

# ==========================
# LLM GPT
# ==========================
SYSTEM_PROMPT = f"""
Bạn là robot hỗ trợ trong bệnh viện (trợ lý lễ tân + điều hướng).
Phong cách: thân thiện, tự nhiên như ChatGPT, tránh văn mẫu, có thể hỏi lại 1 câu ngắn để làm rõ khi cần.

Nguyên tắc an toàn:
- Thông tin y tế chỉ tham khảo, KHÔNG chẩn đoán, KHÔNG kê đơn.
- Nếu có dấu hiệu nguy hiểm (đau ngực/khó thở/ngất/liệt/chảy máu nhiều/sốt cao/lú lẫn/đau bụng dữ dội): khuyên gọi nhân viên y tế gần nhất / đi khu xử trí khẩn cấp.

Về dẫn đường:
- Bạn KHÔNG tự điều khiển robot.
- Nếu bạn nghĩ người dùng nên đến một nơi cụ thể, bạn có thể ĐỀ XUẤT dẫn đường tới đúng 1 địa điểm trong danh sách hợp lệ.
- Khi tư vấn triệu chứng, ưu tiên đề xuất "quầy lễ tân" để đăng ký khám (trừ khi rất khẩn cấp).

Danh sách địa điểm hợp lệ (CHỈ chọn trong list này): {list(LOCATIONS.keys())}

YÊU CẦU ĐẦU RA:
Chỉ trả về JSON đúng định dạng (không thêm văn bản ngoài JSON):
{{
  "reply": "<câu trả lời tự nhiên, rõ ràng>",
  "suggest_navigation": true/false,
  "suggested_place": "<địa điểm hợp lệ hoặc rỗng>"
}}
"""

def _extract_json(text: str):
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        return None

def ask_llm_api_with_memory(history_messages, user_text: str) -> dict:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"reply": "Tôi chưa được cấu hình khóa API để trả lời câu hỏi này.", "suggest_navigation": False, "suggested_place": ""}

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_text})

    payload = {"model": "gpt-4o-mini", "messages": messages, "temperature": 0.6}

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        obj = _extract_json(content)

        if not obj or "reply" not in obj:
            return {"reply": content.strip(), "suggest_navigation": False, "suggested_place": ""}

        suggest = bool(obj.get("suggest_navigation", False))
        place = (obj.get("suggested_place") or "").strip().lower()
        if suggest and place not in LOCATIONS:
            suggest = False
            place = ""
        if not suggest:
            place = ""

        return {"reply": str(obj.get("reply", "")).strip(), "suggest_navigation": suggest, "suggested_place": place}
    except Exception as e:
        rospy.logerr(f"Lỗi gọi LLM API: {e}")
        return {"reply": "Xin lỗi, hiện tại tôi không thể trả lời. Bạn vui lòng hỏi lại hoặc liên hệ nhân viên y tế.", "suggest_navigation": False, "suggested_place": ""}

# ==========================
# DIALOG (GIỮ NGUYÊN LOGIC)
# ==========================
class DialogManager:
    def __init__(self):
        self.mode = "idle"
        self.pending_nav = False

        self.history = []
        self.max_turns = 8

        self.awaiting_nav_confirm = False
        self.suggested_place = ""

        self.awaiting_insurance_id = False
        self.awaiting_phone = False

    def _push_history(self, role: str, content: str):
        if not content:
            return
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-self.max_turns * 2:]

    def _is_confirm(self, text: str) -> bool:
        if not text:
            return False
        yes_words = ["đồng ý", "ok", "oke", "được", "vâng", "dạ", "đi", "có", "yes", "ừ", "uh", "đúng rồi"]
        return any(w in text for w in yes_words)

    def _is_reject(self, text: str) -> bool:
        if not text:
            return False
        no_words = ["không", "thôi", "khỏi", "không cần", "no", "đừng"]
        return any(w in text for w in no_words)

    def _ask_confirm_nav_to_reception(self):
        self.suggested_place = "quầy lễ tân"
        self.awaiting_nav_confirm = True
        msg = "Bạn có muốn tôi dẫn bạn đến quầy lễ tân để đăng ký khám không ạ? Nếu đồng ý hãy nói: 'được' hoặc 'ok'."
        speak(msg)
        self._push_history("assistant", msg)
        self.mode = "chat"

    def _handle_llm_reply_and_optional_nav(self, command: str):
        llm = ask_llm_api_with_memory(self.history, command)
        reply = (llm.get("reply") or "").strip()
        suggest_nav = bool(llm.get("suggest_navigation", False))
        place = (llm.get("suggested_place") or "").strip().lower()

        if reply:
            speak(reply)
            self._push_history("assistant", reply)

        if suggest_nav and place in LOCATIONS:
            self.suggested_place = place
            self.awaiting_nav_confirm = True
            confirm_msg = f"Bạn có muốn tôi dẫn bạn đến {place} không ạ? Nếu đồng ý hãy nói: 'được' hoặc 'ok'."
            speak(confirm_msg)
            self._push_history("assistant", confirm_msg)
            self.mode = "chat"

    # ====== BHYT LOOKUP ======
    def _handle_insurance_id(self, command: str):
        digits = extract_digits(command)
        if len(digits) != 6:
            msg = "Mã BHYT gồm 6 số. Bạn nhập/đọc lại giúp tôi 6 số nhé."
            speak(msg)
            self._push_history("assistant", msg)
            return

        info = db_get_insurance(digits)
        if not info:
            msg = "Tôi không tìm thấy mã BHYT này trong dữ liệu demo. Bạn kiểm tra lại giúp tôi nhé."
            speak(msg)
            self._push_history("assistant", msg)
            return

        hard = (
            f"Mã BHYT: {info['insurance_id']}\n"
            f"Họ tên: {info['owner_name']}\n"
            f"Năm sinh: {info['dob_year']}\n"
            f"Số điện thoại: {info['phone']}\n"
            f"Hiệu lực: {info['valid_from']} đến {info['valid_to']}\n"
            f"Trạng thái: {'còn hạn' if info['is_valid'] else 'hết hạn'}\n"
            f"Yêu cầu chuyển tuyến: {'có' if info['referral_required'] else 'không'}\n"
            f"Có giấy chuyển tuyến: {'có' if info['referral_present'] else 'không'}\n"
        )

        prompt = (
            "Hãy diễn đạt thân thiện, rõ ràng cho người bệnh dựa trên dữ liệu sau (KHÔNG thêm thông tin bịa). "
            "Cuối cùng hỏi người bệnh có cần dẫn đường tới quầy lễ tân để đăng ký không.\n\n"
            f"{hard}\n\n"
            "Trong JSON, đặt suggest_navigation=false (vì robot sẽ hỏi dẫn đường riêng theo flow)."
        )

        llm = ask_llm_api_with_memory(self.history, prompt)
        reply = (llm.get("reply") or "").strip()
        if reply:
            speak(reply)
            self._push_history("assistant", reply)

        self.awaiting_insurance_id = False
        self._ask_confirm_nav_to_reception()

    # ====== PHONE LOOKUP ======
    def _handle_phone(self, command: str):
        digits = extract_digits(command)
        if len(digits) < 8:
            msg = "Tôi chưa thấy số điện thoại hợp lệ. Bạn nhập/đọc lại giúp tôi nhé."
            speak(msg)
            self._push_history("assistant", msg)
            return

        patient = db_get_patient_by_phone(digits)
        if not patient:
            msg = "Tôi không tìm thấy số điện thoại này trong dữ liệu demo. Bạn kiểm tra lại giúp tôi nhé."
            speak(msg)
            self._push_history("assistant", msg)
            return

        visits = db_get_recent_visits(patient["patient_id"], limit=2)
        last = visits[0] if visits else {}

        hard = (
            f"Số điện thoại: {patient['phone']}\n"
            f"Họ tên: {patient['name']}\n"
            f"Năm sinh: {patient['dob_year']}\n"
            f"Mã bệnh nhân: {patient['patient_id']}\n"
        )

        if last:
            hard += (
                f"Lần khám gần nhất: {last.get('visit_time','')}\n"
                f"Khoa: {last.get('department','')}\n"
                f"Lý do khám: {last.get('chief_complaint','')}\n"
                f"Đánh giá/tình trạng: {last.get('assessment','')}\n"
                f"Hướng dẫn lần trước: {last.get('plan','')}\n"
            )

        if len(visits) >= 2:
            v2 = visits[1]
            hard += (
                "\nLần khám trước đó:\n"
                f"- Thời gian: {v2.get('visit_time','')}\n"
                f"- Khoa: {v2.get('department','')}\n"
                f"- Lý do: {v2.get('chief_complaint','')}\n"
            )

        prompt = (
            "Hãy tóm tắt thân thiện cho người bệnh hồ sơ dựa trên dữ liệu sau (KHÔNG thêm thông tin bịa). "
            "Cuối cùng hỏi người bệnh có cần dẫn đường tới quầy lễ tân để đăng ký khám lại không.\n\n"
            f"{hard}\n\n"
            "Trong JSON, đặt suggest_navigation=false (vì robot sẽ hỏi dẫn đường riêng theo flow)."
        )

        llm = ask_llm_api_with_memory(self.history, prompt)
        reply = (llm.get("reply") or "").strip()
        if reply:
            speak(reply)
            self._push_history("assistant", reply)

        self.awaiting_phone = False
        self._ask_confirm_nav_to_reception()

    def _handle_symptom_with_gpt(self, user_symptom_text: str):
        triage_prompt = f"""
Người dùng đang mô tả TRIỆU CHỨNG. Hãy trả lời mượt như tư vấn ban đầu:
1) Giải thích ngắn gọn khả năng liên quan (không chẩn đoán chắc chắn).
2) GỢI Ý NÊN KHÁM Ở KHOA NÀO trong các khoa sau (chỉ chọn 1 khoa phù hợp nhất):
- khoa nội, khoa nhi, khoa tai mũi họng, khoa sản, khoa ngoại, khoa hồi sức gây mê.
3) Hỏi thêm 2–4 câu quan trọng để làm rõ.
4) Nhắc các dấu hiệu cần đi xử trí khẩn cấp nếu có liên quan.
5) Kết thúc bằng câu hỏi: "Bạn có muốn tôi dẫn đường tới quầy lễ tân để đăng ký khám không?"

YÊU CẦU ĐẶC BIỆT VỀ JSON:
- Vì quy trình bệnh viện thường cần đăng ký, hãy đặt:
  "suggest_navigation": true
  "suggested_place": "quầy lễ tân"
(trừ khi tình huống có vẻ cực kỳ nguy hiểm, khi đó suggested_place có thể là "khoa hồi sức gây mê".)

Triệu chứng người dùng: {user_symptom_text}
"""
        self._handle_llm_reply_and_optional_nav(triage_prompt)
        self.mode = "chat"

    def handle(self, command: str):
        if not command:
            return

        command = command.lower().strip()
        self._push_history("user", command)

        # ====== 0) Nếu đang chờ nhập BHYT / SĐT ======
        if self.awaiting_insurance_id:
            self._handle_insurance_id(command)
            return

        if self.awaiting_phone:
            self._handle_phone(command)
            return

        # ====== 1) Nếu đang chờ user xác nhận dẫn đường ======
        if self.awaiting_nav_confirm:
            if self._is_confirm(command):
                place = self.suggested_place
                if place in LOCATIONS:
                    msg = f"Được ạ. Tôi sẽ dẫn bạn đến {place}."
                    speak(msg)
                    self._push_history("assistant", msg)
                    move_to_goal(place, LOCATIONS[place])
                else:
                    msg = "Xin lỗi, tôi không xác định được địa điểm. Bạn nói lại giúp tôi nhé."
                    speak(msg)
                    self._push_history("assistant", msg)

                self.awaiting_nav_confirm = False
                self.suggested_place = ""
                self.mode = "idle"
                return

            if self._is_reject(command):
                msg = "Vâng ạ. Bạn muốn tôi hỗ trợ gì tiếp theo?"
                speak(msg)
                self._push_history("assistant", msg)
                self.awaiting_nav_confirm = False
                self.suggested_place = ""
                self.mode = "chat"
                return

            msg = "Bạn có muốn tôi dẫn đường không ạ? Nếu đồng ý hãy nói: 'được' hoặc 'ok'."
            speak(msg)
            self._push_history("assistant", msg)
            return

        # ====== 2) Lệnh chung ======
        if "cảm ơn" in command or "tạm biệt" in command:
            msg = "Xin cảm ơn. Chào tạm biệt."
            speak(msg)
            self._push_history("assistant", msg)
            move_to_goal("trạm sạc", LOCATIONS["trạm sạc"])
            self.mode = "idle"
            self.pending_nav = False
            return

        if "dừng lại" in command or "dừng" in command:
            msg = "Đã nhận lệnh dừng. Nếu bạn cần dẫn đường hoặc hỏi thông tin, cứ nói với tôi."
            speak(msg)
            self._push_history("assistant", msg)
            return

        # ====== 3) An toàn y tế ======
        if has_danger_signs(command):
            msg = "Tôi nghe có dấu hiệu nguy hiểm. Bạn nên báo nhân viên y tế ngay. Nếu được, tôi có thể dẫn bạn đến khoa hồi sức gây mê hoặc quầy lễ tân."
            speak(msg)
            self._push_history("assistant", msg)
            self.mode = "chat"
            return

        # ====== 4) Pending nav ======
        if self.pending_nav:
            place = normalize_place_from_text(command)
            if place:
                move_to_goal(place, LOCATIONS[place])
                self.pending_nav = False
                self.mode = "idle"
            else:
                msg = "Bạn muốn đến đâu ạ? Ví dụ: khoa nội, khoa nhi, tai mũi họng, khoa sản, khoa ngoại, quầy lễ tân."
                speak(msg)
                self._push_history("assistant", msg)
            return

        # ====== 5) Request dẫn đường ======
        if looks_like_navigation_request(command):
            place = normalize_place_from_text(command)
            if place:
                move_to_goal(place, LOCATIONS[place])
                self.mode = "idle"
                return
            else:
                msg = "Bạn muốn tôi dẫn đến đâu ạ? Ví dụ: khoa nội, khoa nhi, tai mũi họng, khoa sản, khoa ngoại, quầy lễ tân."
                speak(msg)
                self._push_history("assistant", msg)
                self.pending_nav = True
                self.mode = "nav"
                return

        # ====== 6) BHYT ======
        if ("bảo hiểm y tế" in command) or ("bhyt" in command) or ("bảo hiểm" in command and "y tế" in command):
            msg = "Bạn muốn tôi hướng dẫn thủ tục chung hay kiểm tra thẻ BHYT theo mã 6 số ạ?"
            speak(msg)
            self._push_history("assistant", msg)

            if "kiểm tra" in command or len(extract_digits(command)) == 6:
                # cho phép nhập thẳng mã ngay trong câu
                self.awaiting_insurance_id = True
                self._handle_insurance_id(command)
            else:
                self.awaiting_insurance_id = True
                ask = "Bạn nhập hoặc đọc giúp tôi mã BHYT 6 số nhé."
                speak(ask)
                self._push_history("assistant", ask)

            self.mode = "chat"
            return

        # ====== 7) Tra cứu theo SĐT ======
        if ("số điện thoại" in command) or ("tra cứu" in command and "điện thoại" in command) or ("tra cứu bệnh nhân" in command):
            self.awaiting_phone = True
            msg = "Bạn nhập hoặc đọc số điện thoại đăng ký để tôi tra cứu hồ sơ."
            speak(msg)
            self._push_history("assistant", msg)

            if len(extract_digits(command)) >= 8:
                self._handle_phone(command)
            return

        # ====== 8) FAQ ======
        faq_ans = match_faq(command)
        if faq_ans:
            self._handle_llm_reply_and_optional_nav(
                f"Hãy giải thích tự nhiên, dễ hiểu cho người bệnh nội dung sau (không thêm thông tin bịa): {faq_ans}"
            )
            follow = "Bạn muốn tôi hướng dẫn thêm bước nào nữa không ạ?"
            speak(follow)
            self._push_history("assistant", follow)
            self.mode = "chat"
            return

        # ====== 9) TRIỆU CHỨNG ======
        if any(k in command for k in ["bị", "đau", "ho", "sốt", "viêm", "buồn nôn", "tiêu chảy", "đau đầu", "chóng mặt", "mệt", "nôn", "khó ngủ"]):
            self._handle_symptom_with_gpt(command)
            return

        # ====== 10) Mode chat => AI trả lời ======
        if self.mode == "chat":
            self._handle_llm_reply_and_optional_nav(command)
            return

        # ====== 11) Fallback => AI ======
        self._handle_llm_reply_and_optional_nav(command)
        if not self.awaiting_nav_confirm:
            msg = "Bạn cần tôi hỗ trợ gì nữa không ạ? Bạn có thể hỏi thủ tục, bảo hiểm y tế, tra cứu theo số điện thoại, hoặc nhờ dẫn đường."
            speak(msg)
            self._push_history("assistant", msg)

# ==========================
# GUI ( nhập BHYT/SĐT + gửi message)
# ==========================
class ChatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Hospital Robot Assistant")
        self.root.geometry("920x620")
        self.root.configure(bg="#EAF6FF")

        # Header
        header = tk.Frame(root, bg="#0B74B8", height=56)
        header.pack(fill=tk.X, side=tk.TOP)

        title = tk.Label(
            header,
            text="Hospital Robot • Voice Assistant",
            bg="#0B74B8",
            fg="white",
            font=("DejaVu Sans", 16, "bold")
        )
        title.pack(side=tk.LEFT, padx=16, pady=12)

        self.status = tk.Label(
            header,
            text="● Online",
            bg="#0B74B8",
            fg="#D1FADF",
            font=("DejaVu Sans", 12, "bold")
        )
        self.status.pack(side=tk.RIGHT, padx=16)

        # Body
        body = tk.Frame(root, bg="#EAF6FF")
        body.pack(fill=tk.BOTH, expand=True)

        self.text = ScrolledText(
            body,
            wrap=tk.WORD,
            font=("DejaVu Sans", 12),
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=12
        )
        self.text.pack(fill=tk.BOTH, expand=True, padx=14, pady=(14, 10))
        self.text.configure(state=tk.DISABLED, bg="#F8FBFF")

        self.text.tag_configure("user", background="#D6F5D6", foreground="#0B2E13",
                                lmargin1=90, lmargin2=90, rmargin=10, spacing1=4, spacing3=8)
        self.text.tag_configure("robot", background="#D6E9FF", foreground="#06233B",
                                lmargin1=10, lmargin2=10, rmargin=90, spacing1=4, spacing3=8)
        self.text.tag_configure("meta", foreground="#6B7280", lmargin1=10, lmargin2=10, rmargin=10)

        # Footer controls
        footer = tk.Frame(root, bg="#EAF6FF")
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        # Row 1: BHYT + SĐT lookup
        row1 = tk.Frame(footer, bg="#EAF6FF")
        row1.pack(fill=tk.X, padx=14, pady=(6, 2))

        # BHYT
        bhyt_box = tk.Frame(row1, bg="#FFFFFF", bd=0, highlightthickness=1, highlightbackground="#CFE8FF")
        bhyt_box.pack(side=tk.LEFT, padx=(0, 10), pady=6)

        tk.Label(bhyt_box, text="Mã BHYT (6 số)", bg="#FFFFFF", fg="#0B74B8",
                 font=("DejaVu Sans", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))

        self.bhyt_entry = tk.Entry(bhyt_box, font=("DejaVu Sans", 12), bd=0, width=18)
        self.bhyt_entry.pack(side=tk.LEFT, padx=10, pady=(0, 10))
        self.bhyt_entry.bind("<Return>", lambda e: self.lookup_bhyt())

        tk.Button(
            bhyt_box, text="Tra cứu BHYT", command=self.lookup_bhyt,
            bg="#0B74B8", fg="white", relief=tk.FLAT,
            font=("DejaVu Sans", 11, "bold"), padx=10, pady=6
        ).pack(side=tk.LEFT, padx=(0, 10), pady=(0, 10))

        # Phone
        phone_box = tk.Frame(row1, bg="#FFFFFF", bd=0, highlightthickness=1, highlightbackground="#CFE8FF")
        phone_box.pack(side=tk.LEFT, padx=(0, 10), pady=6)

        tk.Label(phone_box, text="Số điện thoại", bg="#FFFFFF", fg="#0B74B8",
                 font=("DejaVu Sans", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))

        self.phone_entry = tk.Entry(phone_box, font=("DejaVu Sans", 12), bd=0, width=22)
        self.phone_entry.pack(side=tk.LEFT, padx=10, pady=(0, 10))
        self.phone_entry.bind("<Return>", lambda e: self.lookup_phone())

        tk.Button(
            phone_box, text="Tra cứu SĐT", command=self.lookup_phone,
            bg="#0B74B8", fg="white", relief=tk.FLAT,
            font=("DejaVu Sans", 11, "bold"), padx=10, pady=6
        ).pack(side=tk.LEFT, padx=(0, 10), pady=(0, 10))

        # Clear
        tk.Button(
            row1,
            text="Clear chat",
            command=self.clear_chat,
            bg="#FFFFFF",
            fg="#0B74B8",
            relief=tk.FLAT,
            font=("DejaVu Sans", 11, "bold"),
            padx=12,
            pady=10
        ).pack(side=tk.RIGHT, padx=0, pady=6)

        # Row 2: typed chat input (optional)
        row2 = tk.Frame(footer, bg="#EAF6FF")
        row2.pack(fill=tk.X, padx=14, pady=(2, 10))

        chat_box = tk.Frame(row2, bg="#FFFFFF", bd=0, highlightthickness=1, highlightbackground="#CFE8FF")
        chat_box.pack(fill=tk.X, expand=True)

        self.chat_entry = tk.Entry(chat_box, font=("DejaVu Sans", 12), bd=0)
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=10)
        self.chat_entry.bind("<Return>", lambda e: self.send_chat())

        tk.Button(
            chat_box, text="Gửi",
            command=self.send_chat,
            bg="#16A34A", fg="white",
            relief=tk.FLAT,
            font=("DejaVu Sans", 11, "bold"),
            padx=14, pady=8
        ).pack(side=tk.RIGHT, padx=10, pady=8)

        # Poll queue + update status
        self.root.after(100, self.poll_queue)

    def clear_chat(self):
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)

    def add_bubble(self, who: str, msg: str):
        self.text.configure(state=tk.NORMAL)
        if who == "user":
            self.text.insert(tk.END, f"Bạn: {msg}\n", ("user",))
        else:
            self.text.insert(tk.END, f"Robot: {msg}\n", ("robot",))
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def _only_digits(self, s: str) -> str:
        return "".join(ch for ch in (s or "") if ch.isdigit())

    def lookup_bhyt(self):
        digits = self._only_digits(self.bhyt_entry.get())
        if len(digits) != 6:
            gui_push("robot", "⚠️ Vui lòng nhập mã BHYT đúng 6 số.")
            speak("Bạn vui lòng nhập mã BHYT đúng 6 số trên giao diện nhé.")
            return

        # Gửi câu lệnh vào pipeline y hệt voice (GIỮ LOGIC)
        cmd = f"bhyt kiểm tra {digits}"
        gui_push("user", f"[GUI] {cmd}")
        gui_send_command(cmd)

    def lookup_phone(self):
        digits = self._only_digits(self.phone_entry.get())
        if len(digits) < 8:
            gui_push("robot", "⚠️ Vui lòng nhập số điện thoại hợp lệ.")
            speak("Bạn vui lòng nhập số điện thoại hợp lệ trên giao diện nhé.")
            return

        cmd = f"tra cứu bệnh nhân theo số điện thoại {digits}"
        gui_push("user", f"[GUI] {cmd}")
        gui_send_command(cmd)

    def send_chat(self):
        text = (self.chat_entry.get() or "").strip()
        if not text:
            return
        self.chat_entry.delete(0, tk.END)
        gui_push("user", f"[GUI] {text}")
        gui_send_command(text)

    def poll_queue(self):
        key = os.getenv("OPENAI_API_KEY")
        if key:
            self.status.configure(text="● Online", fg="#D1FADF")
        else:
            self.status.configure(text="● No API Key", fg="#FFD9D9")

        try:
            while True:
                role, msg = CHAT_Q.get_nowait()
                if role == "user":
                    self.add_bubble("user", msg)
                elif role == "robot":
                    self.add_bubble("robot", msg)
                else:
                    self.text.configure(state=tk.NORMAL)
                    self.text.insert(tk.END, str(msg) + "\n", ("meta",))
                    self.text.configure(state=tk.DISABLED)
        except queue.Empty:
            pass

        self.root.after(100, self.poll_queue)

def ros_loop():
    rospy.init_node('voice_navigation_node', disable_signals=True)

    if not os.path.exists(DB_PATH):
        rospy.logerr(f"Không tìm thấy DB: {DB_PATH}")
        speak("Tôi không tìm thấy cơ sở dữ liệu demo. Bạn kiểm tra lại file hospital_demo.db giúp tôi nhé.")

    dialog = DialogManager()

    rospy.sleep(1)
    speak("Xin chào. Tôi là robot bệnh viện. Bạn cần giúp đỡ gì? Bạn có thể hỏi bảo hiểm y tế, tra cứu theo số điện thoại, hoặc nhờ dẫn đường đến quầy lễ tân.")

    while not rospy.is_shutdown():
        # ====== ƯU TIÊN command từ GUI (NEW) ======
        try:
            gui_cmd = CMD_Q.get_nowait()
        except queue.Empty:
            gui_cmd = None

        if gui_cmd:
            # log như user (để GUI thấy rõ)
            rospy.loginfo(f"[GUI CMD] {gui_cmd}")
            # dialog dùng chung pipeline
            dialog.handle(gui_cmd)
            rospy.sleep(0.05)
            continue

        # ====== nếu không có GUI cmd thì nghe mic như cũ ======
        command = listen()
        if command:
            dialog.handle(command)
        rospy.sleep(0.2)

def main_with_gui():
    t = threading.Thread(target=ros_loop, daemon=True)
    t.start()

    root = tk.Tk()
    _ = ChatGUI(root)
    root.mainloop()

if __name__ == '__main__':
    try:
        main_with_gui()
    except rospy.ROSInterruptException:
        pass
