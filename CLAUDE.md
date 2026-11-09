# Project notes for Claude Code

E-ink kitchen display: a Python server (`server/`, on Railway) renders the screen for a reTerminal E1001 tablet.
Read `docs/DEVELOPER_NOTES.md` first. It explains the architecture, how to add a tile, the custom tiles, the
test method and the gotchas.

Working rules the owner has asked for:
- **Mock up before building** anything visual, and show it enlarged with real data.
- **Ask before pushing** to GitHub, and **ask before sending anything to the live server**. The owner approves each.
- **Never put private data in the repository**: no keys, admin links or tokens, calendar links, the private
  schedule data or its code prefix, or personal details. The GitHub fork is public. Private data lives in Railway
  variables or on the Railway volume. The owner sometimes pastes private links in chat; do not repeat or store them.
- Scan everything git would commit for such data before every commit.
- Test on a local server with temporary paths (see the notes) and clean up test processes afterwards.
- Explain results plainly, say what was and was not tested, and name any limits honestly.
