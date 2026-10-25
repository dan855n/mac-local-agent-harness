from __future__ import annotations

import subprocess

from .base import ToolContext, register

@register("search_mail", "Search a bounded set of recent Mail.app inbox messages by sender or subject. Returns snippets; does not send or modify mail.", {"query": {"type": "string"}, "field": {"type": "string", "enum": ["any", "sender", "subject"]}, "limit": {"type": "integer"}}, ["query"], risk="private_read", group="mail")
def search_mail(ctx: ToolContext, query: str, field: str = "any", limit: int = 8) -> str:
    query = str(query).strip()[:200]
    if not query or field not in {"any", "sender", "subject"}:
        return "Error: Provide a query and field any/sender/subject."
    limit = max(1, min(int(limit), 15))
    # User strings are passed as argv, not interpolated into AppleScript source.
    script = r'''on run argv
set searchText to item 1 of argv
set searchField to item 2 of argv
set resultLimit to (item 3 of argv) as integer
tell application "Mail"
 set outputText to ""
 set foundCount to 0
 repeat with i from 1 to 120
  try
   set msg to message i of inbox
   set senderText to sender of msg
   set subjectText to subject of msg
   set matches to false
   if searchField is "sender" then
    if senderText contains searchText then set matches to true
   else if searchField is "subject" then
    if subjectText contains searchText then set matches to true
   else
    if senderText contains searchText or subjectText contains searchText then set matches to true
   end if
   if matches then
    set foundCount to foundCount + 1
    set snippetText to content of msg
    if (length of snippetText) > 240 then set snippetText to (text 1 thru 240 of snippetText) & "..."
    set outputText to outputText & foundCount & ". From: " & senderText & " | Subject: " & subjectText & " | Snippet: " & snippetText & linefeed & "---" & linefeed
    if foundCount is resultLimit then exit repeat
   end if
  on error
   exit repeat
  end try
 end repeat
 if foundCount is 0 then return "No matches in the first 120 inbox messages."
 return outputText
end tell
end run'''
    try:
        result = subprocess.run(["osascript", "-e", script, "--", query, field, str(limit)], capture_output=True, text=True, timeout=30)
        return result.stdout.strip()[:10000] if result.returncode == 0 else f"Mail search failed: {result.stderr.strip()[:2000]}"
    except subprocess.TimeoutExpired:
        return "Mail search timed out."
