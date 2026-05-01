#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Myanmar AI Backend NLP Tools v2.0.0
Tests all 4 new NLP endpoints + existing grammar check.
"""

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:5000"


def test_endpoint(name, method, path, data=None, expected_keys=None):
    """Test a single API endpoint."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")

    url = BASE_URL + path
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET":
            req = urllib.request.Request(url, headers=headers)
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
                method=method
            )

        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            status = resp.status

        print(f"  Status: {status}")
        print(f"  Response:")
        print(f"  {json.dumps(result, ensure_ascii=False, indent=2)}")

        # Validate expected keys
        if expected_keys:
            missing = [k for k in expected_keys if k not in result]
            if missing:
                print(f"  WARNING: Missing keys: {missing}")
                return False
            else:
                print(f"  All expected keys present: {expected_keys}")
                return True
        return True

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"  HTTP Error {e.code}: {body}")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def main():
    """Run all NLP tool tests."""
    print("\n" + "=" * 60)
    print("  Myanmar AI Backend - NLP Tools Test Suite")
    print("  Version 2.0.0")
    print("=" * 60)

    # First check health
    ok = test_endpoint(
        "Health Check",
        "GET", "/api/health",
        expected_keys=["status", "grammar_rules", "nlp_tools"]
    )

    if not ok:
        print("\nServer is not running. Start it first:")
        print("  python curriculum_grammar_server.py")
        sys.exit(1)

    results = {}

    # Test 1: Home endpoint
    results["home"] = test_endpoint(
        "API Home",
        "GET", "/",
        expected_keys=["service", "version", "endpoints"]
    )

    # Test 2: Zawgyi to Unicode
    results["zawgyi"] = test_endpoint(
        "Zawgyi to Unicode",
        "POST", "/api/zawgyi-to-unicode",
        data={"text": "သီဟိုဠ်မှ ဉာဏ်ကြီးရှင်"},
        expected_keys=["original", "unicode", "detected_encoding", "status"]
    )

    # Test 3: Syllable Tokenizer
    results["syllable"] = test_endpoint(
        "Syllable Tokenizer",
        "POST", "/api/syllable-tokenize",
        data={"text": "မြန်မာစကား"},
        expected_keys=["text", "syllables", "count", "status"]
    )

    # Test 4: Word Tokenizer
    results["word"] = test_endpoint(
        "Word Tokenizer",
        "POST", "/api/word-tokenize",
        data={"text": "ကျွန်တော် အလုပ်သွားမယ်"},
        expected_keys=["text", "words", "count", "status"]
    )

    # Test 5: Spell Check
    results["spell"] = test_endpoint(
        "Spell Check",
        "POST", "/api/spell-check",
        data={"text": "မစားပဲ မသွားပဲ"},
        expected_keys=["checked_text", "errors", "corrections", "error_count", "status"]
    )

    # Test 6: Grammar Check (existing)
    results["grammar"] = test_endpoint(
        "Grammar Check",
        "POST", "/api/grammar-check",
        data={"text": "မစားပဲ မသွားပဲ"},
        expected_keys=["text", "errors", "error_count", "is_correct"]
    )

    # Test 7: NLP Info
    results["nlp_info"] = test_endpoint(
        "NLP Info",
        "GET", "/api/nlp-info",
        expected_keys=["status", "tools"]
    )

    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, status in results.items():
        icon = "PASS" if status else "FAIL"
        print(f"  [{icon}] {name}")

    print(f"\n  Results: {passed}/{total} tests passed")

    if passed == total:
        print("  All tests passed!")
    else:
        print(f"  {total - passed} test(s) failed.")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
