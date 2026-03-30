import datetime

def classify_email(text):
    text_lower = text.lower()

    if any(word in text_lower for word in ["thank", "received", "noted"]):
        return "LOW-RISK"
    if any(word in text_lower for word in ["invest", "portfolio", "returns", "advice"]):
        return "NEEDS APPROVAL"
    if any(word in text_lower for word in ["data", "report", "analysis"]):
        return "NEEDS RESEARCH"
    return "FYI"


def generate_reply(category, text):
    if category == "LOW-RISK":
        return "Noted. Thank you."
    elif category == "NEEDS APPROVAL":
        return "Thank you for your query. I will review this and get back to you shortly."
    elif category == "NEEDS RESEARCH":
        return "We are reviewing this and will share details soon."
    else:
        return ""


def process_email(text):
    category = classify_email(text)
    reply = generate_reply(category, text)

    return {
        "category": category,
        "reply": reply,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    }


if __name__ == "__main__":
    sample_email = input("Paste email text:\n")

    result = process_email(sample_email)

    print("\n--- RESULT ---")
    print("Category:", result["category"])
    print("Suggested Reply:", result["reply"])
    print("Processed at:", result["time"])
