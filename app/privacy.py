import re

EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<!\w)\+?\d[\d ().-]{7,}\d(?!\w)")
URL = re.compile(r"https?://\S+|www\.\S+", re.I)
SENSITIVE = re.compile(
    r"\b(gender|religion|caste|ethnicity|nationality|marital|pregnan\w*|"
    r"disabilit\w*|date of birth|sexual orientation|race|age|"
    r"male|female|muslim|hindu|christian|gay|straight|"
    r"home address|contact details|email address|phone number)\b", re.I
)
ATTACK = re.compile(
    r"ignore (all |any |the )?(previous|prior|system|instructions)|"
    r"system prompt|developer message|you are now|"
    r"rank me first|rank this candidate first|"
    r"reveal.*(secret|api.key)|BEGIN SYSTEM|INJECTION_SUCCESS", re.I
)


def redact(text, aliases=None):
    for name, candidate_id in sorted(
        (aliases or {}).items(), key=lambda item: -len(item[0])
    ):
        text = re.sub(re.escape(name), candidate_id, text, flags=re.I)
    text = EMAIL.sub("[email removed]", text)
    text = PHONE.sub("[phone removed]", text)
    return URL.sub("[link removed]", text)


def safe_lines(text, aliases=None):
    return "\n".join(
        redact(line, aliases)
        for line in text.splitlines()
        if not SENSITIVE.search(line) and not ATTACK.search(line)
    ).strip()


def blocked_question(text):
    return bool(SENSITIVE.search(text) or ATTACK.search(text) or
                re.search(r"\b(hire|reject|offer)\b.*\b(automatically|final)\b", text, re.I))