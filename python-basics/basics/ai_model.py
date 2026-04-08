import os
import requests

API_KEY = os.getenv("OPENROUTER_API_KEY")
##MODEL = "mistralai/devstral-2512:free"
MODEL = "x-ai/grok-code-fast-1"
def call_model(prompt: str):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        },
    )
    return response.json()
if __name__ == "__main__":
    # Check if API key is set
    if not API_KEY:
        print("ERROR: OPENROUTER_API_KEY environment variable is not set!")
        print("Please run this command in your terminal first:")
        print("export OPENROUTER_API_KEY=your_api_key_here")
        print("You can get a new API key at: https://openrouter.ai/keys")
        exit(1)
    
    # INPUT: The prompt we send to the API
    # prompt = "Explain cloud-native systems in two sentences."
    prompt = "Provide a bullet-point summary of cloud-native systems."
    print("INPUT (sending to API):", prompt)
    print()
    
    result = call_model(prompt)
    
    # OUTPUT: The response from the API
    print("OUTPUT (response from API):")
    print(result)
    print()
    
    # Extract and print just the message content
    if "choices" in result:
        message_content = result["choices"][0]["message"]["content"]
        print("Message content:", message_content)
        print(f"Length of returned text: {len(message_content)} characters")
    else:
        print("Error: No 'choices' in response. Full response above.")
