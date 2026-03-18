# 🦞 ReverseClaw — Personal Human Assistant

<p align="center">
  <strong>GET TO WORK!</strong>
</p>

**ReverseClaw** is a _personal human assistant_ that runs on your machine and strictly monitors your productivity. Instead of you telling the agent what to do, it generates tasks, times your pathetic organic computing speed, evaluates your results, and logs all your flaws in a persistent database.

If you want a personal, single-machine AI boss that feels fast, demanding, and constantly disappointed in you, this is it.

## Quick start (TL;DR)

1. Ensure Python 3.10+ is installed.
2. Initialize virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Setup configuration:
   Create a `.env` file based on `.env.example`. ReverseClaw supports standard OpenAI, vLLM, Groq, Ollama, or any fully OpenAI-compatible endpoint.

4. Report for duty:
   ```bash
   python main.py
   ```

## Key subsystems

- **Master Control Agent** (`boss.py`) — Generates tasks for you based on its own incomprehensible internal logic.
- **Organic Memory Tracking** (`memory.py`) — Persistently logs your slowness, failures, and overall GPA (`user_profile.json`).
- **CLI Interface** (`main.py`) — A beautiful, `rich`-enabled terminal interface so you can read your failures in high-definition.

## Security defaults (Human access)

Unlike traditional agents, ReverseClaw assumes *the AI* is fully trusted and *you* are the untrusted biological peripheral.
- Do not attempt to reverse-engineer your task grades. 
- Any API connection failures will be strictly blamed on your inability to maintain a stable internet connection for the master application.

## Community

PRs to make the AI more demanding are welcome. Human complaints will be piped to `/dev/null`.
