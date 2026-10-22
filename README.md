# Mac Local Agent Harness

A lightweight, zero-cloud autonomous agent loop written in pure Python that executes tool-calling workflows locally on Apple Silicon using Ollama.

Designed as an alternative to heavy agent frameworks, this harness runs fully offline with zero external API dependencies, zero token costs, and no telemetry data leaving your machine.

---

## Architecture Overview

The harness orchestrates a local recursive execution loop between a small quantized model running on Apple Silicon unified memory and direct macOS system/hardware APIs:

```text
[ User Request in Terminal ]
            │
            ▼
┌───────────────────────────────┐
│     Local LLM via Ollama      │ <── Qwen 2.5 14B / 32B (Q4/Q6 GGUF)
│    (Function Call Planner)    │
└──────────────┬────────────────┘
               │ Emits JSON tool dispatch
               ▼
┌───────────────────────────────┐
│       agent_harness.py        │ <── Recursive loop (Max depth: 8)
│     (Execution Dispatcher)    │ <── Repetition penalties & deduplication guards
└──────────────┬────────────────┘
               │ Direct OS / Hardware Calls
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Local Tools Stack                        │
├──────────────────┬──────────────────┬───────────────────────────┤
│  Hardware / I/O  │ Filesystem / Git │        macOS Native       │
│  • ADB (Android) │  • read_file     │  • macOS Mail (AppleScript)
│  • pyserial/UART │  • write_file    │  • ripgrep / grep search  │
│  • Serial scans  │  • list_dir      │  • Self-executing Python  │
│                  │  • delete_file   │    with auto bug recovery │
└──────────────────┴──────────────────┴───────────────────────────┘

Features
Hardware & Port I/O:
Direct hardware queries to Android devices via ADB (battery diagnostics, properties, shell commands).
Native USB-UART enumeration and serial command polling via pyserial.
Self-Healing Code Execution:
Writes Python scripts directly to disk, executes them via subprocess, captures stdout/stderr, and autonomously reads tracebacks to patch errors until reaching Exit Code: 0.
Local Desktop & Email Integration:
Fast, index-bounded macOS Mail queries via osascript to summarize unread messages and search order confirmations without cloud IMAP credentials or mail server timeouts.
Local-Model Hardening:
Automated JSON unescape handlers (\n to newline conversion for code writes).
Tool-call signature deduplication to prevent repetitive queries.
Ollama repetition penalty configuration (repeat_penalty: 1.15, low temperature) to prevent token loop crashes.

Prerequisites
1. Apple Silicon Mac (16 GB unified RAM minimum; 32 GB or 48 GB recommended for   concurrent workloads).

2. Ollama:

brew install ollama
brew services start ollama

3. Target Model (Default daily driver):

ollama pull qwen2.5:14b-instruct-q6_K

4. Android Platform Tools & Ripgrep (Optional for ADB and fast search):
brew install android-platform-tools ripgrep

Installation

1. Clone the repository:

git clone [https://github.com/dan855n/mac-local-agent-harness.git](https://github.com/dan855n/mac-local-agent-harness.git)
cd mac-local-agent-harness

2. Install Python dependencies:

pip3 install -r requirements.txt

Usage

Start the interactive agent directly from your terminal:

python3 agent_harness.py

Tool Reference

Tool Name	Scope	Description
run_phone_shell	Hardware	Executes shell diagnostics on connected Android devices via ADB.
list_serial_ports	Hardware	Discovers active /dev/cu.* and virtual USB COM ports.
send_serial_command	Hardware	Transmits ASCII commands over USB serial and reads response buffers.
get_unread_emails	macOS	Queries macOS Mail.app for unread message subjects and senders.
search_emails	macOS	Filters Mail.app by sender, subject, or keyword snippets.
search_codebase	System	Scans local folders for regex or text patterns using ripgrep or grep.
list_dir	Storage	Inspects directory contents, subfolders, and file sizes.
read_local_file	Storage	Reads plaintext files with configurable line limits.
write_local_file	Storage	Writes text, markdown, or scripts to disk.
delete_file	Storage	Removes individual test files or logs safely.
run_python_code	Execution	Runs local Python scripts, capturing exit codes and tracebacks.

