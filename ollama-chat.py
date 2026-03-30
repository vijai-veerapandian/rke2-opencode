#!/usr/bin/env python3
"""
Ollama CLI Chat - A simple terminal chat client for Ollama API.
Supports streaming responses, conversation history, and file context.

Usage:
    python ollama-chat.py                           # Interactive chat
    python ollama-chat.py --url http://host:11434   # Custom Ollama URL
    python ollama-chat.py --model qwen2.5-coder:3b  # Specific model
    python ollama-chat.py --file main.py            # Add file context
"""

import argparse
import json
import sys
import os
import urllib.request
import urllib.error

# ANSI colors
class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def print_banner(model, url):
    print(f"""
{Colors.CYAN}{Colors.BOLD}╔══════════════════════════════════════════════╗
║          Ollama CLI Chat                     ║
╚══════════════════════════════════════════════╝{Colors.RESET}
{Colors.GRAY}Model  : {Colors.GREEN}{model}{Colors.RESET}
{Colors.GRAY}Server : {Colors.GREEN}{url}{Colors.RESET}
{Colors.GRAY}Commands: /quit /clear /model /files /help{Colors.RESET}
""")

def check_connection(base_url):
    """Check if Ollama server is reachable."""
    try:
        req = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            return True, models
    except Exception as e:
        return False, str(e)

def stream_chat(base_url, model, messages):
    """Send a chat request and stream the response token by token."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": True
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    full_response = ""
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            print(f"\n{Colors.GREEN}{Colors.BOLD}AI:{Colors.RESET} ", end="", flush=True)
            for line in resp:
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    if "message" in chunk and "content" in chunk["message"]:
                        token = chunk["message"]["content"]
                        print(token, end="", flush=True)
                        full_response += token
                    if chunk.get("done", False):
                        # Print stats
                        total_duration = chunk.get("total_duration", 0)
                        eval_count = chunk.get("eval_count", 0)
                        eval_duration = chunk.get("eval_duration", 1)
                        if total_duration > 0:
                            total_secs = total_duration / 1e9
                            tokens_per_sec = eval_count / (eval_duration / 1e9) if eval_duration > 0 else 0
                            print(f"\n{Colors.GRAY}[{total_secs:.1f}s | {eval_count} tokens | {tokens_per_sec:.1f} tok/s]{Colors.RESET}")
                        else:
                            print()
            print()
    except urllib.error.URLError as e:
        print(f"\n{Colors.RED}Error: {e}{Colors.RESET}\n")
        return None
    except Exception as e:
        print(f"\n{Colors.RED}Error: {e}{Colors.RESET}\n")
        return None

    return full_response

def read_file_context(filepaths):
    """Read files and format them as context."""
    context = ""
    for fp in filepaths:
        fp = fp.strip()
        if os.path.isfile(fp):
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                context += f"\n\n--- File: {fp} ---\n{content}\n--- End of {fp} ---\n"
                print(f"{Colors.GRAY}  Loaded: {fp} ({len(content)} chars){Colors.RESET}")
            except Exception as e:
                print(f"{Colors.RED}  Error reading {fp}: {e}{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}  File not found: {fp}{Colors.RESET}")
    return context

def show_help():
    print(f"""
{Colors.YELLOW}Available commands:{Colors.RESET}
  /quit, /exit, /q   - Exit the chat
  /clear, /c          - Clear conversation history
  /model <name>       - Switch model
  /models             - List available models
  /file <path>        - Add file(s) to next message context
  /files              - Show loaded file context
  /history            - Show conversation history
  /tokens             - Show token count estimate
  /help, /h           - Show this help
  
{Colors.YELLOW}Tips:{Colors.RESET}
  - Multi-line input: end a line with \\ to continue
  - Paste code directly into the prompt
  - Use /file to give the AI context about your code
""")

def get_multiline_input():
    """Get input that supports multi-line with backslash continuation."""
    lines = []
    try:
        line = input(f"{Colors.CYAN}{Colors.BOLD}You:{Colors.RESET} ")
        while line.endswith("\\"):
            lines.append(line[:-1])
            line = input(f"{Colors.GRAY}...:{Colors.RESET} ")
        lines.append(line)
    except EOFError:
        return "/quit"
    except KeyboardInterrupt:
        print()
        return "/quit"
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Ollama CLI Chat Client")
    parser.add_argument("--url", default="http://192.168.2.66:11434",
                        help="Ollama server URL (default: http://192.168.2.66:11434)")
    parser.add_argument("--model", default="qwen2.5-coder:1.5b-16k",
                        help="Model name (default: qwen2.5-coder:1.5b-16k)")
    parser.add_argument("--file", action="append", default=[],
                        help="File(s) to include as context (can use multiple times)")
    parser.add_argument("--system", default="You are a helpful AI coding assistant. Be concise and direct.",
                        help="System prompt")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    model = args.model

    # Check connection
    print(f"{Colors.GRAY}Connecting to {base_url}...{Colors.RESET}")
    connected, result = check_connection(base_url)
    if not connected:
        print(f"{Colors.RED}Cannot connect to Ollama: {result}{Colors.RESET}")
        print(f"{Colors.YELLOW}Make sure Ollama is running and accessible at {base_url}{Colors.RESET}")
        sys.exit(1)

    available_models = result
    if model not in available_models:
        print(f"{Colors.YELLOW}Warning: Model '{model}' not found. Available models:{Colors.RESET}")
        for m in available_models:
            print(f"  {Colors.GREEN}{m}{Colors.RESET}")
        if available_models:
            model = available_models[0]
            print(f"{Colors.YELLOW}Using: {model}{Colors.RESET}")
        else:
            print(f"{Colors.RED}No models available. Pull a model first.{Colors.RESET}")
            sys.exit(1)

    print_banner(model, base_url)

    # Initialize conversation
    messages = [{"role": "system", "content": args.system}]
    file_context = ""

    # Load initial file context
    if args.file:
        print(f"{Colors.GRAY}Loading file context:{Colors.RESET}")
        file_context = read_file_context(args.file)

    # Main chat loop
    while True:
        user_input = get_multiline_input()

        if not user_input.strip():
            continue

        # Handle commands
        cmd = user_input.strip().lower()

        if cmd in ("/quit", "/exit", "/q"):
            print(f"{Colors.GRAY}Goodbye!{Colors.RESET}")
            break

        elif cmd in ("/clear", "/c"):
            messages = [{"role": "system", "content": args.system}]
            file_context = ""
            print(f"{Colors.YELLOW}Conversation cleared.{Colors.RESET}\n")
            continue

        elif cmd in ("/help", "/h"):
            show_help()
            continue

        elif cmd == "/models":
            _, models = check_connection(base_url)
            if isinstance(models, list):
                print(f"\n{Colors.YELLOW}Available models:{Colors.RESET}")
                for m in models:
                    marker = " (active)" if m == model else ""
                    print(f"  {Colors.GREEN}{m}{Colors.GRAY}{marker}{Colors.RESET}")
            print()
            continue

        elif cmd.startswith("/model "):
            new_model = user_input.strip()[7:].strip()
            _, models = check_connection(base_url)
            if isinstance(models, list) and new_model in models:
                model = new_model
                print(f"{Colors.GREEN}Switched to: {model}{Colors.RESET}\n")
            else:
                print(f"{Colors.RED}Model '{new_model}' not found.{Colors.RESET}\n")
            continue

        elif cmd.startswith("/file "):
            paths = user_input.strip()[6:].strip().split()
            new_context = read_file_context(paths)
            if new_context:
                file_context += new_context
                print(f"{Colors.GREEN}File context updated.{Colors.RESET}\n")
            continue

        elif cmd == "/files":
            if file_context:
                lines = file_context.count("\n")
                chars = len(file_context)
                print(f"{Colors.GRAY}File context: ~{chars} chars, ~{lines} lines{Colors.RESET}\n")
            else:
                print(f"{Colors.GRAY}No file context loaded.{Colors.RESET}\n")
            continue

        elif cmd == "/history":
            print(f"\n{Colors.YELLOW}Conversation history ({len(messages)} messages):{Colors.RESET}")
            for msg in messages:
                role = msg["role"]
                content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
                color = Colors.CYAN if role == "user" else Colors.GREEN if role == "assistant" else Colors.GRAY
                print(f"  {color}{role}: {content}{Colors.RESET}")
            print()
            continue

        elif cmd == "/tokens":
            total_chars = sum(len(m["content"]) for m in messages) + len(file_context)
            est_tokens = total_chars // 4  # rough estimate
            print(f"{Colors.GRAY}Estimated tokens in context: ~{est_tokens}{Colors.RESET}\n")
            continue

        # Build message with file context if available
        if file_context:
            full_message = f"Context from files:\n{file_context}\n\nUser question: {user_input}"
        else:
            full_message = user_input

        messages.append({"role": "user", "content": full_message})

        # Stream response
        response = stream_chat(base_url, model, messages)

        if response:
            messages.append({"role": "assistant", "content": response})
        else:
            # Remove failed user message
            messages.pop()

if __name__ == "__main__":
    main()
