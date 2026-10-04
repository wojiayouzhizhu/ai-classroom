import httpx
import os
import base64

JUDGE0_URL = os.getenv("JUDGE0_URL", "https://ce.judge0.com")

LANGUAGE_IDS = {
    "python": 71,
    "javascript": 63,
    "java": 62,
    "cpp": 54,
    "c": 50,
    "ruby": 72,
    "go": 60,
    "rust": 73,
    "typescript": 63,
    "c#": 51,
    }


async def execute_code(source_code: str, language: str = "python") -> str:
    language_id = LANGUAGE_IDS.get(language.lower())
    if not language_id:
        return f"Unsupported language: {language}. Supported: {', '.join(LANGUAGE_IDS.keys())}"

    encoded_code = base64.b64encode(source_code.encode()).decode()

    payload = {
        "source_code": encoded_code,
        "language_id": language_id,
        "base64_encoded": True,
    }

    rapid_api_key = os.getenv("JUDGE0_API_KEY")

    print(f"[JUDGE0] API key present: {bool(rapid_api_key)}, URL will be: {'RapidAPI' if rapid_api_key else 'demo'}")

    if rapid_api_key:
        url = "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=true&wait=true"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-RapidAPI-Key": rapid_api_key,
            "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com",
        }
    else:
        url = f"{JUDGE0_URL}/submissions?base64_encoded=true&wait=true"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

        print(f"[JUDGE0 API] submitted {language} code, status: {result.get('status', {}).get('description', 'unknown')}")
        print(f"Code string: {source_code}")
        stdout = base64.b64decode(result.get("stdout") or "").decode().strip()
        stderr = base64.b64decode(result.get("stderr") or "").decode().strip()
        compile_output = base64.b64decode(result.get("compile_output") or "").decode().strip()
        print(f"Decoded stdout: {stdout}")
        print(f"Decoded stderr: {stderr}")
        print(f"Decoded compile output: {compile_output}")
        if stdout:
            return f"Output:\n{stdout}"
        elif stderr:
            return f"Error:\n{stderr}"
        elif compile_output:
            return f"Compile error:\n{compile_output}"
        else:
            return "No output produced."

    except httpx.TimeoutException:
        return "Code execution timed out."
    except Exception as e:
        return f"Execution failed: {str(e)}"
    
def detect_language(code: str) -> str:
    if "def " in code or "print(" in code or "import " in code and "public" not in code:
        return "python"
    elif "public static" in code or "System.out" in code:
        return "java"
    elif "#include" in code or "cout" in code or "int main" in code:
        return "cpp"
    elif "console.log" in code or "const " in code or "let " in code:
        return "javascript"
    elif "fn " in code and "println!" in code:
        return "rust"
    elif "func " in code and "fmt." in code:
        return "go"
    return "python"  # default to python

def extract_code(message: str) -> str:
    # If code block exists, extract it
    if "```" in message:
        parts = message.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                lines = part.strip().split("\n")
                if lines and lines[0].lower() in LANGUAGE_IDS:
                    return "\n".join(lines[1:])
                return part.strip()

    # Find the first line that looks like code and take everything from there
    lines = message.strip().split("\n")
    code_start_indicators = ["def ", "class ", "import ", "public static", "int main", "#include", "function "]
    
    for i, line in enumerate(lines):
        if any(indicator in line for indicator in code_start_indicators):
            return "\n".join(lines[i:])
    
    return message

def contains_code(message: str) -> bool:
    # A simple heuristic to check if the message contains code-like patterns
    code_indicators = ["def ", "class ", "import ", "public ", "function ", "{", "}", ";", "```", "#include", "console.log", "System.out.println", "print("]
    return any(indicator in message for indicator in code_indicators)