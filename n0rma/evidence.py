"""Tamper-evident evidence report (same layout and hash chain as the Android app, so either side can verify the other's file).

Every log line carries a hash that also covers the previous line, and the summary above the log is covered by the starting hash:
editing, deleting or reordering anything after export is detectable. It cannot prove who made the report: send the CHAIN END value to
someone you trust right away to fix the time and content."""
import hashlib
import re
import time

VERSION = "homewatch-evidence-v1"   # kept as-is so reports stay compatible with the Android verifier


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _fmt(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(ts))


def build(events, now_ms=None):
    """events: dicts with ts (seconds), domain, level, msg. Only watch/alert events are listed."""
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    flagged = sorted((e for e in events if e["level"] in ("watch", "alert")), key=lambda e: e["ts"])
    out = ["N0RMA EVIDENCE REPORT", f"Generated: {_fmt(now_ms / 1000)}", "", "SUMMARY (plain language)",
           "- This report lists what this computer's Bluetooth, Wi-Fi and network checks saw: nearby trackers, drone broadcasts and new or unknown devices.",
           f"- {len(flagged)} watch/alert events are listed below, from {_fmt(flagged[0]['ts']) if flagged else 'n/a'} to {_fmt(flagged[-1]['ts']) if flagged else 'n/a'}.",
           "- Limits: this is signal evidence, not proof of who placed a device. A computer stays in one place, so this report cannot show a tracker following you. "
           "Cellular/GPS trackers cannot be heard. Remote ID drone broadcasts can be faked.", ""]
    body = "\n".join(out) + "\n"
    h = start = _sha(f"{VERSION}|{now_ms}|{_sha(body)}")
    out.append("EVENT LOG  (line number | time | level | area | detail | chained hash)")
    for i, e in enumerate(flagged, 1):
        line = "%04d | %s | %s | %s | %s" % (i, _fmt(e["ts"]), e["level"], e["domain"], " ".join(str(e["msg"]).split("\n")))
        h = _sha(f"{h}|{line}")
        out.append(f"{line} | {h[:12]}")
    out += ["", f"CHAIN START: {start[:12]}  (generated-at {now_ms} ms)", f"CHAIN END (final hash): {h}",
            "To keep this tamper-evident, email or text the CHAIN END value to yourself or an advocate right now: it fixes the time and content."]
    return "\n".join(out) + "\n"


def verify(report):
    lines = report.split("\n")
    gen = next((l for l in lines if l.startswith("CHAIN START:")), None)
    end = next((l[len("CHAIN END (final hash): "):].strip() for l in lines if l.startswith("CHAIN END (final hash): ")), None)
    start = next((i for i, l in enumerate(lines) if l.startswith("EVENT LOG")), -1)
    if not gen or end is None or start < 0:
        return False
    m = re.search(r"generated-at (\d+) ms", gen)
    if not m:
        return False
    h = _sha(f"{VERSION}|{m.group(1)}|{_sha(chr(10).join(lines[:start]) + chr(10))}")
    if gen[len("CHAIN START:"):].strip()[:12] != h[:12]:
        return False
    for l in lines[start + 1:]:
        if not l.strip():
            break
        cut = l.rfind(" | ")
        if cut < 0:
            return False
        h = _sha(f"{h}|{l[:cut]}")
        if l[cut + 3:].strip() != h[:12]:
            return False
    return h == end
