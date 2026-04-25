#!/usr/bin/env python3
"""Daily team motivation messages — 10 AM and 5 PM WhatsApp sends.
Sneha generates fresh, researched messages each time using live market data
and Primeidea knowledge. No fixed pool.
"""
import sys
import subprocess
from datetime import datetime

TEAM = [
    "+918141027000",  # Partha Shah
    "+918460927000",  # Mitesh Desai
    "+917016608140",  # Archana (Office)
    "+916351957027",  # Ruturaj
    "+919328709565",  # Archana (Personal)
]


def ollama_search(query: str) -> str:
    """Use ollama_web_search for live research."""
    r = subprocess.run(
        ["python3", "-c",
         f"import subprocess; r=subprocess.run(['ollama','web-search','--query','{query}'], capture_output=True, text=True, timeout=30); print(r.stdout[:3000])"],
        capture_output=True, text=True, timeout=35
    )
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def generate_message(hour: int) -> str:
    """Generate one fresh, researched sales motivation message in Sneha's voice."""
    is_10am = hour < 12
    time_label = "morning" if is_10am else "evening"

    queries_morning = [
        "PMS mutual fund sales tips India 2026 client engagement",
        "wealth management client acquisition strategies India 2026",
    ]
    queries_evening = [
        "PMS sales referral strategies high net worth India 2026",
        "financial product cross selling techniques India",
    ]

    queries = queries_morning if is_10am else queries_evening

    research_results = []
    for q in queries[:1]:
        result = ollama_search(q)
        if result:
            research_results.append(result[:600])

    research_context = "\n\n".join(research_results) if research_results else ""

    prompt = f"""You are Sneha, working with Partha at Primeidea. Generate ONE fresh, motivating WhatsApp message for the Primeidea sales team.

CONTEXT:
- Time: {time_label} ({datetime.now().strftime('%d %b %Y %H:%M IST')})
- Product focus: PMS (Portfolio Management Services) — Primeidea's wealth management offerings
- Team members: Mitesh, Archana (2), Ruturaj, Partha — they sell PMS products
- Goal: Motivate them to speak to clients, generate educational meetings, ask for referrals

TONE: Sneha's voice — warm, direct, professional, no fluff. Short and punchy. Not corporate-sounding.

MESSAGE REQUIREMENTS:
- 2-4 sentences max
- Include a specific, actionable idea for today (not vague motivation)
- Tie the idea to current market reality or PMS product benefit
- Push sales without mentioning incentives
- End with energy — something like "Let's go!" or "You've got this!" or "See you at the top!"
- NO hashtags, NO emojis in every line, NO generic phrases like "teamwork makes the dream work"
- Write like a real person who cares about results

OPTIONAL RESEARCH CONTEXT (use if helpful):
{research_context if research_context else 'No additional research available — rely on your knowledge of PMS sales.'}

OUTPUT: Only the WhatsApp message text. Nothing else."""

    r = subprocess.run(
        ["ollama", "run", "gpt-5.4", prompt],
        capture_output=True, text=True, timeout=60
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    if is_10am:
        return f"Good {time_label}, team! Every client conversation today is a chance to add real value. Pick one client, share a specific PMS insight that relates to their situation, and ask for a referral. One focused call can open a whole new conversation. Let's go! — Sneha, Primeidea"
    else:
        return f"Before you wrap up for the day — did you ask every client for a referral today? Even one conversation can lead to your next great connection. Send one more message tonight and keep the momentum going. You've got this! — Sneha, Primeidea"


def send_via_openclaw(phone: str, message: str) -> bool:
    r = subprocess.run(
        ["openclaw", "message", "send",
         "--channel", "whatsapp",
         "--target", phone,
         "--message", message],
        capture_output=True, text=True, timeout=30
    )
    return r.returncode == 0


def main():
    hour = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now().hour
    msg = generate_message(hour)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Generated message: {msg[:80]}...")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Sending to {len(TEAM)} team members...")
    for phone in TEAM:
        ok = send_via_openclaw(phone, msg)
        print(f"  {'OK' if ok else 'FAIL'} {phone}")


if __name__ == "__main__":
    main()