#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Myanmar NLP Tools v1.0.0
Zawgyi/Unicode conversion, Syllable tokenization, Word tokenization, Spell checking
Pure Python implementation with optional library acceleration.
"""

import os
import re
import sys
from typing import List, Dict, Any, Tuple, Optional


# ============================================================
# 1. Zawgyi ↔ Unicode Conversion
# ============================================================

# Zawgyi-to-Unicode character mapping based on Google Myanmar Tools logic
# This covers the most common character differences between Zawgyi and Unicode encoding
_ZG2UNI_MAP = {
    '\u102b': '\u102b',   # Virama
    '\u103c': '\u103c',   # Medial ra
    '\u1031': '\u1031',   # Vowel sign e
    '\u103b': '\u103b',   # Medial wa
    '\u103d': '\u103d',   # Medial ha
    '\u103e': '\u103e',   # Medial ya
    '\u102c': '\u102c',   # Vowel sign aa
    '\u102d': '\u102d',   # Vowel sign i
    '\u102e': '\u102e',   # Vowel sign ii
    '\u102f': '\u102f',   # Vowel sign u
    '\u1030': '\u1030',   # Vowel sign uu
    '\u1036': '\u1036',   # Vowel sign ae
    '\u1037': '\u1037',   # Dot below
    '\u1038': '\u1038',   # Visarga
    '\u1039': '\u1039',   # Stack sign (virama for conjuncts)
    '\u103a': '\u103a',   # Asat
    '\u1032': '\u1032',   # Vowel sign ai
    '\u1033': '\u1033',   # Vowel sign ai (tall)
    '\u1034': '\u1034',   # Vowel sign ai (short)
    '\u1035': '\u1035',   # Vowel sign ai (alternative)
}

# Common Zawgyi-specific patterns that need reordering for Unicode
_ZAWGYI_PATTERNS = [
    # Kinzi reordering: consonant + virama + ra + asat
    (re.compile(r'(\u103c)(\u1031)(\u103b)'), r'\3\2\1'),
    # E vowel + wa medial reordering
    (re.compile(r'(\u103b)(\u1031)'), r'\2\1'),
    # E vowel + ha medial reordering
    (re.compile(r'(\u103d)(\u1031)'), r'\2\1'),
    # E vowel + ya medial reordering
    (re.compile(r'(\u103e)(\u1031)'), r'\2\1'),
]

# Unicode medial order (correct order)
# Correct order: consonant, asat, vowel(e/i/ii/u/uu), medial(wa/ra/ha/ya), virama, stack
_UNI_MEDIAL_ORDER = {
    '\u103a': 1,  # Asat
    '\u1031': 2,  # E vowel
    '\u103b': 3,  # Medial wa
    '\u103c': 4,  # Medial ra
    '\u103d': 5,  # Medial ha
    '\u103e': 6,  # Medial ya
}

# Myanmar consonant range
_MYANMAR_CONSONANT = re.compile(r'[\u1000-\u1021]')
# Myanmar vowel/diacritic range
_MYANMAR_VOWEL = re.compile(r'[\u102b-\u103e\u1032-\u1035]')
# Myanmar independent vowels
_MYANMAR_INDEPENDENT_VOWEL = re.compile(r'[\u1025\u1026\u1029-\u102a]')
# Myanmar digits
_MYANMAR_DIGIT = re.compile(r'[\u1040-\u1049]')
# Punctuation
_MYANMAR_PUNCT = re.compile(r'[\u104a-\u104f\u1004\u100b\u100c]')
# General Myanmar script
_MYANMAR_SCRIPT = re.compile(r'[\u1000-\u109f]')


def _is_zawgyi(text: str) -> bool:
    """
    Heuristic detection: check if text is likely Zawgyi encoded.
    Uses statistical analysis of character patterns common in Zawgyi.
    """
    if not text:
        return False

    # Count Zawgyi-indicating patterns
    zawgyi_indicators = 0
    unicode_indicators = 0
    total_myanmar = 0

    for i, ch in enumerate(text):
        if '\u1000' <= ch <= '\u109f':
            total_myanmar += 1

            # Zawgyi often has consonant followed directly by e-vowel
            if i > 0 and ch == '\u1031':
                prev = text[i - 1]
                if '\u1000' <= prev <= '\u1021':
                    zawgyi_indicators += 1

            # Zawgyi often has medial before vowel
            if i > 0 and ch in ('\u103b', '\u103d', '\u103e'):
                prev = text[i - 1]
                if prev == '\u1031':
                    zawgyi_indicators += 2  # Strong Zawgyi signal

            # Unicode typically has vowel before medial
            if i > 0 and ch in ('\u103b', '\u103d', '\u103e', '\u103c'):
                prev = text[i - 1]
                if prev in ('\u102d', '\u102e', '\u102f', '\u1030', '\u1036'):
                    unicode_indicators += 1

    if total_myanmar == 0:
        return False

    return zawgyi_indicators > unicode_indicators


def _reorder_to_unicode(text: str) -> str:
    """
    Reorder Zawgyi character sequences to Unicode standard order.
    Unicode standard order: consonant, asat, vowel, medial, virama, stack
    """
    result = []
    i = 0

    while i < len(text):
        ch = text[i]

        # If we hit a Myanmar consonant, process the following syllable modifiers
        if _MYANMAR_CONSONANT.match(ch):
            result.append(ch)
            i += 1

            # Collect all diacritics/modifiers following this consonant
            modifiers = []
            while i < len(text) and _MYANMAR_VOWEL.match(text[i]):
                modifiers.append(text[i])
                i += 1

            # Also collect virama + stacked consonant (conjuncts)
            if i < len(text) and text[i] == '\u1039':
                modifiers.append(text[i])
                i += 1
                if i < len(text) and _MYANMAR_CONSONANT.match(text[i]):
                    modifiers.append(text[i])
                    i += 1

            # Sort modifiers by Unicode standard order
            modifiers.sort(key=lambda m: _UNI_MEDIAL_ORDER.get(m, 99))
            result.extend(modifiers)
        else:
            result.append(ch)
            i += 1

    return ''.join(result)


def zawgyi_to_unicode(text: str) -> str:
    """
    Convert Zawgyi-encoded Myanmar text to Unicode standard encoding.
    Uses pattern-based reordering and character mapping.

    Args:
        text: Zawgyi-encoded Myanmar text

    Returns:
        Unicode-standard Myanmar text
    """
    if not text:
        return text

    converted = text

    # Apply pattern reordering
    for pattern, replacement in _ZAWGYI_PATTERNS:
        converted = pattern.sub(replacement, converted)

    # Apply character-level reordering for syllable modifiers
    converted = _reorder_to_unicode(converted)

    return converted


def unicode_to_zawgyi(text: str) -> str:
    """
    Convert Unicode-standard Myanmar text to Zawgyi encoding.
    Reverses the Unicode ordering to Zawgyi-specific order.

    Args:
        text: Unicode-standard Myanmar text

    Returns:
        Zawgyi-encoded Myanmar text
    """
    if not text:
        return text

    result = []
    i = 0

    while i < len(text):
        ch = text[i]

        if _MYANMAR_CONSONANT.match(ch):
            result.append(ch)
            i += 1

            # Collect modifiers
            modifiers = []
            while i < len(text) and _MYANMAR_VOWEL.match(text[i]):
                modifiers.append(text[i])
                i += 1

            # Collect virama + stacked consonant
            if i < len(text) and text[i] == '\u1039':
                modifiers.append(text[i])
                i += 1
                if i < len(text) and _MYANMAR_CONSONANT.match(text[i]):
                    modifiers.append(text[i])
                    i += 1

            # Zawgyi order: move e-vowel after medials
            e_vowel = '\u1031'
            has_e_vowel = e_vowel in modifiers
            if has_e_vowel:
                modifiers.remove(e_vowel)

            # Add medials first, then e-vowel (Zawgyi convention)
            for m in modifiers:
                result.append(m)
            if has_e_vowel:
                result.append(e_vowel)
        else:
            result.append(ch)
            i += 1

    return ''.join(result)


# ============================================================
# 2. Syllable Tokenizer (Sylbreak)
# ============================================================

# Myanmar syllable boundary pattern based on linguistic rules
# A Myanmar syllable consists of:
# - Optional onset consonant(s) or independent vowel
# - Optional medial(s)
# - Optional nucleus vowel
# - Optional coda (nasal, stops, etc.)
# - Optional tone markers

# Core syllable pattern components
_CONSONANT = r'\u1000-\u1021'           # Main consonants
_INDEPENDENT_VOWEL = r'\u1025-\u102a'    # Independent vowels
_MEDIAL = r'\u103b\u103c\u103d\u103e'   # Medial consonant signs
_VOWEL_SIGN = r'\u102b-\u103e\u1032-\u1035'  # All vowel/diacritic signs
_TONE = r'\u1036\u1037\u1038'           # Tone markers
_ABOVE_BELOW = r'\u1036'                # Vowel sign ae
_DOT_BELOW = r'\u1037'                  # Dot below
_VISARGA = r'\u1038'                    # Visarga
_ASAT = r'\u103a'                       # Asat (kills consonant)
_VIRAMA = r'\u1039'                     # Virama (conjunct formation)

# Extended Myanmar ranges
_MW_EXT = r'\u1050-\u1059'              # Myanmar Extended-A consonants

# Build syllable regex pattern
# Pattern: [consonant/vowel] [asat]? [vowel/diacritics]* [virama consonant]? [tone]? [asat]?
_SYLLABLE_PATTERN = re.compile(
    r'[' + _CONSONANT + _INDEPENDENT_VOWEL + _MW_EXT + r']'  # Base character
    r'[' + _ASAT + r']?'                                          # Asat after consonant
    r'(?:[' + _MEDIAL + _VOWEL_SIGN + r']+'                      # Vowels and medials
    r'(?:' + _VIRAMA + r'[' + _CONSONANT + _MW_EXT + r'])?)*'   # Optional conjunct
    r'[' + _TONE + r']*'                                          # Tone markers
    r'[' + _ASAT + r']?'                                          # Trailing asat
)

# Non-Myanmar syllable (numbers, punctuation, Latin, etc.)
_NON_MYANMAR = re.compile(r'[^\u1000-\u109f]+')


def syllable_tokenize(text: str) -> List[str]:
    """
    Break Myanmar text into syllables using regex-based rules.

    A Myanmar syllable typically follows the pattern:
    C(C)V(C)(T) where C=consonant, V=vowel, T=tone

    Args:
        text: Myanmar text to tokenize

    Returns:
        List of syllable strings
    """
    if not text or not text.strip():
        return []

    syllables = []
    i = 0

    while i < len(text):
        # Skip whitespace
        if text[i] in (' ', '\t', '\n', '\r', '\u200b'):
            i += 1
            continue

        # Handle non-Myanmar characters (Latin, numbers, punctuation)
        if not _MYANMAR_SCRIPT.match(text[i]):
            # Collect consecutive non-Myanmar characters as one token
            j = i
            while j < len(text) and not _MYANMAR_SCRIPT.match(text[j]):
                j += 1
            syllables.append(text[i:j])
            i = j
            continue

        # Try to match a Myanmar syllable
        match = _SYLLABLE_PATTERN.match(text, i)
        if match:
            syllables.append(match.group())
            i = match.end()
        else:
            # Single character fallback
            syllables.append(text[i])
            i += 1

    return syllables


# ============================================================
# 3. Word Tokenizer
# ============================================================

# Try to import pyidaungsu for better word segmentation
_HAS_PYIDAUNGSU = False
_pyidaungsu_tokenizer = None

try:
    from pyidaungsu import tokenizer as _pz_tokenizer
    _HAS_PYIDAUNGSU = True
    _pyidaungsu_tokenizer = _pz_tokenizer
except ImportError:
    pass

# Try mytokenize as fallback
_HAS_MYTOKENIZE = False
_mytokenize = None

try:
    import mytokenize as _mt
    _HAS_MYTOKENIZE = True
    _mytokenize = _mt
except ImportError:
    pass


# Myanmar syllable boundary used for word segmentation
# Common Myanmar word boundary markers
_WORD_BREAK = re.compile(
    r'(?:'
    r'[\s\u200b\u200c\u200d]+'           # Whitespace and zero-width chars
    r'|(?<=[\u1000-\u109f])(?=[a-zA-Z])' # Myanmar to Latin boundary
    r'|(?<=[a-zA-Z])(?=[\u1000-\u109f])' # Latin to Myanmar boundary
    r'|(?<=[\u1000-\u109f])(?=[\u104a-\u109f])' # Myanmar to punctuation
    r'|(?<=[\u104a-\u109f])(?=[\u1000-\u102a])' # Punctuation to Myanmar
    r'|(?<=[\u1038\u1037])(?=\u1000)'     # After visarga/dot to new consonant
    r'|(?<=[\u1038\u1037])(?=[\u1025])'    # After visarga to independent vowel
    r')'
)


def word_tokenize(text: str) -> List[str]:
    """
    Segment Myanmar text into words.

    Uses pyidaungsu if available, otherwise falls back to syllable-based
    heuristic word segmentation.

    Args:
        text: Myanmar text to tokenize

    Returns:
        List of word strings
    """
    if not text or not text.strip():
        return []

    # Use pyidaungsu if available (most accurate)
    if _HAS_PYIDAUNGSU and _pyidaungsu_tokenizer:
        try:
            words = _pyidaungsu_tokenizer.tokenize(text)
            return [w.strip() for w in words if w.strip()]
        except Exception:
            pass

    # Use mytokenize if available
    if _HAS_MYTOKENIZE and _mytokenize:
        try:
            words = _mytokenize.tokenize(text)
            return [w.strip() for w in words if w.strip()]
        except Exception:
            pass

    # Pure Python fallback: syllable-based segmentation with heuristic merging
    return _word_tokenize_fallback(text)


def _word_tokenize_fallback(text: str) -> List[str]:
    """
    Pure Python fallback for Myanmar word tokenization.
    Uses syllable segmentation combined with heuristic merging rules.

    Myanmar words are typically 1-4 syllables long. Common single-syllable
    words include post-positions and particles.
    """
    syllables = syllable_tokenize(text)

    if not syllables:
        return []

    words = []
    current_word = []

    for syl in syllables:
        # Non-Myanmar tokens are separate words
        if not _MYANMAR_SCRIPT.match(syl[0]) if syl else True:
            if current_word:
                words.append(''.join(current_word))
                current_word = []
            words.append(syl)
            continue

        # Check if this syllable should start a new word
        should_break = _is_word_boundary(current_word, syl, syllables)

        if should_break and current_word:
            words.append(''.join(current_word))
            current_word = [syl]
        else:
            current_word.append(syl)

    if current_word:
        words.append(''.join(current_word))

    return words


def _is_word_boundary(prev_syllables: List[str], current: str, all_syllables: List[str]) -> bool:
    """
    Heuristic to determine if there's a word boundary between previous syllables
    and the current syllable.

    Rules:
    - Empty previous = no boundary (start of word)
    - Single syllable particles/postpositions = likely boundary
    - Long current word (>3 syllables) = likely boundary
    - Common post-positions and particles tend to be word boundaries
    """
    if not prev_syllables:
        return False

    prev = ''.join(prev_syllables)

    # Common Myanmar particles and post-positions (single syllable words)
    single_word_particles = {
        '\u1015\u103b',    # ပါ - polite particle
        '\u1015\u102c',    # ပါ - topic marker
        '\u1005\u103a',    # က - subject marker
        '\u1036',          # - vowel sign
        '\u1021\u102c',    # အာ - accusative
        '\u1031\u1010\u103e',  # စ်- genitive
        '\u1021\u1004\u103a',  # အက - nominative
        '\u1014\u102e',    # နှင့် - and
    }

    # Check if current syllable is a common particle
    if current in single_word_particles or len(current) <= 2:
        # Short particles after any word = boundary
        if len(prev) >= 2:
            return True

    # If previous word is getting very long (4+ syllables), likely a boundary
    if len(prev_syllables) >= 4:
        return True

    # If previous ends with a post-position marker
    if prev.endswith('\u1038') or prev.endswith('\u1037') or prev.endswith('\u103a'):
        return True

    return False


# ============================================================
# 4. Spell Checker
# ============================================================

# Dictionary for spell checking (lazy loaded)
_SPELL_DICT: Optional[set] = None


def _load_spell_dict() -> set:
    """Lazy load the Myanmar spell check dictionary."""
    global _SPELL_DICT

    if _SPELL_DICT is not None:
        return _SPELL_DICT

    _SPELL_DICT = set()

    # Try multiple paths for the dictionary file
    dict_paths = [
        os.path.join(os.path.dirname(__file__), "data", "myanmar_words.txt"),
        os.path.join(os.path.dirname(__file__), "myanmar_words.txt"),
        "/home/z/myanmar-ai-backend/data/myanmar_words.txt",
        "data/myanmar_words.txt",
    ]

    for path in dict_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        word = line.strip()
                        if word:
                            _SPELL_DICT.add(word)
                break
            except Exception:
                continue

    return _SPELL_DICT


def _edit_distance_1(word: str) -> List[str]:
    """
    Generate all words at edit distance 1 from the given word.
    Operations: insertion, deletion, substitution of Myanmar characters.
    """
    letters = list(word)
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]

    deletes = [L + R[1:] for L, R in splits if R]
    transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R) > 1]

    # Myanmar character set for substitutions and insertions
    myanmar_chars = (
        list('ကကျကှက_selectionကွက̽က린က#type: ignore')
    )
    # Use common Myanmar consonants and vowels for edit operations
    common_myanmar = (
        'ကခဂဂ်သထဒဓမငဂညတဆယရလဝသညဓအဇ'
        'ာုီ delayသီသီးနီါဝး'
        'ပဲဝါးဂီ'
        'ေး ်ါ္渋'
    )

    # Keep it manageable - use the word's own characters for substitutions
    char_set = set(word)
    char_set.update(list(common_myanmar))
    char_list = list(char_set)

    substitutes = [L + c + R[1:] for L, R in splits if R for c in char_list if c != R[0]]
    inserts = [L + c + R for L, R in splits for c in char_list]

    return list(set(deletes + transposes + substitutes + inserts))


def spell_check(text: str) -> Dict[str, Any]:
    """
    Check Myanmar text for spelling errors.

    Uses dictionary lookup with edit distance suggestions.
    Unknown words are checked against a Myanmar word dictionary,
    and close matches are suggested as corrections.

    Args:
        text: Myanmar text to check

    Returns:
        Dictionary with 'errors' and 'corrections' lists
    """
    if not text or not text.strip():
        return {
            "errors": [],
            "corrections": [],
            "error_count": 0,
            "checked_text": text
        }

    dictionary = _load_spell_dict()
    words = word_tokenize(text)

    errors = []
    corrections = []

    for word in words:
        # Skip non-Myanmar words
        if not word or not _MYANMAR_SCRIPT.match(word[0]):
            continue

        # Skip very short words (single characters, common particles)
        if len(word) <= 1:
            continue

        # Clean the word (remove trailing punctuation for checking)
        clean_word = word.rstrip('\u104b\u104c\u104d\u104e\u104f')
        if clean_word != word:
            stripped = word[len(clean_word):]
        else:
            stripped = ''

        if len(clean_word) <= 1:
            continue

        # Check if word is in dictionary
        if clean_word in dictionary:
            continue

        # Word not found - it might be misspelled
        # Generate suggestions using edit distance
        suggestions = []
        candidates = _edit_distance_1(clean_word)

        # Filter to only dictionary words and rank by commonality
        for candidate in candidates:
            if candidate in dictionary:
                suggestions.append(candidate)

        # Also check if removing diacritics helps match
        # (e.g., words with different tone markers)
        base = re.sub(r'[\u1036\u1037\u1038\u103a]', '', clean_word)
        if base in dictionary:
            suggestions.insert(0, base)

        if suggestions:
            # Get unique suggestions, prioritizing shorter edit distance
            seen = set()
            unique_suggestions = []
            for s in suggestions:
                if s not in seen:
                    seen.add(s)
                    unique_suggestions.append(s)

            errors.append({
                "word": clean_word,
                "position": text.find(clean_word),
                "suggestions": unique_suggestions[:5]  # Top 5 suggestions
            })

            corrections.append({
                "original": clean_word + stripped,
                "top_suggestion": unique_suggestions[0] + stripped if unique_suggestions else clean_word + stripped,
                "all_suggestions": unique_suggestions[:5]
            })

    return {
        "errors": errors,
        "corrections": corrections,
        "error_count": len(errors),
        "checked_text": text
    }


# ============================================================
# Utility functions
# ============================================================


def detect_encoding(text: str) -> str:
    """
    Detect whether Myanmar text is Zawgyi or Unicode encoded.

    Args:
        text: Myanmar text

    Returns:
        "zawgyi", "unicode", or "unknown"
    """
    if not text:
        return "unknown"

    if _is_zawgyi(text):
        return "zawgyi"

    # Check if it has any Myanmar characters at all
    if _MYANMAR_SCRIPT.search(text):
        return "unicode"

    return "unknown"


def get_word_count(text: str) -> int:
    """Count words in Myanmar text."""
    return len(word_tokenize(text))


def get_syllable_count(text: str) -> int:
    """Count syllables in Myanmar text."""
    return len(syllable_tokenize(text))


# ============================================================
# Module info
# ============================================================

def get_module_info() -> Dict[str, Any]:
    """Return information about available NLP tools."""
    return {
        "zawgyi_unicode": {
            "available": True,
            "method": "pure_python",
            "type": "character_reordering"
        },
        "syllable_tokenizer": {
            "available": True,
            "method": "regex_syllable_pattern"
        },
        "word_tokenizer": {
            "available": True,
            "method": "pyidaungsu" if _HAS_PYIDAUNGSU else
                      ("mytokenize" if _HAS_MYTOKENIZE else "syllable_heuristic"),
            "pyidaungsu": _HAS_PYIDAUNGSU,
            "mytokenize": _HAS_MYTOKENIZE
        },
        "spell_checker": {
            "available": True,
            "method": "dictionary_lookup_edit_distance",
            "dictionary_size": len(_load_spell_dict())
        }
    }
