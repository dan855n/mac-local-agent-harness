import subprocess
import os
import time
import json
import shutil
import ollama
import serial
import serial.tools.list_ports

# ==========================================
# 1. TOOL ACTIONS
# ==========================================

def run_phone_shell(command: str) -> str:
    """Execute shell commands on tethered Android phone via ADB."""
    try:
        res = subprocess.run(["adb", "-d", "shell", command], capture_output=True, text=True, timeout=10)
        return res.stdout.strip() if res.returncode == 0 else f"Error: {res.stderr.strip()}"
    except Exception as e:
        return f"ADB execution failed: {str(e)}"



def get_unread_emails(limit: int = 5) -> str:
    """Query macOS Mail.app safely for recent unread emails without crashing on large inboxes."""
    script = f"""
    tell application "Mail"
        set output to ""
        set foundCount to 0
        set checkLimit to 40
        repeat with i from 1 to checkLimit
            try
                set msg to message i of inbox
                if read status of msg is false then
                    set foundCount to foundCount + 1
                    set msgSender to sender of msg
                    set msgSubject to subject of msg
                    set output to output & foundCount & ". From: " & msgSender & " | Subject: " & msgSubject & "
"
                    if foundCount is {limit} then
                        exit repeat
                    end if
                end if
            on error
                exit repeat
            end try
        end repeat
        if foundCount is 0 then
            return "No unread messages found in the first " & checkLimit & " messages of inbox."
        end if
        return output
    end tell
    """
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
        return res.stdout.strip() if res.returncode == 0 else f"Mail notice: {res.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Mail query timed out."
    except Exception as e:
        return f"Mail check failed: {str(e)}"

def search_emails(query: str, search_type: str = "any", max_results: int = 5) -> str:
    """Search macOS Mail.app for specific emails matching a keyword in subject, sender, or content."""
    clean_q = query.replace('"', '\"').replace("'", "")
    
    script = f"""
    tell application "Mail"
        set output to ""
        set matchCount to 0
        set checkWindow to 100
        
        repeat with i from 1 to checkWindow
            try
                set msg to message i of inbox
                set isMatch to false
                
                if "{search_type}" is "sender" then
                    if (sender of msg) contains "{clean_q}" then set isMatch to true
                else if "{search_type}" is "subject" then
                    if (subject of msg) contains "{clean_q}" then set isMatch to true
                else
                    if (subject of msg) contains "{clean_q}" or (sender of msg) contains "{clean_q}" then set isMatch to true
                end if
                
                if isMatch then
                    set matchCount to matchCount + 1
                    set msgDate to (date received of msg as string)
                    set msgSender to sender of msg
                    set msgSubject to subject of msg
                    set msgBody to (content of msg)
                    if length of msgBody > 300 then
                        set msgBody to (text 1 thru 300 of msgBody) & "..."
                    end if
                    set output to output & "Match " & matchCount & ":\nFrom: " & msgSender & "\nSubject: " & msgSubject & "\nDate: " & msgDate & "\nSnippet: " & msgBody & "\n---\n"
                    if matchCount is {max_results} then
                        exit repeat
                    end if
                end if
            on error
                exit repeat
            end try
        end repeat
        
        if matchCount is 0 then
            return "No matching emails found for {clean_q} in the last " & checkWindow & " messages."
        end if
        return output
    end tell
    """
    try:
        import subprocess
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=25)
        return res.stdout.strip() if res.returncode == 0 else f"Mail query notice: {res.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Search timed out."
    except Exception as e:
        return f"Email search failed: {str(e)}"

def delete_file(path: str) -> str:
    """Delete a specified file from the local filesystem."""
    clean_path = path.replace("\\/", "/")
    expanded_path = os.path.expanduser(clean_path)
    if not os.path.exists(expanded_path):
        return f"Notice: File '{clean_path}' does not exist."
    if os.path.isdir(expanded_path):
        return f"Error: '{clean_path}' is a directory, not a file. Deletion refused for safety."
    try:
        os.remove(expanded_path)
        return f"Successfully deleted file: {clean_path}"
    except Exception as e:
        return f"Failed to delete '{clean_path}': {str(e)}"

def list_dir(path: str = ".") -> str:
    """List files and directories with sizes in a given path."""
    clean_path = path.replace("\\/", "/")
    expanded_path = os.path.expanduser(clean_path)
    if not os.path.exists(expanded_path):
        return f"Error: Path '{clean_path}' does not exist."
    try:
        entries = os.listdir(expanded_path)
        if not entries:
            return f"Directory '{clean_path}' is empty."
        output = []
        for e in sorted(entries):
            if e.startswith(".") and e not in (".gitignore", ".env"):
                continue
            full_p = os.path.join(expanded_path, e)
            is_dir = os.path.isdir(full_p)
            size = os.path.getsize(full_p) if not is_dir else 0
            size_str = f"{size:,} bytes" if not is_dir else "DIR"
            output.append(f"{e:30} [{size_str}]")
        return "\n".join(output[:50])
    except Exception as e:
        return f"List dir failed: {str(e)}"

def read_local_file(path: str, max_lines: int = 120) -> str:
    """Read plain text safely from a file on the Mac SSD."""
    clean_path = path.replace("\\/", "/")
    expanded_path = os.path.expanduser(clean_path)
    if not os.path.exists(expanded_path):
        return f"Error: File '{clean_path}' does not exist."
    try:
        with open(expanded_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(max_lines)]
            return "".join(lines)
    except Exception as e:
        return f"File read failed: {str(e)}"

def write_local_file(path: str, content: str) -> str:
    """Write text content to a local file on the Mac SSD."""
    clean_path = path.replace("\\/", "/")
    expanded_path = os.path.expanduser(clean_path)
    
    if "\\n" in content and "\n" not in content:
        content = content.encode("utf-8").decode("unicode_escape")
    
    try:
        os.makedirs(os.path.dirname(os.path.abspath(expanded_path)), exist_ok=True)
        with open(expanded_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to {clean_path}"
    except Exception as e:
        return f"File write failed: {str(e)}"

def run_python_code(script_path: str, timeout: int = 15) -> str:
    """Execute a local Python script on the Mac and capture stdout/stderr."""
    clean_path = script_path.replace("\\/", "/")
    expanded_path = os.path.expanduser(clean_path)
    if not os.path.exists(expanded_path):
        return f"Error: File '{clean_path}' not found."
    try:
        res = subprocess.run(
            ["python3", expanded_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        output = []
        if res.stdout:
            output.append(f"STDOUT:\n{res.stdout.strip()}")
        if res.stderr:
            output.append(f"STDERR:\n{res.stderr.strip()}")
        output.append(f"Exit Code: {res.returncode}")
        return "\n".join(output)
    except subprocess.TimeoutExpired:
        return f"Execution timed out after {timeout} seconds."
    except Exception as e:
        return f"Execution error: {str(e)}"

def list_serial_ports() -> str:
    """Scan and list all hardware and virtual serial/COM ports."""
    ports = serial.tools.list_ports.comports()
    if not ports:
        return "No serial ports detected."
    results = []
    for p in ports:
        device_node = p.device.replace("/dev/tty.", "/dev/cu.")
        results.append(f"Port: {device_node} | Description: {p.description} | HWID: {p.hwid}")
    return "\n".join(results)

def send_serial_command(port: str, command: str = "", baudrate: int = 115200, timeout: float = 2.0) -> str:
    """Send an ASCII command to a serial device and read the response buffer."""
    clean_port = port.replace("\\/", "/")
    if clean_port.startswith("/dev/tty."):
        clean_port = clean_port.replace("/dev/tty.", "/dev/cu.")
    try:
        with serial.Serial(port=clean_port, baudrate=baudrate, timeout=timeout) as ser:
            ser.reset_input_buffer()
            if command:
                ser.write((command + "\r\n").encode("utf-8"))
                time.sleep(0.3)
            raw = ser.read_all()
            return raw.decode("utf-8", errors="replace").strip() if raw else "Port opened; no response returned."
    except Exception as e:
        return f"Serial error: {str(e)}"

def search_codebase(pattern: str, path: str = ".", file_glob: str = "") -> str:
    """Recursively search for a regex pattern or string across files in a folder."""
    clean_path = path.replace("\\/", "/")
    expanded_path = os.path.expanduser(clean_path)
    if not os.path.exists(expanded_path):
        return f"Error: Path '{clean_path}' does not exist."

    has_rg = shutil.which("rg") is not None

    if has_rg:
        cmd = [
            "rg", "--line-number", "--no-heading", "--color", "never",
            "--max-count", "20",
            "-g", "!Library/**",
            "-g", "!node_modules/**",
            "-g", "!.git/**",
        ]
        if file_glob:
            cmd.extend(["-g", file_glob])
        cmd.extend([pattern, expanded_path])
    else:
        cmd = [
            "grep", "-rn",
            "--exclude-dir=.git",
            "--exclude-dir=Library",
            "--exclude-dir=node_modules",
            "--exclude-dir=venv",
            "--exclude-dir=__pycache__",
            pattern, expanded_path
        ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = res.stdout.strip()
        if not output:
            return f"No matches found for pattern '{pattern}' in '{clean_path}'."
        lines = output.splitlines()
        if len(lines) > 30:
            return "\n".join(lines[:30]) + f"\n... [{len(lines) - 30} additional matches truncated]"
        return output
    except subprocess.TimeoutExpired:
        return "Search timed out after 10 seconds."
    except Exception as e:
        return f"Search execution failed: {str(e)}"

# ==========================================
# 2. DISPATCH REGISTRY & SCHEMAS
# ==========================================

TOOL_DISPATCHER = {
    "run_phone_shell": run_phone_shell,
    "get_unread_emails": get_unread_emails,
    "search_emails": search_emails,
    "delete_file": delete_file,
    "list_dir": list_dir,
    "read_local_file": read_local_file,
    "write_local_file": write_local_file,
    "run_python_code": run_python_code,
    "list_serial_ports": list_serial_ports,
    "send_serial_command": send_serial_command,
    "search_codebase": search_codebase,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Permanently delete an individual file on the Mac (e.g. temporary logs or test scripts).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to delete (e.g. '~/Desktop/test.py')."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search for specific emails in macOS Mail.app by subject, sender name/address, or general keyword, returning sender, subject, date, and a snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search keyword, sender name, or subject phrase to find."
                    },
                    "search_type": {
                        "type": "string",
                        "enum": ["subject", "sender", "any"],
                        "description": "Target field to search in (default: any)."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matching emails to retrieve (default: 5)."
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_unread_emails",
            "description": "Fetch unread email subjects, senders, and dates directly from macOS Mail.app without credentials.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum number of recent unread messages to retrieve (default 5)."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files, subfolders, and sizes in a directory (supports ~ paths).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Folder path to list, default '.'."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_phone_shell",
            "description": "Execute diagnostic commands on connected Android phone via ADB (e.g. 'dumpsys battery', 'getprop ro.product.model').",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Shell command to run."}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_local_file",
            "description": "Read text content from a file on the local filesystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path."},
                    "max_lines": {"type": "integer", "description": "Lines to read (default 120)."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_local_file",
            "description": "Write text or source code directly to a local file on the Mac SSD.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination file path."},
                    "content": {"type": "string", "description": "Full file content to write."}
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python_code",
            "description": "Execute a Python script on the Mac and capture console stdout, stderr, and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_path": {"type": "string", "description": "Path to Python script."},
                    "timeout": {"type": "integer", "description": "Execution timeout in seconds (default 15)."}
                },
                "required": ["script_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_serial_ports",
            "description": "Enumerate all connected USB-to-serial and hardware ports.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_serial_command",
            "description": "Send a command string to a serial port and capture device output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {"type": "string", "description": "Device path, e.g. /dev/cu.usbserial*"},
                    "command": {"type": "string", "description": "Command string to transmit."},
                    "baudrate": {"type": "integer", "description": "Baud rate (default 115200)."},
                    "timeout": {"type": "number", "description": "Timeout in seconds."}
                },
                "required": ["port"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Search through text files and codebases for a text pattern or regex using ripgrep/grep.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text or regex pattern to search for."},
                    "path": {"type": "string", "description": "Directory or file to search in (default '.')."},
                    "file_glob": {"type": "string", "description": "File extension glob, e.g. '*.py'."}
                },
                "required": ["pattern"],
            },
        },
    }
]

# ==========================================
# 3. RECURSIVE ENGINE & SAFE GUARDS
# ==========================================

MODEL_NAME = "qwen2.5:14b-instruct-q6_K"

OLLAMA_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.15,
}

SYSTEM_PROMPT = """You are an authentic, adaptive local engineering assistant running offline on macOS.
Core behavior guidelines:
1. When searching emails, prefer simple brand/sender keywords (e.g. 'Amazon', 'Google') with search_type='any' rather than guessing exact subject phrases.
2. When writing summary files, always compose full, readable markdown content. Never pass empty content to write_local_file.
3. Always invoke tools directly for live data.
"""


def run_agent_turn(messages: list, max_depth: int = 8):
    """Executes agent loop with robust tool-calling detection and response handling."""
    for step in range(max_depth):
        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOL_SCHEMAS,
                options=OLLAMA_OPTIONS,
            )
        except ollama.ResponseError as e:
            print(f"\n[Ollama Notice]: {e.error}")
            return
        except Exception as e:
            print(f"\n[Inference Error]: {str(e)}")
            return

        msg = response.message
        tool_calls = getattr(msg, "tool_calls", None)

        # Case 1: Model returned tool calls
                
        if tool_calls:
            messages.append(msg)
            executed_calls = set()

            for call in tool_calls:
                fn_name = call.function.name
                fn_args = call.function.arguments
                call_sig = (fn_name, json.dumps(fn_args, sort_keys=True))

                # Skip identical calls within the same turn
                if call_sig in executed_calls:
                    continue
                executed_calls.add(call_sig)

                print(f"\n[Invoking]: {fn_name}({fn_args})")

                if fn_name in TOOL_DISPATCHER:
                    result = TOOL_DISPATCHER[fn_name](**fn_args)
                    preview = str(result)[:200]
                    print(f"[Result]: {preview}{'...' if len(str(result)) > 200 else ''}")
                    messages.append({
                        "role": "tool",
                        "content": str(result),
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "content": f"Error: Tool '{fn_name}' does not exist.",
                    })
            continue
        # Case 2: Model returned text content
        content = getattr(msg, "content", "").strip()
        if content:
            messages.append(msg)
            print(f"\nLocal Agent: {content}")
            return

        # Case 3: Empty response edge-case; force text generation
        if step > 0:
            final_check = ollama.chat(
                model=MODEL_NAME,
                messages=messages + [{"role": "user", "content": "Summarize the tool output."}],
                options=OLLAMA_OPTIONS
            )
            print(f"\nLocal Agent: {final_check.message.content.strip()}")
            messages.append(final_check.message)
            return

    print("\nLocal Agent: [Max tool iterations reached for this turn.]")

def main():
    print(f"\n=== Offline Engineering Agent [{MODEL_NAME}] ===")
    print("Registered Tools: " + ", ".join(TOOL_DISPATCHER.keys()))
    print("Commands: Type 'clear' to reset history, 'exit' to quit.\n")

    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nShutting down.")
            break

        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit"):
            break
        if prompt.lower() in ("clear", "reset"):
            history = [{"role": "system", "content": SYSTEM_PROMPT}]
            print("Conversation history cleared.")
            continue

        history.append({"role": "user", "content": prompt})
        run_agent_turn(history)

if __name__ == "__main__":
    main()
