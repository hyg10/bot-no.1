# -*- coding: utf-8 -*-
"""
Run Self-Improving Trading Bot
==============================
Entry point for the self-improving trading bot.

Setup:
  1. Copy .env.example to .env and fill in API keys
  2. Install dependencies: pip install -r requirements.txt
  3. Run: python run_self_improving_bot.py

The bot will:
  - Trade on Backpack Exchange using RL-guided decisions
  - Learn from each trade (DQN reinforcement learning)
  - Re-optimize parameters daily (genetic algorithm)
  - Trigger emergency optimization if performance drops
  - A/B test new parameters before applying them
  - Save RL model to models/rl/ for persistence across restarts
  - Log improvement history to logs/improvement/
"""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.self_improving_bot import main

if __name__ == "__main__":
    print("=" * 60)
    print("  Self-Improving Trading Bot v1.0")
    print("=" * 60)
    print("  [+] DQN Reinforcement Learning (learns from every trade)")
    print("  [+] Genetic Algorithm (daily parameter optimization)")
    print("  [+] A/B Testing (validates improvements before applying)")
    print("  [+] Emergency re-optimization on performance drops")
    print("  [+] Full risk management (SL, TP, trailing stop)")
    print("  [+] Trade Analysis (win/loss pattern learning)")
    print("-" * 60)
    print("  Logs   : logs/improvement/improvement_history.json")
    print("  Analysis: logs/trade_analysis/lessons.json")
    print("  RL Model: models/rl/rl_agent.npz")
    print("=" * 60)
    main()
