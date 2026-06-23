import os
from google import genai
from google.genai import types

def ask_ai_root_cause(user_query, alerts):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return "I cannot answer this right now because the GEMINI_API_KEY environment variable is not set on the server."

    try:
        client = genai.Client(api_key=api_key)
        
        # Format context
        context = "Here are the current Active Security Alerts on our network:\n"
        for alert in alerts:
            context += f"- {alert.message} (Created at {alert.created_at})\n"
            
        prompt = f"""
You are a cybersecurity expert analyzing network logs.
Context:
{context}

User Question: {user_query}

Provide a concise, professional Root Cause Analysis. Keep it under 4 sentences. If there are no alerts, tell the user the network is healthy.
"""
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
        
    except Exception as e:
        print(f"AI Error Trace: {e}")
        return f"AI Error: {str(e)}"
