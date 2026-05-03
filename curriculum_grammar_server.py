#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Myanmar AI Backend Server v2.0.0
Grammar Check + Curriculum Data + NLP Tools REST API
Deploy on Render.com (free tier)
NLP: Zawgyi/Unicode, Syllable Tokenizer, Word Tokenizer, Spell Check
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

import requests as http_requests

from flask import Flask, request, jsonify
from flask_cors import CORS
from storage_onedrive import register_storage_routes

# Import NLP tools
from nlp_tools import (
    zawgyi_to_unicode, unicode_to_zawgyi, detect_encoding,
    syllable_tokenize, word_tokenize, spell_check, get_module_info
)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ============================================================
# Grammar Rules Engine (MA_01 - MA_10)
# ============================================================

def _near(text, match, keyword, before=25, after=25):
    region = text[max(0, match.start() - before):match.start() + after]
    return keyword in region


RULES: List[Dict[str, Any]] = [
    {
        "id": "MA_01",
        "name": "ပဲ နှင့် ဘဲ ခွဲခြားခြင်း",
        "pattern": "ပဲ",
        "context_check": lambda m, t: (
            _near(t, m, "မစား") or _near(t, m, "မသွား") or
            _near(t, m, "မလောက်") or _near(t, m, "မကြည့်") or
            _near(t, m, "မလုပ်") or _near(t, m, "မဖိအား")
        ) and not _near(t, m, "မပဲ", 10, 3),
        "error": "ငြင်းဆိုသော ဝါကျတွင် 'ပဲ' အစား 'ဘဲ' သုံးသင့်သည်",
        "suggestion": "ဘဲ",
        "example_fix": "မစားပဲ → မစားဘဲ"
    },
    {
        "id": "MA_02",
        "name": "ဖူး နှင့် ဘူး ခွဲခြားခြင်း",
        "pattern": "ဖူး",
        "context_check": lambda m, t: False,
        "error": "ငြင်းပယ်လိုလျှင် 'ဘူး' သုံးသင့်သည်",
        "suggestion": "ဘူး",
        "example_fix": "မလုပ်ဖူး → မလုပ်ဘူး (context-sensitive, disabled)"
    },
    {
        "id": "MA_03",
        "name": "ကို နှင့် အား ခွဲခြားခြင်း",
        "pattern": "ကို",
        "context_check": lambda m, t: (
            _near(t, m, "လေးစား", 5, 30) or
            _near(t, m, "ရှိခိုး", 5, 30) or
            _near(t, m, "ပဲ့ဆို", 5, 30) or
            _near(t, m, "ဝမ်းမြောက်", 5, 30) or
            _near(t, m, "မြင်", 5, 30) or
            _near(t, m, "နှုတ်ဆင်", 5, 30)
        ),
        "error": "လေးစားရမှုဖော်ပြရာတွင် 'ကို' အစား 'အား' သုံးသင့်သည်",
        "suggestion": "အား",
        "example_fix": "ဆရာကို လေးစားသည် → ဆရာအား လေးစားသည်"
    },
    {
        "id": "MA_04",
        "name": "မှ နှင့် က (ထွက်ရာ/နေရာ)",
        "pattern": "မှ",
        "context_check": lambda m, t: (
            _near(t, m, "လာ", 0, 30) or
            _near(t, m, "သွား", 0, 30) or
            _near(t, m, "ရောက်", 0, 30) or
            _near(t, m, "ထွက်", 0, 30) or
            _near(t, m, "ပေါ်", 0, 15)
        ),
        "error": "ထွက်ရာဌာနနာမ်အတွက် 'မှ' အစား 'က' သုံးသင့်သည်",
        "suggestion": "က",
        "example_fix": "ရန်ကုန်မှ လာတယ် → ရန်ကုန်က လာတယ်"
    },
    {
        "id": "MA_05",
        "name": "သညျ အမှားသုံးခြင်း",
        "pattern": "သညျ",
        "context_check": None,
        "error": "'သညျ' သည် မြန်မာစာတွင် အဓိပ္ပာယ်ရသော စကားမဟုတ်ပါ",
        "suggestion": "သည် / မှာ",
        "example_fix": "ကျောင်းသညျ ရှိတယ် → ကျောင်းမှာ ရှိသည်"
    },
    {
        "id": "MA_06",
        "name": "အင်္ဂလိပ် ဂဏန်း သုံးခြင်း",
        "pattern": r'[0-9]+',
        "context_check": lambda m, t: bool(
            re.search(r'[\u1000-\u109F]', t[max(0, m.start() - 10):m.start()]) or
            re.search(r'[\u1000-\u109F]', t[m.end():m.end() + 10])
        ),
        "error": "အင်္ဂလိပ်ဂဏန်းအစား မြန်မာဂဏန်း သုံးသင့်သည်",
        "suggestion": "မြန်မာဂဏန်း (၀၁၂၃၄၅၆၇၈၉)",
        "example_fix": "25 → ၂၅"
    },
    {
        "id": "MA_07",
        "name": "ခဲ့ဖူး ထပ်သုံးခြင်း",
        "pattern": r"ခဲ့[\s\u200B]*?" + "ဖူး",
        "context_check": None,
        "error": "'ခဲ့' နှင့် 'ဖူး' ထပ်မသုံးသင့်ပါ၊ တစ်ခုတည်းသုံးပါ",
        "suggestion": "ခဲ့",
        "example_fix": "သွားခဲ့ဖူး → သွားခဲ့"
    },
    {
        "id": "MA_08",
        "name": "ခဲ့ခဲ့ ထပ်သုံးခြင်း",
        "pattern": r"ခဲ့[\s\u200B]*?ခဲ့",
        "context_check": None,
        "error": "'ခဲ့' ကို နှစ်ကြိမ် ထပ်မသုံးသင့်ပါ",
        "suggestion": "ခဲ့ (တစ်ကြိမ်သာ)",
        "example_fix": "သွားခဲ့ခဲ့ → သွားခဲ့"
    },
    {
        "id": "MA_09",
        "name": "မဟုတ်ဘုး မမှန်ကန်ခြင်း",
        "pattern": "မဟုတ်ဘုး",
        "context_check": None,
        "error": "'ဘုး' သည် ခေါ်ဝေါ်သော အသုံးစွဲဖြစ်သည်၊ 'ဘူး' သုံးသင့်သည်",
        "suggestion": "မဟုတ်ဘူး",
        "example_fix": "မဟုတ်ဘုး → မဟုတ်ဘူး"
    },
    {
        "id": "MA_10",
        "name": "ပုဒ်မ နှစ်ခုဆက်သုံးခြင်း",
        "pattern": "\u104b\u104b",
        "context_check": None,
        "error": "မြန်မာပုဒ်မ '။' နှစ်ကြိမ်ထပ်နေသည်၊ တစ်ကြိမ်သာ သုံးသင့်သည်",
        "suggestion": "။ (တစ်ခုသာ)",
        "example_fix": "ပြီးပြီ။။ → ပြီးပြီ။"
    },
]

NUMERAL_MAP = {
    '0': '၀', '1': '၁', '2': '၂', '3': '၃', '4': '၄',
    '5': '၅', '6': '၆', '7': '၇', '8': '၈', '9': '၉'
}


def check_grammar(text: str) -> Dict[str, Any]:
    if not text or not text.strip():
        return {
            "text": text,
            "errors": [],
            "error_count": 0,
            "is_correct": True,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    errors = []
    seen = set()

    for rule in RULES:
        pat = rule["pattern"]
        if isinstance(pat, str) and not pat.startswith(r'\\'):
            if not any(c in pat for c in r'[](){}*+?|.^$\\'):
                pat = re.escape(pat)

        try:
            matches = list(re.finditer(pat, text, re.UNICODE))
        except re.error:
            try:
                matches = list(re.finditer(re.escape(rule["pattern"]), text, re.UNICODE))
            except Exception:
                continue

        ctx_fn = rule.get("context_check")

        for match in matches:
            if ctx_fn and not ctx_fn(match, text):
                continue
            key = (match.start(), rule["id"])
            if key in seen:
                continue
            seen.add(key)

            suggestion_val = rule["suggestion"]
            if rule["id"] == "MA_06":
                myanmar_num = "".join(NUMERAL_MAP.get(c, c) for c in match.group(0))
                suggestion_val = myanmar_num

            errors.append({
                "rule_id": rule["id"],
                "description": rule["error"],
                "original": match.group(0),
                "suggestion": suggestion_val,
                "position": match.start()
            })

    return {
        "text": text,
        "errors": errors,
        "error_count": len(errors),
        "is_correct": len(errors) == 0,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }


# ============================================================
# Curriculum Data
# ============================================================

# Grade ID mapping (both formats accepted)
GRADE_ALIASES = {
    "kg": "KG",
    "g1": "G1", "g2": "G2", "g3": "G3", "g4": "G4",
    "g5": "G5", "g6": "G6", "g7": "G7", "g8": "G8",
    "g9": "G9", "g10": "G10", "g11": "G11",
}

# Load curriculum from JSON file
CURRICULUM_DATA = None

def load_curriculum():
    global CURRICULUM_DATA
    if CURRICULUM_DATA is not None:
        return CURRICULUM_DATA

    # Try multiple paths
    paths = [
        os.path.join(os.path.dirname(__file__), "myanmar-education-curriculum-training.json"),
        "/home/z/my-project/download/myanmar-education-curriculum-training.json",
        "myanmar-education-curriculum-training.json",
    ]

    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    CURRICULUM_DATA = json.load(f)
                return CURRICULUM_DATA
            except Exception:
                continue

    return None


def get_grade_data(grade_id: str, subject: str = None) -> Dict[str, Any]:
    data = load_curriculum()
    if data is None:
        return {"error": "Curriculum data file not found", "status": "error"}

    # Normalize grade
    normalized = GRADE_ALIASES.get(grade_id.lower(), grade_id.upper())

    # Find the grade
    grade_entry = None
    for g in data.get("grades", []):
        g_label = g.get("grade", "")
        # Match by checking if grade label contains the normalized ID
        if normalized in g_label or g_label.startswith(normalized):
            grade_entry = g
            break

    if grade_entry is None:
        available = [g.get("grade", "") for g in data.get("grades", [])]
        return {
            "error": f"Grade '{grade_id}' not found",
            "available_grades": available,
            "status": "error"
        }

    result = {
        "grade": grade_entry.get("grade", normalized),
        "grade_local": grade_entry.get("grade_local", ""),
        "level": grade_entry.get("level", ""),
        "age_range": grade_entry.get("age_range", ""),
        "status": "success"
    }

    # Subjects
    subjects = grade_entry.get("subjects", [])
    textbook_links = grade_entry.get("textbook_links", [])

    if subject and subject.lower() != "all":
        # Filter by subject
        subject_lower = subject.lower()
        matching = []
        for s in subjects:
            if (subject_lower in s.get("name_english", "").lower() or
                    subject_lower in s.get("name_myanmar", "").lower()):
                matching.append(s)
        for t in textbook_links:
            if (subject_lower in t.get("name_english", "").lower() or
                    subject_lower in t.get("name_myanmar", "").lower()):
                matching.append(t)
        result["data"] = matching
    else:
        # Return all subjects
        if textbook_links:
            result["data"] = textbook_links
        else:
            result["data"] = subjects

    # Add parental advice if available
    if grade_entry.get("parental_advice"):
        result["parental_advice"] = grade_entry["parental_advice"]

    # Add notes
    if grade_entry.get("notes"):
        result["notes"] = grade_entry["notes"]

    # Add matriculation tracks for G10
    if grade_entry.get("matriculation_tracks"):
        result["matriculation_tracks"] = grade_entry["matriculation_tracks"]

    # Add exam preparation for G11
    if grade_entry.get("exam_preparation"):
        result["exam_preparation"] = grade_entry["exam_preparation"]

    return result


# ============================================================
# API Routes
# ============================================================

@app.route("/", methods=["GET"])
def api_home():
    return jsonify({
        "service": "Myanmar AI Backend",
        "version": "1.0.0",
        "status": "online",
        "endpoints": {
            "POST /api/grammar-check": {
                "description": "မြန်မာသဒ္ဒါ စစ်ဆေးခြင်း",
                "body": {"text": "စာသား"},
                "content_type": "application/json"
            },
            "GET /api/curriculum": {
                "description": "သင်ရိုးညွှန်းတမ်း ဒေတာ",
                "params": {"grade": "KG, G1-G11 (required)", "subject": "optional filter"}
            },
            "GET /api/rules": {
                "description": "သဒ္ဒါစည်းမျဉ်း စာရင်း"
            },
            "GET /api/health": {
                "description": "စနစ်ကွန်ပျူတာအခြေအနေ"
            },
            "GET /api/tool-definitions": {
                "description": "GLM-5-TURBO Agent Tool Definitions"
            },
            "POST /api/termux-exec": {
                "description": "Termux terminal command execution",
                "body": {"command": "ls"},
                "content_type": "application/json"
            },
            "POST /api/zawgyi-to-unicode": {
                "description": "ဇော်ဂျီကို မြန်မာစကားသို့ ပြောင်းလဲခြင်း",
                "body": {"text": "ဇော်ဂျီစာသား"},
                "content_type": "application/json"
            },
            "POST /api/syllable-tokenize": {
                "description": "မြန်မာစာကို သီအိုရီများ အဖြစ် ဖွဲ့စည်းခြင်း",
                "body": {"text": "မြန်မာစာသား"},
                "content_type": "application/json"
            },
            "POST /api/word-tokenize": {
                "description": "မြန်မာစာကို စကားလုံးများ အဖြစ် ဖွဲ့စည်းခြင်း",
                "body": {"text": "ကျွန်တော် အလုပ်သွားမယ်"},
                "content_type": "application/json"
            },
            "POST /api/spell-check": {
                "description": "မြန်မာစာ အကြောင်းစစ် (သဒ္ဒါစစ်ဆေးခြင်း နှင့် အကြုံပြုခြင်း)",
                "body": {"text": "မစားပဲ မသွားပဲ"},
                "content_type": "application/json"
            },
            "GET /api/nlp-info": {
                "description": "NLP Tools အချက်အလက်"
            }
        }
    })


@app.route("/api/health", methods=["GET"])
def api_health():
    data = load_curriculum()
    nlp_info = get_module_info()
    return jsonify({
        "status": "online",
        "uptime": "ok",
        "curriculum_loaded": data is not None,
        "grammar_rules": len(RULES),
        "nlp_tools": nlp_info,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route("/api/grammar-check", methods=["POST"])
def api_grammar_check():
    if not request.is_json:
        return jsonify({
            "error": "Content-Type must be application/json",
            "status": "error"
        }), 400

    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({
            "error": "Missing 'text' field in request body",
            "status": "error",
            "example": {"text": "မစားပဲ မသွားပဲ"}
        }), 400

    text = body["text"]
    if not text or not text.strip():
        return jsonify({
            "error": "Empty text provided",
            "status": "error"
        }), 400

    result = check_grammar(text)
    return jsonify(result)


@app.route("/api/curriculum", methods=["GET"])
def api_curriculum():
    grade = request.args.get("grade", "").strip()
    subject = request.args.get("subject", "").strip()

    if not grade:
        return jsonify({
            "error": "Missing 'grade' parameter",
            "status": "error",
            "available_grades": list(GRADE_ALIASES.values()),
            "example": "/api/curriculum?grade=G1"
        }), 400

    result = get_grade_data(grade, subject if subject else None)
    status_code = 200 if result.get("status") == "success" else 404
    return jsonify(result), status_code


@app.route("/api/rules", methods=["GET"])
def api_rules():
    return jsonify({
        "tool": "myanmar_grammar_tool",
        "version": "1.0.0",
        "rules_count": len(RULES),
        "rules": [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["error"],
                "suggestion": r["suggestion"],
                "example_fix": r.get("example_fix", "")
            }
            for r in RULES
        ]
    })


@app.route("/api/tool-definitions", methods=["GET"])
def api_tool_definitions():
    """Return tool definitions for GLM-5-TURBO agent integration"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "check_myanmar_grammar",
                "description": "ပေးလိုက်သော မြန်မာစာသားအတွင်း အဖြစ်များသော သဒ္ဒါအမှားများ (ပဲ/ဘဲ၊ ကို/အား၊ မှ/က စသည်) ကို စစ်ဆေးပေးသည်။",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "စစ်ဆေးလိုသော မြန်မာစာသား"}
                    },
                    "required": ["text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_myanmar_curriculum",
                "description": "မြန်မာအခြေခံပညာ အတန်းလိုက် သင်ရိုးအချက်အလက်များကို ရယူရန်။",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "grade": {"type": "string", "description": "KG, G1, G2, ..., G11"},
                        "subject": {"type": "string", "description": "ဘာသာရပ် (optional)"}
                    },
                    "required": ["grade"]
                }
            }
        }
    ]
    tools.append({
        "type": "function",
        "function": {
            "name": "exec_myanmar_terminal",
            "description": "Termux terminal မှာ command တစ်ခုခု run ပြီး result ကို ပြန်ပေးမယ်။ (ဥပမာ - ls, python, npm, git, pkg)",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Termux မှာ run ချင်တဲ့ exact command"}
                },
                "required": ["command"]
            }
        }
    })

    return jsonify({
        "tools": tools,
        "status": "success",
        "base_url": request.base_url.replace("/api/tool-definitions", "")
    })


@app.route("/api/termux-exec", methods=["POST"])
def api_termux_exec():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json", "status": "error"}), 400

    data = request.get_json(silent=True)
    if not data or "command" not in data:
        return jsonify({"error": "Missing 'command' field", "status": "error"}), 400

    command = data["command"].strip()
    if not command:
        return jsonify({"error": "Empty command", "status": "error"}), 400

    # Allowed safe commands whitelist
    ALLOWED_PREFIXES = [
        "ls", "pwd", "whoami", "date", "echo", "cat", "head",
        "tail", "wc", "grep", "find", "python", "python3",
        "pip", "npm", "node", "git", "curl", "wget",
        "pkg", "apt", "mkdir", "touch", "cp", "mv",
        "chmod", "uname", "df", "free", "ps", "env",
        "which", "man", "history", "clear", "help",
    ]

    # Check if command starts with an allowed prefix
    cmd_first = command.split()[0] if command.split() else ""
    allowed = False
    for prefix in ALLOWED_PREFIXES:
        if cmd_first == prefix or command.startswith(prefix + " "):
            allowed = True
            break

    if not allowed:
        return jsonify({
            "error": f"Command '{cmd_first}' is not in the allowed list",
            "status": "blocked",
            "allowed_commands": ALLOWED_PREFIXES
        }), 403

    # Forward to Puter terminal
    puter_url = os.environ.get("PUTER_EXEC_URL", "https://helpful-cat-7216.puter.site/exec")
    try:
        resp = http_requests.post(puter_url, json={"command": command}, timeout=30)
        return jsonify(resp.json())
    except http_requests.exceptions.Timeout:
        return jsonify({"error": "Puter terminal timeout after 30s", "status": "timeout"}), 504
    except Exception as e:
        return jsonify({"error": f"Puter connection failed: {str(e)}", "status": "error"}), 502


# ============================================================
# NLP Tool Routes
# ============================================================

@app.route("/api/zawgyi-to-unicode", methods=["POST"])
def api_zawgyi_to_unicode():
    """Convert Zawgyi-encoded Myanmar text to Unicode standard."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json", "status": "error"}), 400

    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({
            "error": "Missing 'text' field in request body",
            "status": "error",
            "example": {"text": "ဇော်ဂျီစာသား"}
        }), 400

    text = body["text"]
    if not text or not text.strip():
        return jsonify({"error": "Empty text provided", "status": "error"}), 400

    detected = detect_encoding(text)
    converted = zawgyi_to_unicode(text)

    return jsonify({
        "original": text,
        "unicode": converted,
        "detected_encoding": detected,
        "status": "success",
        "length": len(text)
    })


@app.route("/api/syllable-tokenize", methods=["POST"])
def api_syllable_tokenize():
    """Break Myanmar text into syllables."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json", "status": "error"}), 400

    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({
            "error": "Missing 'text' field in request body",
            "status": "error",
            "example": {"text": "မြန်မာစကား"}
        }), 400

    text = body["text"]
    if not text or not text.strip():
        return jsonify({"error": "Empty text provided", "status": "error"}), 400

    syllables = syllable_tokenize(text)

    return jsonify({
        "text": text,
        "syllables": syllables,
        "count": len(syllables),
        "status": "success"
    })


@app.route("/api/word-tokenize", methods=["POST"])
def api_word_tokenize():
    """Segment Myanmar text into words."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json", "status": "error"}), 400

    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({
            "error": "Missing 'text' field in request body",
            "status": "error",
            "example": {"text": "ကျွန်တော် အလုပ်သွားမယ်"}
        }), 400

    text = body["text"]
    if not text or not text.strip():
        return jsonify({"error": "Empty text provided", "status": "error"}), 400

    words = word_tokenize(text)

    return jsonify({
        "text": text,
        "words": words,
        "count": len(words),
        "status": "success"
    })


@app.route("/api/spell-check", methods=["POST"])
def api_spell_check():
    """Check Myanmar text for spelling errors."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json", "status": "error"}), 400

    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({
            "error": "Missing 'text' field in request body",
            "status": "error",
            "example": {"text": "မစားပဲ မသွားပဲ"}
        }), 400

    text = body["text"]
    if not text or not text.strip():
        return jsonify({"error": "Empty text provided", "status": "error"}), 400

    result = spell_check(text)

    return jsonify({
        "checked_text": result["checked_text"],
        "errors": result["errors"],
        "corrections": result["corrections"],
        "error_count": result["error_count"],
        "is_correct": result["error_count"] == 0,
        "status": "success"
    })


@app.route("/api/nlp-info", methods=["GET"])
def api_nlp_info():
    """Return information about available NLP tools."""
    return jsonify({
        "status": "success",
        "tools": get_module_info()
    })


# ============================================================
# Main
# ============================================================

# Register OneDrive Storage API
register_storage_routes(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"Myanmar AI Backend v1.0.0 starting on port {port}...")
    load_curriculum()
    print(f"Curriculum data loaded: {CURRICULUM_DATA is not None}")
    print(f"Grammar rules active: {len(RULES)}")
    app.run(host="0.0.0.0", port=port, debug=debug)
