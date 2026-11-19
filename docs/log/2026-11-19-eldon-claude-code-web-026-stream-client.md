# Session log: web-026-stream-client

Date: 2026-11-19
Author: eldon
Tool and model: claude-code / sonnet
Plan IDs: WEB-026

## Summary
AG-UI stream client for the chat screen: own SSE parser, allow-list event mapper, ChatPort with abort, idle timeout and bounded retry, hostile-input tests. Not yet wired into ChatView (no token, Q-270).

## Files touched
- see the PR file list

## Decisions
- None.

## Tokens or cost
Subagent run, about 120k tokens.

## Next step
Open questions listed in docs/open-questions.md.
