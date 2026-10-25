# Mac Local Harness

A modular, local-first Mac assistant that can use **Ollama**, **LM Studio**, or another OpenAI-compatible chat endpoint. It includes a desktop-style local web GUI and a terminal interface. Inference goes to the configured model server. The tool set is built for practical Mac work, software projects, web research, local files, Mail.app, Android ADB, serial devices, CircuitPython/ESP32 boards, and FilmCraft video editing through its local MCP server.

## Install on macOS

1. Install Python 3.11 or newer.
2. Start Ollama or LM Studio's local API server.
3. Double-click `Setup.command`, or from Terminal run:

   ```sh
   git clone https://github.com/dan855n/mac-local-agent-harness.git
   cd mac-local-agent-harness
   ./Setup.command
   ```

4. Launch the GUI with `Run GUI.command`; use `Run.command` for the terminal interface. You can also run `.venv/bin/mac-harness-gui` or `.venv/bin/mac-harness` from the project directory.
5. Type `/provider` to choose a server and list available models, or edit the config file shown by `/settings`.

The first launch creates the app's config and conversation database. macOS may ask you to grant Terminal privacy access to folders (such as Documents/Downloads) or Automation access to Mail/other apps when you first use those tools. Approve only the access you want this harness to have.

The setup script installs this project into its own virtual environment. Ollama's common OpenAI-compatible address is `http://127.0.0.1:11434/v1`; LM Studio's default is `http://127.0.0.1:1234/v1`. Choose the actual model ID reported by `/models`. You can choose `custom_openai` for a different compatible endpoint. Its API key is read from the environment variable named in `api_key_env`; keys are never written to this project's config.

## GUI

`Run GUI.command` opens a private, loopback-only app in your browser. It provides a conversation sidebar, saved history, model selection, live tool activity, and a per-action approval dialog. Approvals apply to one action only. The app does not expose a network listener beyond `127.0.0.1`; a random session token protects state-changing requests. The GUI shares the CLI's conversation database, settings, tools, and audit log. Use Settings to choose Ollama or LM Studio and refresh the model list. A custom compatible endpoint can be remote, so check its URL before sending private prompts.

LM Studio has native Python tooling too, but the harness uses the shared OpenAI-compatible chat-completions interface so the same agent, tools, and saved conversations work with both servers. Tool calling still depends on the selected model and server build; `/doctor` checks the connection and visible model IDs, while `/models` lists what the server exposes.

## Capabilities

| Area | Tools |
| --- | --- |
| Local files | List files, read bounded text, search with ripgrep/fallback, write with timestamped backup, copy, move to Trash |
| macOS | System report, installed apps, processes, app launching, browser launch, clipboard read/write, AppleScript |
| Developer work | Git status/diff, find paths, run a zsh command in a chosen project folder |
| Web | DuckDuckGo search and public webpage text retrieval |
| Mail | Search recent Mail.app inbox messages by sender/subject; read-only |
| Hardware | Serial port list/read/send, ESP32-S3 reset/boot capture, allowlisted ADB diagnostics, CircuitPython deploy, ESP32-S3 app flashing |
| Video | Inspect FilmCraft projects and sequences; import media, run FilmCraft commands, and batch edits through local MCP |
| Sessions | SQLite conversation history, resume/list/delete/export, provider and model switching, JSONL action audit |

FilmCraft support uses the CLI at `~/filmcraft/filmcraft-cli` by default; change `filmcraft_cli_path` in `~/Library/Application Support/MacLocalHarness/config.toml` if you stored it elsewhere. Use `filmcraft_inspect` to inspect an existing `.fcproj`. `filmcraft_edit` asks for approval and saves the project after each edit; its MCP process runs as your Mac user and can access files that user can access. The FilmCraft MCP server does not provide folder confinement, so use a dedicated project and review any proposed imports, edits, or exports.

The tool registry is modular: add a Python file under `src/mac_harness/tools/`, register a function with its JSON parameter schema and risk level, then import the module from `tools/__init__.py`.

## Safety and privacy

- File tools start with `allowed_roots = ["~"]`, but block common secret locations and key files such as `.ssh`, `.aws`, `.codex`, Keychains, `.env*`, `.netrc`, `.npmrc`, and private-key extensions. Edit `allowed_roots` and `allow_sensitive_paths` in `config.toml` only when you intend to expand access.
- File writes create a timestamped backup when replacing an existing file. Deletion moves items into `~/.Trash` for recovery.
- The CLI asks for a typed `yes`, and the GUI shows an approval dialog, before each shell command, AppleScript, app/browser launch, write/copy/trash, clipboard operation, Mail/clipboard read, web request, serial transmission, or hardware deployment/flash.
- Shell commands (up to 4,000 characters) and AppleScript (up to 12,000 characters) are shown in full at approval. Very large file contents are previewed with the omitted middle identified; decline if you need to inspect the complete proposed content first.
- The configured terminal tool can run arbitrary zsh commands after approval. Approval prompts are a guardrail, **not** an OS sandbox; a command or AppleScript can access anything your Mac user account can access. Turn `allow_terminal_commands` off to disable that tool.
- Conversations are stored locally in `~/Library/Application Support/MacLocalHarness/conversations.sqlite3`; the audit log records action metadata, not tool output. The database is not app-level encrypted, so rely on your Mac account security/FileVault. `/delete ID` removes one saved conversation; deleting the project folder does not automatically erase that data.
- Local model traffic goes to the endpoint you configure. `custom_openai` can be remote, so confirm its host before sending private prompts. Web search sends its query to DuckDuckGo after approval. Page/mail/file text is treated as untrusted data by the system prompt.
- Web page retrieval only permits public HTTP/HTTPS host addresses and checks redirect targets. It is not a complete network sandbox.

## Commands

`/help`, `/doctor`, `/models`, `/model MODEL_ID`, `/provider`, `/tools`, `/threads`, `/new`, `/use ID`, `/clear`, `/delete ID`, `/export PATH`, `/settings`, `/quit`.

## Optional tools

`git`, `rg`, `adb`, `esptool`, and connected devices are optional. `pyserial` is installed with the project dependencies. The search tool falls back to a bounded Python scan when ripgrep is unavailable. Web tools require network access; everything else can run locally once dependencies and models are installed.
