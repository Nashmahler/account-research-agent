# Account Research Agent (public repo)

Public portfolio project. Never mention job searching, applications, or resumes anywhere in this repo, and never commit secrets (the API key lives in GitHub Actions secrets or a local .env).

## Rules for the agent itself
- Every claim a rep sees must cite a source number and quote that source word for word; verify.py enforces this in code. Never loosen it to make output look fuller.
- If nothing verifies, publish "No verified brief", never a guess.
- Hiring counts are computed in code, never by the model.
- At most 2 Claude calls per account (agent/llm.py).

## Git commits
- Always commit as the author Nash Mahler <mahler.nash@gmail.com>.
- Never set the commit author to Claude or noreply@anthropic.com.
- Before the first commit in a session, run `git config user.name` and `git config user.email`; if they aren't mine, set them for this repo.
- A "Co-Authored-By: Claude" line at the end of the message is fine.
- Exception: the GitHub Actions "Save brief" step commits as github-actions[bot] <41898583+github-actions[bot]@users.noreply.github.com>. These rules cover my own work, not automated runs.
